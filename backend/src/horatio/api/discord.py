"""Connecting a troupe's Discord server, and the channels to pick from."""

import secrets
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from horatio import audit
from horatio.api.connectors import connector_row
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import SendError, discord
from horatio.models import Character, TroupeConnector
from horatio.permissions import TroupeAction

router = APIRouter(tags=["connectors"])


class Invite(BaseModel):
    url: str


class ChannelOut(BaseModel):
    id: str
    name: str
    category: str | None
    private: bool


class CharacterRef(BaseModel):
    id: uuid.UUID
    name: str


class DiscordSetup(BaseModel):
    guild_id: str | None
    guild_name: str | None
    channels: list[ChannelOut]
    # The troupe's characters, to give each a channel.
    characters: list[CharacterRef]


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
    db: DbSession,
    user: CurrentUser,
    state: str = "",
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Where Discord sends a storyteller after they add the bot (or decline)."""
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
        # A different server: channels picked in the old one mean nothing here.
        settings = {"channels": {}, "test_channel": None}
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
    """The connected server, its text channels, and the troupe's characters."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.DELIVER_RESPONSES)
    row = connector_row(db, troupe.id, "discord")
    guild_id = row.settings.get("guild_id") if row else None
    channels: list[ChannelOut] = []
    if guild_id and discord.configured():
        try:
            channels = [ChannelOut(**c.__dict__) for c in discord.text_channels(guild_id)]
        except SendError as failure:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, failure.reason) from None
    return DiscordSetup(
        guild_id=guild_id,
        guild_name=row.settings.get("guild_name") if row else None,
        channels=channels,
        characters=[
            CharacterRef(id=c.id, name=c.name)
            for c in db.scalars(
                select(Character)
                .where(
                    Character.home_troupe_id == troupe.id,
                    Character.kind == "pc",
                    Character.status == "active",
                )
                .order_by(Character.name)
            )
        ],
    )
