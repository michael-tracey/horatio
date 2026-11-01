"""Discord: downtime results posted by the one Horatio bot, which each troupe
invites to its own server, in a private channel per character.

The bot's token, and the app's id and secret, are server configuration
(`HORATIO_DISCORD_*`); no troupe stores a credential. A troupe connects its
server through Discord's bot invite, and Horatio takes the server from the
invite's code exchange, never from the browser, so nobody can attach a server
they could not add the bot to. Storytellers then pick each character's
channel, and a test channel, from the server's text channels.

Messages longer than Discord's 2,000 characters are split on paragraph
boundaries and sent in order. Discord's rate limits are honoured: a short wait
happens here, a longer one is left to the delivery worker.
"""

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from horatio.config import get_settings
from horatio.connectors import Connector, Message, Recipient, SendError, register

API = "https://discord.com/api/v10"
AUTHORIZE = "https://discord.com/oauth2/authorize"
LIMIT = 2000
# The bot needs only to see channels and send messages there: VIEW_CHANNEL (1 << 10)
# and SEND_MESSAGES (1 << 11). No privileged intents.
VIEW_CHANNEL = 1 << 10
PERMISSIONS = VIEW_CHANNEL | (1 << 11)
# Text and announcement channels.
TEXT_CHANNEL_TYPES = (0, 5)
# A wait Discord asks for that is short enough to sit out here, in seconds.
SHORT_WAIT = 5.0
SHORT_WAITS = 3

# Tests swap these for a fake Discord and a clock that does not wait.
transport: httpx.BaseTransport | None = None
sleep: Callable[[float], None] = time.sleep


def configured() -> bool:
    settings = get_settings()
    return bool(
        settings.discord_client_id and settings.discord_client_secret and settings.discord_bot_token
    )


def redirect_uri() -> str:
    """Where Discord sends a storyteller back after adding the bot. It must be
    listed among the app's redirects in Discord's developer portal."""
    return f"{get_settings().public_url.rstrip('/')}/api/discord/callback"


def invite_url(state: str) -> str:
    """Discord's page for adding the Horatio bot to a server."""
    query = {
        "client_id": get_settings().discord_client_id,
        "scope": "bot",
        "permissions": str(PERMISSIONS),
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "state": state,
    }
    return f"{AUTHORIZE}?{urlencode(query)}"


def client() -> httpx.Client:
    return httpx.Client(
        base_url=API,
        transport=transport,
        timeout=15,
        headers={
            "Authorization": f"Bot {get_settings().discord_bot_token}",
            "User-Agent": "DiscordBot (https://github.com/michael-tracey/horatio, 0.1)",
        },
    )


def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    """One call to Discord's API, sitting out short rate limits. Raises SendError,
    saying whether trying again later could help."""
    with client() as http:
        for _ in range(SHORT_WAITS + 1):
            try:
                response = http.request(method, path, **kwargs)
            except httpx.TransportError as error:
                raise SendError(f"Could not reach Discord: {error}", retry=True) from error
            if response.status_code == 429:
                wait = rate_limit_wait(response)
                if wait <= SHORT_WAIT:
                    sleep(wait)
                    continue
                raise SendError("Discord asked Horatio to slow down.", retry=True, retry_after=wait)
            if response.status_code >= 500:
                raise SendError(f"Discord is having trouble ({response.status_code}).", retry=True)
            if response.status_code == 401:
                raise SendError("Discord refused Horatio's bot token.", retry=False)
            if response.status_code == 403:
                raise SendError("The Horatio bot cannot see or post in that channel.", retry=False)
            if response.status_code == 404:
                raise SendError("That channel or server no longer exists.", retry=False)
            if response.is_error:
                raise SendError(
                    f"Discord refused the message ({response.status_code}).", retry=False
                )
            return response
        raise SendError("Discord kept asking Horatio to slow down.", retry=True, retry_after=60)


def rate_limit_wait(response: httpx.Response) -> float:
    try:
        return float(response.json()["retry_after"])
    except (ValueError, KeyError, TypeError):
        return float(response.headers.get("Retry-After", 60))


def split(text: str, limit: int = LIMIT) -> list[str]:
    """Parts of at most `limit` characters, broken between paragraphs where
    possible, then between lines, and only then mid-line."""
    parts: list[str] = []
    current = ""
    for block in pieces(text, limit):
        joined = f"{current}\n\n{block}" if current else block
        if len(joined) <= limit:
            current = joined
        else:
            parts.append(current)
            current = block
    if current:
        parts.append(current)
    return parts


