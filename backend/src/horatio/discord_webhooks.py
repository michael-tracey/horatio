"""Posting to Discord under another name and picture (#883): a news story as its
agency, and (#884) an in-character message as an NPC. Discord lets a message have
its own sender only when it goes through a channel's webhook, so the bot makes one
Horatio webhook in each channel it posts to this way, keeps it (`DiscordWebhook`),
and reuses it; each message sets its own name and picture.

Making a webhook needs Manage Webhooks in the channel. Without it these raise a
SendError (status 403) that names it, and never post as the bot instead: a caller
that wants that (news stories) catches the error and does so itself.

A webhook someone deleted on Discord is made again, once, when posting. Messages it
sent can no longer be edited or deleted by Horatio: an edit says the message is gone
(status 404), so the caller posts it again, and a deletion counts as done.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.connectors import SendError, discord
from horatio.models import DiscordWebhook

# The webhook's own name, as the channel's settings on Discord list it.
NAME = "Horatio"
# Discord's error code for a webhook that no longer exists, and for a wrong token.
UNKNOWN_WEBHOOK = 10015
INVALID_TOKEN = 50027
# A sender's name: 1 to 80 characters, and Discord refuses some words in it.
NAME_LIMIT = 80
REFUSED_WORDS = ("discord", "clyde")


@dataclass(frozen=True)
class Hook:
    id: str
    token: str


def sender_name(name: str) -> str:
    """A name as a webhook's message may carry it: at most 80 characters, and with
    the words Discord refuses in a sender's name ("Discord", "Clyde") broken by an
    invisible space, so "The Discord Daily" still reads as itself."""
    text = " ".join(name.split())[:NAME_LIMIT] or NAME
    for word in REFUSED_WORDS:
        at = text.casefold().find(word)
        while at != -1:
            text = f"{text[: at + 1]}​{text[at + 1 :]}"
            at = text.casefold().find(word, at + 2)
    return text[:NAME_LIMIT]


def gone(error: SendError) -> bool:
    """Whether Discord says the webhook itself is no longer there."""
    return error.code in (UNKNOWN_WEBHOOK, INVALID_TOKEN) or error.status == 401


def lacks_webhooks(error: SendError, channel: str) -> SendError:
    """A refusal to make or list webhooks, naming Manage Webhooks (and whatever else
    the bot lacks there) when it is for want of permission."""
    if error.status != 403:
        return error
    discord.explained(error, channel, discord.FOR_WEBHOOKS)
    if "Manage Webhooks" not in error.reason:
        error.reason = (
            "The Horatio bot needs Manage Webhooks in that channel. "
            "Give it that permission in the channel's settings on Discord."
        )
    return error


def ours(found: Mapping[str, Any]) -> bool:
    """A webhook the Horatio bot made, which it may post through."""
    return (
        found.get("type") == 1
        and bool(found.get("token"))
        and str(found.get("application_id") or "") == str(get_settings().discord_client_id or "")
    )


def make(channel: str) -> Hook:
    """The channel's Horatio webhook: one the bot made before, if Discord still has
    it, or a new one. Raises SendError, naming Manage Webhooks when the bot lacks it."""
    try:
        listed = discord.request("GET", f"/channels/{channel}/webhooks").json()
        found = next((w for w in listed if ours(w) and w.get("name") == NAME), None)
        if found is None:
            found = discord.request(
                "POST", f"/channels/{channel}/webhooks", json={"name": NAME}
            ).json()
        return Hook(id=str(found["id"]), token=str(found["token"]))
    except SendError as error:
        raise lacks_webhooks(error, channel) from None
    except (KeyError, TypeError, ValueError) as error:
        raise SendError(
            "Discord's answer about the channel's webhook was not as expected.", retry=False
        ) from error


def stored(db: Session, troupe_id: uuid.UUID, channel: str) -> DiscordWebhook | None:
    return db.scalar(
        select(DiscordWebhook).where(
            DiscordWebhook.troupe_id == troupe_id, DiscordWebhook.channel == channel
        )
    )


def keep(db: Session, troupe_id: uuid.UUID, channel: str, hook: Hook) -> Hook:
    """Store the channel's webhook, or, when another post stored one first, use that."""
    db.execute(
        insert(DiscordWebhook)
        .values(troupe_id=troupe_id, channel=channel, webhook_id=hook.id, token=hook.token)
        .on_conflict_do_nothing(index_elements=["troupe_id", "channel"])
    )
    row = stored(db, troupe_id, channel)
    assert row is not None
    db.refresh(row)
    return Hook(id=row.webhook_id, token=row.token)


