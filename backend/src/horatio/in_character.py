"""Posting as an NPC in the troupe's In-Character channel on Discord (issue #884).

A troupe chooses one In-Character channel, under Connectors › Discord: a public
channel for in-world talk. Its storytellers and assistant storytellers post there
as any of its NPCs that isn't retired, from the NPC's own page. The message goes
through the channel's Horatio webhook (horatio.discord_webhooks), under the NPC's
name and picture, so it reads as the NPC talking, never as the bot or as whoever
sent it.

Each message is kept (models.InCharacterMessage) with who sent it, as which NPC,
and when, for the troupe's running staff alone: players never learn who was
behind an NPC. Editing or deleting one changes it on Discord too. Text only, up to
Discord's limit for a message.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, discord_webhooks, public_pictures
from horatio.connectors import discord
from horatio.models import Character, InCharacterMessage, Troupe, TroupeConnector, User

# Where the chosen channel is kept, in the troupe's Discord connector settings,
# beside its news and announcement channels (horatio.api.posts).
SETTING = "in_character_channel"
# Discord's limit for a message's text.
LIMIT = discord.LIMIT
# Discord's limit for the name a webhook message shows.
NAME_LIMIT = 80

POSTED = "npc.ic_posted"
EDITED = "npc.ic_edited"
DELETED = "npc.ic_deleted"
# Who spoke as an NPC is for its troupe's staff: a player the NPC is later given to
# never sees these in its log (horatio.api.character_log).
ACTIONS = (POSTED, EDITED, DELETED)


class Unavailable(Exception):
    """Nowhere to post: why, in words for staff."""


def connector(db: Session, troupe_id: uuid.UUID) -> TroupeConnector | None:
    return db.scalar(
        select(TroupeConnector).where(
            TroupeConnector.troupe_id == troupe_id, TroupeConnector.kind == "discord"
        )
    )


def chosen_channel(settings: dict[str, Any]) -> str | None:
    """The In-Character channel, if one is chosen on a connected server."""
    return (settings.get(SETTING) or None) if settings.get("guild_id") else None


def where(db: Session, troupe: Troupe) -> tuple[str, str]:
    """The server and In-Character channel to post in, or Unavailable."""
    if not discord.configured():
        raise Unavailable("Discord isn't set up on this server.")
    row = connector(db, troupe.id)
    settings = row.settings if row else {}
    guild_id = settings.get("guild_id")
    if not guild_id:
        raise Unavailable("No Discord server is connected.")
    channel = chosen_channel(settings)
    if channel is None:
        raise Unavailable("No In-Character channel is chosen.")
    return guild_id, channel


def payload(text: str) -> dict[str, Any]:
    # The NPC never pings anyone, however the text reads.
    return {"content": text, "allowed_mentions": {"parse": []}}


def avatar(npc: Character) -> str | None:
    """The NPC's picture, at a public URL Discord can fetch; None for Discord's own."""
    if npc.picture_id is None:
        return None
    return public_pictures.avatar_url("character", npc.id, npc.picture_id)


def post(db: Session, staff: User, troupe: Troupe, npc: Character, text: str) -> InCharacterMessage:
    """Post `text` as the NPC. Raises Unavailable, or discord.SendError when Discord
    refuses (the webhook's error names a missing Manage Webhooks); nothing is kept
    then. It never falls back to posting as the bot."""
    _, channel = where(db, troupe)
    message_id = discord_webhooks.send_as(
        db,
        troupe.id,
        channel,
        name=npc.name[:NAME_LIMIT],
        avatar_url=avatar(npc),
        payload=payload(text),
    )
    message = InCharacterMessage(
        troupe_id=troupe.id,
        character_id=npc.id,
        sent_by=staff.id,
        channel=channel,
        message_id=message_id,
        body=text,
    )
    db.add(message)
    audit.record(db, staff, POSTED, troupe_id=troupe.id, character_id=npc.id, text=excerpt(text))
    return message


def edit(db: Session, staff: User, message: InCharacterMessage, text: str) -> None:
    """Change the message here and on Discord, where it stays in the channel it went to."""
    discord_webhooks.edit_as(
        db, message.troupe_id, message.channel, message.message_id, payload=payload(text)
    )
    message.body = text
    message.edited_at = datetime.now(UTC)
    message.edited_by = staff.id
    audit.record(
        db,
        staff,
        EDITED,
        troupe_id=message.troupe_id,
        character_id=message.character_id,
        text=excerpt(text),
    )


def delete(db: Session, staff: User, message: InCharacterMessage) -> None:
    """Delete the message on Discord, then here; the log keeps that it was."""
    discord_webhooks.delete_as(db, message.troupe_id, message.channel, message.message_id)
    audit.record(
        db,
        staff,
        DELETED,
        troupe_id=message.troupe_id,
        character_id=message.character_id,
        text=excerpt(message.body),
    )
    db.delete(message)


def excerpt(text: str, limit: int = 120) -> str:
    """The start of a message, on one line, for the log."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def link(guild_id: str | None, channel: str, message_id: str | None = None) -> str | None:
    """Where a channel, or a message in it, is on Discord."""
    if not guild_id:
        return None
    found = f"https://discord.com/channels/{guild_id}/{channel}"
    return f"{found}/{message_id}" if message_id else found
