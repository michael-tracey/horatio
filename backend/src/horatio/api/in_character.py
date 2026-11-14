"""Posting as an NPC in the troupe's In-Character channel on Discord (issue #884;
horatio.in_character): choosing the channel, and posting, editing and deleting an
NPC's messages from its page.

The troupe's storytellers and assistant storytellers, who manage its NPCs, post and
see who sent each message. Choosing the channel is managing connectors, a
storyteller's, as the news and announcement channels are (horatio.api.posts).
Narrators and players never see an NPC's page, nor who spoke as it.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, in_character
from horatio.api.connectors import connector_row
from horatio.api.discord import ChannelOut
from horatio.api.downtimes import staff_troupe
from horatio.api.posts import known_channel
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import SendError, discord
from horatio.models import Character, InCharacterMessage, Troupe, User
from horatio.permissions import (
    TroupeAction,
    allows,
    require_troupe_action,
    troupe_role,
    visible_character,
)

router = APIRouter(tags=["in character"])

# The most recent messages an NPC's page lists.
RECENT = 50


class InCharacterChannelOut(BaseModel):
    # The connected server's name, or why there is none to choose from.
    server: str | None
    unavailable: str | None
    channels: list[ChannelOut]
    # The In-Character channel, if one is chosen.
    channel: str | None
    # Whether the caller may choose (a storyteller's, as connectors are).
    can_change: bool


class InCharacterChannelIn(BaseModel):
    channel: str | None


class InCharacterMessageOut(BaseModel):
    id: uuid.UUID
    body: str
    sent_at: datetime
    # Who sent it, by name: for the troupe's running staff only.
    sent_by: str
    edited_at: datetime | None
    edited_by: str | None
    # Where it is on Discord, while the server is connected.
    link: str | None


class InCharacterOut(BaseModel):
    """An NPC's in-character messages, newest first, and whether it can post now."""

    troupe_id: uuid.UUID
    # Why it can't post now (no channel chosen, retired, ...), or None when it can.
    unavailable: str | None
    # Whether that is for want of a server or channel, chosen in Connectors › Discord.
    needs_channel: bool
    # The In-Character channel on Discord, while one is chosen.
    channel_link: str | None
    # Whether the caller chooses the channel themselves (a storyteller), or asks one.
    can_choose_channel: bool
    messages: list[InCharacterMessageOut]
    # There are older ones than these.
    older: bool


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=in_character.LIMIT)


# --- who may ---------------------------------------------------------------------------


def staff_npc(db: Session, user: User, character_id: uuid.UUID) -> tuple[Character, Troupe]:
    """The NPC, if the caller manages its troupe's NPCs; 404 for anyone who can't see
    it at all, so nobody learns what NPCs a troupe keeps."""
    npc = visible_character(db, user, character_id)
    troupe = db.get(Troupe, npc.owner_troupe_id) if npc.owner_troupe_id else None
    if npc.kind != "npc" or troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such NPC.")
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_NPCS)
    return npc, troupe


def staff_message(
    db: Session, user: User, message_id: uuid.UUID
) -> tuple[InCharacterMessage, Character, Troupe]:
    message = db.get(InCharacterMessage, message_id, with_for_update=True)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such message.")
    npc, troupe = staff_npc(db, user, message.character_id)
    if message.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such message.")
    return message, npc, troupe


def going_out(troupe: Troupe) -> None:
    """Nothing goes out from an archived troupe, even at the custodian's hand."""
    if troupe.archived_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This troupe is archived, so nothing goes to Discord."
        )


def why_not(db: Session, troupe: Troupe, npc: Character) -> str | None:
    """Why the NPC can't post now, or None."""
    if troupe.archived_at is not None:
        return "This troupe is archived, so nothing goes to Discord."
    if npc.status != "active":
        return f"{npc.name} is retired, so can't post."
    try:
        in_character.where(db, troupe)
    except in_character.Unavailable as reason:
        return str(reason)
    return None


def text_of(body: TextIn) -> str:
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Write something to post.")
    return text


def failed(error: SendError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, error.reason)