def hook_for(db: Session, troupe_id: uuid.UUID, channel: str) -> Hook:
    row = stored(db, troupe_id, channel)
    if row is not None:
        return Hook(id=row.webhook_id, token=row.token)
    return keep(db, troupe_id, channel, make(channel))


def remade(db: Session, troupe_id: uuid.UUID, channel: str) -> Hook:
    """A new webhook for the channel, in place of one that has gone from Discord."""
    row = stored(db, troupe_id, channel)
    hook = make(channel)
    if row is None:
        return keep(db, troupe_id, channel, hook)
    row.webhook_id, row.token = hook.id, hook.token
    db.flush()
    return hook


def execute(
    hook: Hook,
    name: str,
    avatar_url: str | None,
    payload: Mapping[str, Any],
    files: Sequence[discord.File],
) -> str:
    sender: dict[str, Any] = {"username": sender_name(name)}
    if avatar_url:
        sender["avatar_url"] = avatar_url
    sent = discord.request(
        "POST",
        f"/webhooks/{hook.id}/{hook.token}",
        bot=False,
        params={"wait": "true"},
        **discord.message_request({**payload, **sender}, files),
    )
    return str(sent.json()["id"])


def send_as(
    db: Session,
    troupe_id: uuid.UUID,
    channel: str,
    *,
    name: str,
    avatar_url: str | None,
    payload: Mapping[str, Any],
    files: Sequence[discord.File] = (),
) -> str:
    """Posts to `channel` as `name` with `avatar_url`; returns the message id.
    Without a picture, Discord shows its default one. Raises SendError: status 403,
    naming Manage Webhooks, when the bot may not make the channel's webhook."""
    hook = hook_for(db, troupe_id, channel)
    try:
        return execute(hook, name, avatar_url, payload, files)
    except SendError as error:
        if not gone(error):
            raise
    return execute(remade(db, troupe_id, channel), name, avatar_url, payload, files)


def edit_as(
    db: Session,
    troupe_id: uuid.UUID,
    channel: str,
    message_id: str,
    *,
    payload: Mapping[str, Any],
    files: Sequence[discord.File] = (),
) -> None:
    """Change a message sent through the channel's webhook; its sender stays as it
    was. Raises SendError, with status 404 when the message, or the webhook that
    sent it, is no longer there."""
    row = stored(db, troupe_id, channel)
    if row is None:
        raise SendError("That message is no longer on Discord.", retry=False, status=404)
    try:
        discord.request(
            "PATCH",
            f"/webhooks/{row.webhook_id}/{row.token}/messages/{message_id}",
            bot=False,
            **discord.message_request(payload, files),
        )
    except SendError as error:
        if gone(error):
            raise SendError(
                "That message is no longer on Discord.", retry=False, status=404
            ) from None
        raise


def delete_as(db: Session, troupe_id: uuid.UUID, channel: str, message_id: str) -> None:
    """Delete a message sent through the channel's webhook. One already gone is no
    failure, nor is one whose webhook is gone, which Horatio can no longer delete."""
    row = stored(db, troupe_id, channel)
    if row is None:
        return
    try:
        discord.request(
            "DELETE",
            f"/webhooks/{row.webhook_id}/{row.token}/messages/{message_id}",
            bot=False,
        )
    except SendError as error:
        if error.status != 404 and not gone(error):
            raise


def forget(db: Session, troupe_id: uuid.UUID) -> None:
    """Forget the troupe's webhooks, as it disconnects its server. They stay on
    Discord, for the server's staff to delete."""
    for row in db.scalars(select(DiscordWebhook).where(DiscordWebhook.troupe_id == troupe_id)):
        db.delete(row)
