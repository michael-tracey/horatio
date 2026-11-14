"""Connecting a troupe's Discord server, and the channels to pick from."""

import secrets
import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select, update

from horatio import audit, discord_channels
from horatio.api import discord_account
from horatio.api.connectors import connector_row
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import SendError, discord
from horatio.models import Character, NewsAgency, Troupe, TroupeConnector, User
from horatio.permissions import TroupeAction

router = APIRouter(tags=["connectors"])


class Invite(BaseModel):
    url: str


class ChannelOut(BaseModel):
    id: str
    name: str
    category: str | None
    private: bool
    # Of View Channels, Send Messages, Embed Links and Attach Files, those the
    # Horatio bot lacks here (#839), or None when Discord wouldn't say.
    missing: list[str] | None = None


class CharacterRef(BaseModel):
    id: uuid.UUID
    name: str


class RoleOut(BaseModel):
    id: str
    name: str


class MatchOut(BaseModel):
    """The member a player's typed Discord username found, for a storyteller to
    confirm is them."""

    username: str
    display_name: str
    avatar: str | None


class ManagedCharacter(BaseModel):
    # What last happened when Horatio was asked for its channel, in words, or None.
    status: str | None
    note: str | None
    # Its channel is one Horatio made, and that channel.
    made: bool
    channel: str | None = None
    # How Horatio knows its player on Discord (horatio.discord_channels.discord_of).
    discord: Literal["verified", "confirmed", "typed", "none"]
    # The username they typed, or the one staff confirmed; None when verified or none.
    username: str | None
    match: MatchOut | None


class ChannelProblemOut(BaseModel):
    """Something wrong with a channel Horatio made (#856), and its fix, if any:
    "fix" (put it right), "remake" (make it again), "invite" (invite its player) or
    "relink" (send its character's results there again)."""

    key: str
    # The character, or None for the server as a whole.
    character_id: str | None
    name: str | None
    kind: str
    note: str
    fix: Literal["fix", "remake", "invite", "relink"] | None
    since: datetime


class ManagedOut(BaseModel):
    """Character channels Horatio makes on the server (#855), kept in step and
    checked (#856)."""

    on: bool
    # The server's roles let into every channel Horatio makes, by id.
    staff_roles: list[str]
    # The server's roles to choose them from; empty when Discord wouldn't say.
    roles: list[RoleOut]
    # What the bot lacks on the server to make channels, or None when Discord
    # wouldn't say.
    lacks: list[str] | None
    # Whether it may invite players who aren't on the server; None when unknown.
    can_invite: bool | None
    queued: int
    characters: dict[str, ManagedCharacter]
    # What a check found wrong, the oldest first.
    problems: list[ChannelProblemOut] = []
    # When Horatio last checked the channels, whether staff asked it to check again,
    # and how many channels wait to be brought into step.
    checked_at: datetime | None = None
    checking: bool = False
    syncing: int = 0


class DiscordSetup(BaseModel):
    guild_id: str | None
    guild_name: str | None
    channels: list[ChannelOut]
    # The troupe's characters, to give each a channel.
    characters: list[CharacterRef]
    # A channel for each character whose name it matches, by character id, for
    # storytellers to use or not (horatio.connectors.discord.suggested_channels).
    suggestions: dict[str, str]
    # Character channels Horatio makes; None with no server connected.
    managed: ManagedOut | None = None


def discord_row(db: DbSession, troupe_id: uuid.UUID) -> TroupeConnector:
    row = connector_row(db, troupe_id, "discord")
    if row is None:
        row = TroupeConnector(troupe_id=troupe_id, kind="discord", settings={})
        db.add(row)
    return row


def available() -> None:
    reason = discord.DiscordConnector().unavailable()
    if reason is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, reason)