def pieces(text: str, limit: int) -> list[str]:
    """Paragraphs, each cut into lines or lengths that fit within `limit`."""
    found: list[str] = []
    for paragraph in text.split("\n\n"):
        if len(paragraph) <= limit:
            found.append(paragraph)
            continue
        line_part = ""
        for line in paragraph.split("\n"):
            while len(line) > limit:
                if line_part:
                    found.append(line_part)
                    line_part = ""
                found.append(line[:limit])
                line = line[limit:]
            joined = f"{line_part}\n{line}" if line_part else line
            if len(joined) <= limit:
                line_part = joined
            else:
                found.append(line_part)
                line_part = line
        if line_part:
            found.append(line_part)
    return found


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    category: str | None
    # Whether @everyone is kept out, so only roles and people given access see it.
    private: bool


def text_channels(guild_id: str) -> list[Channel]:
    """The server's text channels, in Discord's order, with whether each is private."""
    found = request("GET", f"/guilds/{guild_id}/channels").json()
    categories = {c["id"]: c["name"] for c in found if c.get("type") == 4}

    def private(channel: Mapping[str, Any]) -> bool:
        return any(
            o["id"] == guild_id and int(o.get("deny", 0)) & VIEW_CHANNEL
            for o in channel.get("permission_overwrites", [])
        )

    return [
        Channel(
            id=c["id"],
            name=c["name"],
            category=categories.get(c.get("parent_id") or ""),
            private=private(c),
        )
        for c in sorted(found, key=lambda c: (c.get("position", 0), c["id"]))
        if c.get("type") in TEXT_CHANNEL_TYPES
    ]


def exchange_code(code: str) -> tuple[str, str]:
    """The server a storyteller just added the bot to, as (id, name), from the
    invite's code. Raises SendError when Discord will not say."""
    settings = get_settings()
    with httpx.Client(transport=transport, timeout=15) as http:
        try:
            response = http.post(
                f"{API}/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri(),
                },
                auth=(settings.discord_client_id or "", settings.discord_client_secret or ""),
            )
        except httpx.TransportError as error:
            raise SendError(f"Could not reach Discord: {error}", retry=True) from error
    if response.is_error or "guild" not in response.json():
        raise SendError("Discord did not confirm which server the bot was added to.", retry=False)
    guild = response.json()["guild"]
    return str(guild["id"]), str(guild["name"])


def snowflake(value: Any, what: str) -> str:
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError(f"{what} is not a Discord channel.")
    return text


class DiscordConnector(Connector):
    kind = "discord"
    name = "Discord"

    needs = (
        "HORATIO_DISCORD_CLIENT_ID",
        "HORATIO_DISCORD_CLIENT_SECRET",
        "HORATIO_DISCORD_BOT_TOKEN",
    )

    def unavailable(self) -> str | None:
        if configured():
            return None
        return "Discord isn't set up on this server yet."

    def check_settings(
        self, settings: Mapping[str, Any], current: Mapping[str, Any]
    ) -> dict[str, Any]:
        """The server stays as Horatio connected it; channels must be its text channels."""
        guild_id = current.get("guild_id")
        channels = {
            str(uuid.UUID(str(character))): snowflake(channel, "A character's channel")
            for character, channel in (settings.get("channels") or {}).items()
            if channel
        }
        test_channel = settings.get("test_channel") or None
        if test_channel is not None:
            test_channel = snowflake(test_channel, "The test channel")
        if (channels or test_channel) and not guild_id:
            raise ValueError("Connect a Discord server before choosing channels.")
        if guild_id and (channels or test_channel):
            try:
                known = {c.id for c in text_channels(guild_id)}
            except SendError as error:
                raise ValueError(f"Could not check the channels: {error.reason}") from error
            if any(c not in known for c in [*channels.values(), test_channel] if c):
                raise ValueError("Pick channels from the connected server's text channels.")
        return {
            "guild_id": guild_id,
            "guild_name": current.get("guild_name"),
            "channels": channels,
            "test_channel": test_channel,
        }

    def target(self, settings: Mapping[str, Any], recipient: Recipient, test_mode: bool) -> str:
        if not settings.get("guild_id"):
            raise SendError("No Discord server is connected.", retry=False)
        if test_mode:
            if not settings.get("test_channel"):
                raise SendError("No Discord test channel is chosen.", retry=False)
            return settings["test_channel"]
        channel = (settings.get("channels") or {}).get(str(recipient.character_id))
        if not channel:
            raise SendError(f"{recipient.character_name} has no Discord channel.", retry=False)
        return channel

    def send(self, settings: Mapping[str, Any], target: str, message: Message) -> dict[str, Any]:
        parts = split(message.text)
        ids: list[str] = []
        for n, part in enumerate(parts):
            try:
                sent = request(
                    "POST",
                    f"/channels/{target}/messages",
                    # Never ping anyone, whatever the text says.
                    json={"content": part, "allowed_mentions": {"parse": []}},
                )
            except SendError as error:
                if n:
                    error.reason = f"{error.reason} ({n} of {len(parts)} parts were sent.)"
                raise
            ids.append(str(sent.json()["id"]))
        return {"message_ids": ids}


register(DiscordConnector())