# --- the channel -----------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/in-character-channel")
def in_character_channel(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> InCharacterChannelOut:
    """The troupe's In-Character channel on Discord, and those to choose from."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_NPCS)
    row = connector_row(db, troupe.id, "discord")
    settings = row.settings if row else {}
    guild_id = settings.get("guild_id")
    unavailable = discord.DiscordConnector().unavailable() or (
        None if guild_id else "No Discord server is connected."
    )
    channels: list[ChannelOut] = []
    if unavailable is None and guild_id:
        try:
            channels = [
                ChannelOut(**c.__dict__) for c in discord.text_channels(guild_id, permissions=True)
            ]
        except SendError as failure:
            unavailable = failure.reason
    return InCharacterChannelOut(
        server=settings.get("guild_name"),
        unavailable=unavailable,
        channels=channels,
        channel=in_character.chosen_channel(settings),
        can_change=allows(
            troupe_role(db, user, troupe),
            TroupeAction.MANAGE_CONNECTORS,
            is_custodian=user.is_custodian,
        ),
    )


@router.put("/troupes/{troupe_id}/in-character-channel")
def choose_in_character_channel(
    troupe_id: uuid.UUID, body: InCharacterChannelIn, db: DbSession, user: CurrentUser
) -> InCharacterChannelOut:
    """Choose the In-Character channel, or none."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_CONNECTORS)
    row = connector_row(db, troupe.id, "discord")
    guild_id = row.settings.get("guild_id") if row else None
    if row is None or not guild_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a Discord server first.")
    channel = known_channel(guild_id, body.channel) if body.channel else None
    settings = {k: v for k, v in row.settings.items() if k != in_character.SETTING}
    row.settings = {**settings, **({in_character.SETTING: channel} if channel else {})}
    audit.record(
        db,
        user,
        "post.channel_chosen",
        troupe_id=troupe.id,
        what="In-Character channel",
        state="chosen" if channel else "cleared",
    )
    db.commit()
    return in_character_channel(troupe.id, db, user)


# --- an NPC's messages -----------------------------------------------------------------


def messages_out(
    db: Session, troupe: Troupe, found: list[InCharacterMessage]
) -> list[InCharacterMessageOut]:
    row = connector_row(db, troupe.id, "discord")
    guild_id = row.settings.get("guild_id") if row else None
    people = {m.sent_by for m in found} | {m.edited_by for m in found if m.edited_by}
    names = {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(people)))}
    return [
        InCharacterMessageOut(
            id=m.id,
            body=m.body,
            sent_at=m.created_at,
            sent_by=names.get(m.sent_by, "Someone"),
            edited_at=m.edited_at,
            edited_by=names.get(m.edited_by) if m.edited_by else None,
            link=in_character.link(guild_id, m.channel, m.message_id),
        )
        for m in found
    ]


def message_out(db: Session, troupe: Troupe, message: InCharacterMessage) -> InCharacterMessageOut:
    db.flush()
    db.refresh(message)
    return messages_out(db, troupe, [message])[0]


@router.get("/characters/{character_id}/in-character")
def npc_in_character(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> InCharacterOut:
    """The NPC's recent in-character messages, with who sent each, for its troupe's
    storytellers and assistant storytellers; and whether it can post now."""
    npc, troupe = staff_npc(db, user, character_id)
    found = list(
        db.scalars(
            select(InCharacterMessage)
            .where(
                InCharacterMessage.character_id == npc.id,
                InCharacterMessage.troupe_id == troupe.id,
            )
            .order_by(InCharacterMessage.created_at.desc(), InCharacterMessage.id.desc())
            .limit(RECENT + 1)
        )
    )
    row = connector_row(db, troupe.id, "discord")
    settings = row.settings if row else {}
    channel = in_character.chosen_channel(settings)
    unavailable = why_not(db, troupe, npc)
    return InCharacterOut(
        troupe_id=troupe.id,
        unavailable=unavailable,
        needs_channel=unavailable is not None
        and channel is None
        and npc.status == "active"
        and troupe.archived_at is None,
        channel_link=in_character.link(settings.get("guild_id"), channel) if channel else None,
        can_choose_channel=allows(
            troupe_role(db, user, troupe),
            TroupeAction.MANAGE_CONNECTORS,
            is_custodian=user.is_custodian,
        ),
        messages=messages_out(db, troupe, found[:RECENT]),
        older=len(found) > RECENT,
    )


@router.post("/characters/{character_id}/in-character", status_code=status.HTTP_201_CREATED)
def post_in_character(
    character_id: uuid.UUID, body: TextIn, db: DbSession, user: CurrentUser
) -> InCharacterMessageOut:
    """Post in the In-Character channel as the NPC, under its name and picture."""
    npc, troupe = staff_npc(db, user, character_id)
    text = text_of(body)
    reason = why_not(db, troupe, npc)
    if reason is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    try:
        message = in_character.post(db, user, troupe, npc, text)
    except in_character.Unavailable as unavailable:
        raise HTTPException(status.HTTP_409_CONFLICT, str(unavailable)) from None
    except SendError as error:
        db.rollback()
        raise failed(error) from None
    db.commit()
    return message_out(db, troupe, message)


@router.put("/in-character-messages/{message_id}")
def edit_in_character(
    message_id: uuid.UUID, body: TextIn, db: DbSession, user: CurrentUser
) -> InCharacterMessageOut:
    """Change a message, here and on Discord."""
    message, _, troupe = staff_message(db, user, message_id)
    going_out(troupe)
    text = text_of(body)
    try:
        in_character.edit(db, user, message, text)
    except SendError as error:
        db.rollback()
        if error.status == 404:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "That message is no longer on Discord, so it can't be edited. Delete it here.",
            ) from None
        raise failed(error) from None
    db.commit()
    return message_out(db, troupe, message)


@router.delete("/in-character-messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_in_character(message_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Delete a message from Discord, and from the NPC's list."""
    message, _, troupe = staff_message(db, user, message_id)
    going_out(troupe)
    try:
        in_character.delete(db, user, message)
    except SendError as error:
        db.rollback()
        raise failed(error) from None
    db.commit()