@router.post("/troupes/{troupe_id}/discord/invite")
def discord_invite(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Invite:
    """Discord's page for adding the Horatio bot to the troupe's server. Discord
    sends the storyteller back to `/api/discord/callback`."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CONNECTORS)
    available()
    row = discord_row(db, troupe.id)
    token = secrets.token_urlsafe(24)
    row.settings = {**row.settings, "pending_state": token}
    db.commit()
    return Invite(url=discord.invite_url(f"{troupe.id}.{token}"))


@router.get("/discord/callback", include_in_schema=False)
def discord_callback(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Where Discord sends a storyteller after they add the bot (or decline), and
    a player after they link their own Discord account (`state` begins `link.`)."""
    if state.startswith(discord.LINK_STATE):
        return discord_account.finish_link(request, db, user, state, code, error)
    troupe_part, _, token = state.partition(".")
    try:
        troupe_id = uuid.UUID(troupe_part)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That link is not from Horatio.") from None
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CONNECTORS)
    row = connector_row(db, troupe.id, "discord")
    expected = (row.settings.get("pending_state") if row else None) or ""
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That link has expired; try again.")
    assert row is not None

    def back(outcome: str) -> RedirectResponse:
        query = urlencode({"discord": outcome})
        return RedirectResponse(f"/troupes/{troupe.id}/connectors?{query}", status_code=303)

    settings = {k: v for k, v in row.settings.items() if k != "pending_state"}
    if error or not code:
        row.settings = settings
        db.commit()
        return back("cancelled")
    try:
        guild_id, guild_name = discord.exchange_code(code)
    except SendError as failure:
        row.settings = settings
        db.commit()
        return back(failure.reason)
    if guild_id != settings.get("guild_id"):
        # A different server: channels picked in the old one mean nothing here,
        # including those for the troupe's news (horatio.posts).
        settings = {"channels": {}, "test_channel": None}
        db.execute(
            update(NewsAgency).where(NewsAgency.troupe_id == troupe.id).values(discord_channel=None)
        )
    row.settings = {**settings, "guild_id": guild_id, "guild_name": guild_name}
    audit.record(db, user, "connector.discord_connected", troupe_id=troupe.id, server=guild_name)
    db.commit()
    return back("connected")


@router.delete("/troupes/{troupe_id}/discord", status_code=status.HTTP_204_NO_CONTENT)
def discord_disconnect(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Forget the troupe's server and its channels, and stop sending to Discord.
    The bot stays in the server until someone there removes it."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CONNECTORS)
    row = connector_row(db, troupe.id, "discord")
    if row is None or not row.settings.get("guild_id"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No Discord server is connected.")
    server = row.settings.get("guild_name") or row.settings["guild_id"]
    row.settings = {}
    row.enabled = False
    audit.record(db, user, "connector.discord_disconnected", troupe_id=troupe.id, server=server)
    db.commit()


@router.get("/troupes/{troupe_id}/discord")
def discord_setup(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DiscordSetup:
    """The connected server, its text channels with the permissions the bot lacks in
    each, and the troupe's characters, with the channel each one's name suggests.
    Four calls to Discord."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.DELIVER_RESPONSES)
    row = connector_row(db, troupe.id, "discord")
    guild_id = row.settings.get("guild_id") if row else None
    found: list[discord.Channel] = []
    access: discord.BotAccess | None = None
    if guild_id and discord.configured():
        try:
            access = discord.bot_access(guild_id)
        except SendError:
            access = None
        try:
            found = discord.text_channels(guild_id, permissions=access is not None, access=access)
        except SendError as failure:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, failure.reason) from None
    listed = discord_channels.characters(db, troupe.id)
    characters = [CharacterRef(id=c.id, name=c.name) for c in listed]
    return DiscordSetup(
        guild_id=guild_id,
        guild_name=row.settings.get("guild_name") if row else None,
        channels=[ChannelOut(**c.__dict__) for c in found],
        characters=characters,
        suggestions=discord.suggested_channels([(c.id, c.name) for c in characters], found),
        managed=managed_out(db, row, listed, access) if row is not None and guild_id else None,
    )


def managed_out(
    db: DbSession,
    row: TroupeConnector,
    listed: list[Character],
    access: discord.BotAccess | None,
) -> ManagedOut:
    parts = discord_channels.managed(row.settings)
    channels = row.settings.get("channels") or {}
    players = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_([c.player_id for c in listed if c.player_id]))
        )
    }
    found: dict[str, ManagedCharacter] = {}
    for character in listed:
        key = str(character.id)
        player = players.get(character.player_id) if character.player_id else None
        kind, _ = discord_channels.discord_of(parts, player)
        state = parts["state"].get(key) or {}
        match = parts["pending"].get(str(player.id)) if player is not None else None
        confirmed = parts["members"].get(str(player.id)) if player is not None else None
        made = bool(channels.get(key)) and parts["made"].get(key) == channels.get(key)
        found[key] = ManagedCharacter(
            status=state.get("status"),
            note=state.get("note"),
            made=made,
            channel=channels.get(key) if made else None,
            discord=kind,  # type: ignore[arg-type]  # one of the four
            username=(confirmed or {}).get("username")
            if kind == "confirmed"
            else (player.discord_handle if kind == "typed" and player is not None else None),
            match=MatchOut(
                username=match["username"],
                display_name=match["display_name"],
                avatar=match.get("avatar"),
            )
            if match and match.get("character_id") in (key, None)
            else None,
        )
    server = access.server_permissions() if access is not None else None
    return ManagedOut(
        on=parts["on"],
        staff_roles=parts["staff_roles"],
        roles=[RoleOut(id=r.id, name=r.name) for r in access.named_roles] if access else [],
        lacks=discord.missing(server, discord.FOR_MANAGED) if server is not None else None,
        can_invite=bool(server & discord.CREATE_INSTANT_INVITE) if server is not None else None,
        queued=len(parts["queue"]),
        characters=found,
        problems=sorted(
            (
                ChannelProblemOut(
                    key=key,
                    character_id=p.get("character_id") if p.get("kind") != "server" else None,
                    name=p.get("name"),
                    kind=p.get("kind", ""),
                    note=p.get("note", ""),
                    fix=p.get("fix"),
                    since=datetime.fromisoformat(p["since"]),
                )
                for key, p in parts["problems"].items()
            ),
            key=lambda p: (p.since, p.key),
        ),
        checked_at=datetime.fromisoformat(parts["checked_at"]) if parts["checked_at"] else None,
        checking=bool(parts["check_asked"]),
        syncing=len(parts["made"]) if "*" in parts["sync"] else len(parts["sync"]),
    )


class ManagedChange(BaseModel):
    on: bool
    # Server role ids let into every channel Horatio makes.
    staff_roles: list[str] = []


class OutcomeOut(BaseModel):
    status: str
    note: str
    # The channel made, or the one it had already.
    channel: str | None


class MatchAnswer(BaseModel):
    # Whether the member the typed username found is really the player.
    its_them: bool


class Queued(BaseModel):
    queued: int


def managing_troupe(
    db: DbSession, user: User, troupe_id: uuid.UUID
) -> tuple[Troupe, TroupeConnector]:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CONNECTORS)
    available()
    row = connector_row(db, troupe.id, "discord")
    if row is None or not row.settings.get("guild_id"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a Discord server first.")
    return troupe, row


def listed_character(db: DbSession, troupe: Troupe, character_id: uuid.UUID) -> Character:
    character = db.get(Character, character_id)
    if character is None or character not in discord_channels.characters(db, troupe.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character in this troupe.")
    return character


@router.put("/troupes/{troupe_id}/discord/managed", status_code=status.HTTP_204_NO_CONTENT)
def change_managed(
    troupe_id: uuid.UUID, body: ManagedChange, db: DbSession, user: CurrentUser
) -> None:
    """Switch Horatio making the troupe's character channels on or off, and choose
    the server's roles let into each (#855)."""
    troupe, row = managing_troupe(db, user, troupe_id)
    guild = str(row.settings["guild_id"])
    roles = list(dict.fromkeys(body.staff_roles))
    names: dict[str, str] = {}
    if roles:
        try:
            access = discord.bot_access(guild)
        except SendError as failure:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, failure.reason) from None
        names = {r.id: r.name for r in access.named_roles}
        if any(r not in names for r in roles):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick roles from the server's own roles."
            )
    row = discord_channels.locked(db, troupe.id)
    assert row is not None
    parts = discord_channels.managed(row.settings)
    if parts["on"] != body.on:
        audit.record(
            db,
            user,
            "connector.discord_managed",
            troupe_id=troupe.id,
            state="on" if body.on else "off",
        )
    if parts["staff_roles"] != roles:
        audit.record(
            db,
            user,
            "connector.discord_staff_roles",
            troupe_id=troupe.id,
            roles=", ".join(f"@{names[r]}" for r in roles) if roles else "none",
        )
    if parts["staff_roles"] != roles:
        # Every channel Horatio made lets the new roles in and the old ones out (#856).
        discord_channels.staff_roles_changed(parts)
    parts["on"] = body.on
    parts["staff_roles"] = roles
    if not body.on:
        parts["queue"] = []
    discord_channels.save(row, parts)
    db.commit()


def outcome_out(outcome: discord_channels.Outcome) -> OutcomeOut:
    return OutcomeOut(status=outcome.status, note=outcome.note, channel=outcome.channel)


@router.post("/troupes/{troupe_id}/discord/characters/{character_id}/channel")
def make_channel(
    troupe_id: uuid.UUID, character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> OutcomeOut:
    """Make the character's private channel now, or say what stands in the way."""
    troupe, _ = managing_troupe(db, user, troupe_id)
    character = listed_character(db, troupe, character_id)
    try:
        outcome = discord_channels.make(db, troupe, character, user)
    except SendError as failure:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, failure.reason) from None
    db.commit()
    return outcome_out(outcome)


@router.post("/troupes/{troupe_id}/discord/characters/{character_id}/match")
def answer_match(
    troupe_id: uuid.UUID,
    character_id: uuid.UUID,
    body: MatchAnswer,
    db: DbSession,
    user: CurrentUser,
) -> OutcomeOut:
    """Say whether the member a player's typed Discord username found is them;
    yes makes the channel."""
    troupe, _ = managing_troupe(db, user, troupe_id)
    character = listed_character(db, troupe, character_id)
    try:
        outcome = discord_channels.confirm(db, troupe, character, user, body.its_them)
    except LookupError as missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(missing)) from None
    except SendError as failure:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, failure.reason) from None
    db.commit()
    return outcome_out(outcome)


@router.post("/troupes/{troupe_id}/discord/channels")
def make_every_channel(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Queued:
    """Queue every character without a channel; the worker makes them, a few at a
    time, as Discord allows."""
    troupe, row = managing_troupe(db, user, troupe_id)
    if not discord_channels.managed(row.settings)["on"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Horatio doesn't make this troupe's channels: switch it on first.",
        )
    queued = discord_channels.queue_all(db, troupe, user)
    db.commit()
    return Queued(queued=queued)


class FixAsk(BaseModel):
    how: Literal["fix", "remake", "invite", "relink"]


@router.post("/troupes/{troupe_id}/discord/check", status_code=status.HTTP_204_NO_CONTENT)
def check_channels(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Ask Horatio to check every channel it made against what it set (#856); the
    worker does it, and the page shows what it found."""
    troupe, row = managing_troupe(db, user, troupe_id)
    if not discord_channels.managed(row.settings)["on"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Horatio doesn't make this troupe's channels: switch it on first.",
        )
    discord_channels.ask_check(db, troupe, user)
    db.commit()


@router.post("/troupes/{troupe_id}/discord/characters/{character_id}/fix")
def fix_channel(
    troupe_id: uuid.UUID, character_id: uuid.UUID, body: FixAsk, db: DbSession, user: CurrentUser
) -> OutcomeOut:
    """Put right something wrong with a channel Horatio made (#856)."""
    troupe, _ = managing_troupe(db, user, troupe_id)
    character = db.get(Character, character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    try:
        outcome = discord_channels.fix(db, troupe, character, body.how, user)
    except LookupError as missing:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(missing)) from None
    except SendError as failure:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, failure.reason) from None
    db.commit()
    return outcome_out(outcome)
