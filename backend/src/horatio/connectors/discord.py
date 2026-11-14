"""Discord: downtime results posted by the one Horatio bot, which each troupe
invites to its own server, in a private channel per character; and the troupe's
news, as embeds the bot edits and deletes as the story changes (horatio.posts).

The bot's token, and the app's id and secret, are server configuration
(`HORATIO_DISCORD_*`); no troupe stores a credential. A troupe connects its
server through Discord's bot invite, and Horatio takes the server from the
invite's code exchange, never from the browser, so nobody can attach a server
they could not add the bot to. Storytellers then pick each character's
channel, and a test channel, from the server's text channels.

Messages longer than Discord's 2,000 characters, and embeds longer than
`EMBED_LIMIT`, are split on paragraph boundaries and sent in order. Discord's
rate limits are honoured: a short wait happens here, a longer one is left to the
delivery worker.
"""

import json
import time
import unicodedata
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from horatio.config import get_settings
from horatio.connectors import Connector, Message, Recipient, SendError, register

API = "https://discord.com/api/v10"
AUTHORIZE = "https://discord.com/oauth2/authorize"
LIMIT = 2000
# An embed's text. Discord allows 4,096, and 6,000 across a message's embeds with
# their titles, so this leaves room for the headline and the agency's name.
EMBED_LIMIT = 4000
# What the bot asks for when a server adds it (#839): to see channels and send
# messages there, and, for the troupe's news and announcements, which are embeds
# with their pictures attached, Embed Links and Attach Files. No privileged intents.
ADMINISTRATOR = 1 << 3
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
PERMISSIONS = VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES
# Each of them by the name Discord shows in a channel's settings, in that order.
PERMISSION_NAMES = {
    VIEW_CHANNEL: "View Channels",
    SEND_MESSAGES: "Send Messages",
    EMBED_LINKS: "Embed Links",
    ATTACH_FILES: "Attach Files",
}
# Downtime results are plain text; posts are embeds with pictures.
FOR_RESULTS = VIEW_CHANNEL | SEND_MESSAGES
FOR_POSTS = PERMISSIONS
# Every permission, as the server's owner and an administrator have.
ALL_PERMISSIONS = (1 << 64) - 1
# Discord's error code for a request the bot lacks a permission for.
MISSING_PERMISSIONS = 50013
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


# A `state` for Discord's shared callback that begins with this belongs to a player
# linking their own Discord account (#857), not to a troupe adding the bot.
LINK_STATE = "link."


def link_url(state: str) -> str:
    """Discord's page for a player to link their own Discord account (#857): the
    `identify` scope only, which tells Horatio who they are and nothing else. It
    comes back to the same callback as the bot's invite, told apart by `state`."""
    query = {
        "client_id": get_settings().discord_client_id,
        "scope": "identify",
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "state": f"{LINK_STATE}{state}",
        "prompt": "consent",
    }
    return f"{AUTHORIZE}?{urlencode(query)}"


@dataclass(frozen=True)
class Account:
    """A Discord account, as Discord itself says: its id and username."""

    id: str
    username: str


def account_from_code(code: str) -> Account:
    """The Discord account a player just linked, from the code Discord sent back.
    Raises SendError when Discord will not say."""
    settings = get_settings()
    with httpx.Client(transport=transport, timeout=15) as http:
        try:
            token = http.post(
                f"{API}/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri(),
                },
                auth=(settings.discord_client_id or "", settings.discord_client_secret or ""),
            )
            access = None if token.is_error else token.json().get("access_token")
            if not access:
                raise SendError("Discord did not confirm your account.", retry=False)
            me = http.get(f"{API}/users/@me", headers={"Authorization": f"Bearer {access}"})
        except httpx.TransportError as error:
            raise SendError(f"Could not reach Discord: {error}", retry=True) from error
    if me.is_error or "id" not in me.json():
        raise SendError("Discord did not say which account is yours.", retry=False)
    body = me.json()
    return Account(id=str(body["id"]), username=str(body.get("username") or "").lower())


def bot_invite_url() -> str:
    """Discord's page for adding the bot to a server by hand, asking for the
    permissions Horatio needs. A troupe connects its own server from its Connectors
    tab instead (`invite_url`), so Horatio learns which server is theirs."""
    query = {
        "client_id": get_settings().discord_client_id,
        "scope": "bot",
        "permissions": str(PERMISSIONS),
    }
    return f"{AUTHORIZE}?{urlencode(query)}"


@dataclass(frozen=True)
class Bot:
    """Who Discord says the bot is, and how many servers it is in."""

    id: str
    name: str
    servers: int
    # Discord lists at most 200 servers at once: there may be more.
    more: bool


def whoami() -> Bot:
    """Ask Discord who the bot is, with its token. Raises SendError."""
    me = request("GET", "/users/@me").json()
    guilds = request("GET", "/users/@me/guilds", params={"limit": 200}).json()
    return Bot(
        id=str(me["id"]),
        name=str(me.get("username") or ""),
        servers=len(guilds),
        more=len(guilds) >= 200,
    )


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
                reason = (
                    "The Horatio bot is missing a permission in that channel."
                    if error_code(response) == MISSING_PERMISSIONS
                    else "The Horatio bot cannot see or post in that channel."
                )
                raise SendError(reason, retry=False, status=403)
            if response.status_code == 404:
                raise SendError("That channel or server no longer exists.", retry=False, status=404)
            if response.is_error:
                raise SendError(
                    f"Discord refused the message ({response.status_code}).", retry=False
                )
            return response
        raise SendError("Discord kept asking Horatio to slow down.", retry=True, retry_after=60)


def error_code(response: httpx.Response) -> int | None:
    try:
        return int(response.json()["code"])
    except (ValueError, KeyError, TypeError):
        return None


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
class File:
    """A file sent with a message, such as a picture an embed shows as
    `attachment://<name>`."""

    name: str
    data: bytes
    content_type: str = "image/webp"


def message_request(payload: Mapping[str, Any], files: Sequence[File]) -> dict[str, Any]:
    """What to send for a message with `payload` (its embeds and so on) and `files`:
    JSON, or a form with the files when there are any. The files listed are the
    message's only attachments, so an edit drops any it had before. Nobody is ever
    pinged, whatever the text says."""
    body = {
        **payload,
        "allowed_mentions": {"parse": []},
        "attachments": [{"id": n, "filename": f.name} for n, f in enumerate(files)],
    }
    if not files:
        return {"json": body}
    return {
        "data": {"payload_json": json.dumps(body)},
        "files": {f"files[{n}]": (f.name, f.data, f.content_type) for n, f in enumerate(files)},
    }


def post_message(channel: str, payload: Mapping[str, Any], files: Sequence[File] = ()) -> str:
    """Post one message to a channel; returns its id. Raises SendError, naming the
    permissions the bot lacks there when Discord refuses it for that."""
    try:
        sent = request("POST", f"/channels/{channel}/messages", **message_request(payload, files))
    except SendError as error:
        raise explained(error, channel, FOR_POSTS) from None
    return str(sent.json()["id"])


def edit_message(
    channel: str, message_id: str, payload: Mapping[str, Any], files: Sequence[File] = ()
) -> None:
    """Change a message the bot posted. Raises SendError, with status 404 when the
    message is no longer there."""
    try:
        request(
            "PATCH", f"/channels/{channel}/messages/{message_id}", **message_request(payload, files)
        )
    except SendError as error:
        raise explained(error, channel, FOR_POSTS) from None


def delete_message(channel: str, message_id: str) -> None:
    """Delete a message the bot posted. One already gone is no failure."""
    try:
        request("DELETE", f"/channels/{channel}/messages/{message_id}")
    except SendError as error:
        if error.status != 404:
            raise


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    category: str | None
    # Whether @everyone is kept out, so only roles and people given access see it.
    private: bool
    # Of the permissions Horatio asks for (PERMISSION_NAMES), those the bot lacks
    # in this channel; None when they weren't checked or couldn't be.
    missing: tuple[str, ...] | None = None


def text_channels(guild_id: str, permissions: bool = False) -> list[Channel]:
    """The server's text channels, in Discord's order, with whether each is private,
    and with `permissions`, which of the permissions Horatio needs the bot lacks in
    each. A failure to check them leaves them unchecked rather than failing."""
    found = request("GET", f"/guilds/{guild_id}/channels").json()
    categories = {c["id"]: c["name"] for c in found if c.get("type") == 4}
    access: BotAccess | None = None
    if permissions:
        try:
            access = bot_access(guild_id)
        except SendError:
            access = None

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
            missing=None
            if access is None
            else tuple(
                missing(access.permissions(c.get("permission_overwrites", [])), PERMISSIONS)
            ),
        )
        for c in sorted(found, key=lambda c: (c.get("position", 0), c["id"]))
        if c.get("type") in TEXT_CHANNEL_TYPES
    ]


# --- the bot's permissions in a channel ---------------------------------------------------


def overwrite(permissions: int, rule: Mapping[str, Any] | None) -> int:
    if rule is None:
        return permissions
    return (permissions & ~int(rule.get("deny", 0))) | int(rule.get("allow", 0))


@dataclass(frozen=True)
class BotAccess:
    """What decides the bot's permissions in a server's channels: the server, its
    owner and roles (role id to permissions), and the bot's id and roles."""

    guild_id: str
    owner_id: str
    roles: Mapping[str, int]
    bot_id: str
    bot_roles: Sequence[str]

    def permissions(self, overwrites: Sequence[Mapping[str, Any]]) -> int:
        """The bot's permissions in a channel with these overwrites, as Discord works
        them out: the server's owner and an administrator have every one; otherwise
        @everyone's, then the bot's roles', then the channel's overwrites for
        @everyone, for the bot's roles together, and for the bot itself. Without
        View Channels it has none; without Send Messages, it can't embed or attach."""
        if self.bot_id == self.owner_id:
            return ALL_PERMISSIONS
        base = self.roles.get(self.guild_id, 0)
        for role in self.bot_roles:
            base |= self.roles.get(role, 0)
        if base & ADMINISTRATOR:
            return ALL_PERMISSIONS
        rules = {str(o.get("id")): o for o in overwrites}
        result = overwrite(base, rules.get(self.guild_id))
        allow = deny = 0
        for role in self.bot_roles:
            rule = rules.get(role)
            if rule is not None:
                allow |= int(rule.get("allow", 0))
                deny |= int(rule.get("deny", 0))
        result = (result & ~deny) | allow
        result = overwrite(result, rules.get(self.bot_id))
        if not result & VIEW_CHANNEL:
            return 0
        if not result & SEND_MESSAGES:
            result &= ~(EMBED_LINKS | ATTACH_FILES)
        return result


def bot_access(guild_id: str) -> BotAccess:
    """The bot's place in a server, from Discord: three calls. Raises SendError."""
    try:
        bot_id = str(request("GET", "/users/@me").json()["id"])
        guild = request("GET", f"/guilds/{guild_id}").json()
        member = request("GET", f"/guilds/{guild_id}/members/{bot_id}").json()
        return BotAccess(
            guild_id=guild_id,
            owner_id=str(guild.get("owner_id", "")),
            roles={str(r["id"]): int(r.get("permissions", 0)) for r in guild.get("roles", [])},
            bot_id=bot_id,
            bot_roles=[str(r) for r in member.get("roles", [])],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SendError(
            "Discord's answer about the bot was not as expected.", retry=False
        ) from error


def missing(permissions: int, needs: int) -> list[str]:
    """The names of the permissions in `needs` that `permissions` lacks."""
    return [name for bit, name in PERMISSION_NAMES.items() if needs & bit and not permissions & bit]


def listed(names: Sequence[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def missing_in(channel: str, needs: int) -> list[str] | None:
    """The permissions in `needs` the bot lacks in a channel, or None when Discord
    won't say. Never raises."""
    try:
        found = request("GET", f"/channels/{channel}").json()
        access = bot_access(str(found["guild_id"]))
        return missing(access.permissions(found.get("permission_overwrites") or []), needs)
    except (SendError, KeyError, TypeError, ValueError):
        return None


def explained(error: SendError, channel: str, needs: int) -> SendError:
    """A refusal for want of permission, saying which ones the bot lacks there."""
    if error.status == 403:
        lacking = missing_in(channel, needs)
        if lacking:
            them = "that permission" if len(lacking) == 1 else "those permissions"
            error.reason = (
                f"The Horatio bot needs {listed(lacking)} in that channel. "
                f"Give it {them} in the channel's settings on Discord."
            )
    return error


def plain_name(name: str) -> str:
    """A name as channel names are matched: no accents, case, spaces or punctuation,
    so "Agnes Wren", "#agnes-wren" and "agnes_wren" are all "agneswren"."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if c.isalnum()).casefold()


def first_name(name: str) -> str:
    words = name.split()
    return plain_name(words[0]) if words else ""


def suggested_channels(
    characters: Sequence[tuple[uuid.UUID, str]], channels: Sequence[Channel]
) -> dict[str, str]:
    """A channel for each character that it can be told by name: its full name, or
    its first name where no other character shares it. A private channel comes
    before one everyone can see, then a full name before a first name, then
    Discord's order. A channel that would suit two characters is suggested for
    neither. Character id to channel id; storytellers choose whether to use them."""
    firsts = Counter(first_name(name) for _, name in characters)
    found: dict[str, str] = {}
    for character_id, name in characters:
        full, first = plain_name(name), first_name(name)
        names = {full: 0} if full else {}
        if first and firsts[first] == 1:
            names.setdefault(first, 1)
        matches = [
            (not c.private, names[plain_name(c.name)], n, c.id)
            for n, c in enumerate(channels)
            if plain_name(c.name) in names
        ]
        if matches:
            found[str(character_id)] = min(matches)[3]
    claimed = Counter(found.values())
    return {character: channel for character, channel in found.items() if claimed[channel] == 1}


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
        """The server stays as Horatio connected it; channels must be its text channels.
        The channels for the troupe's posts are chosen apart from these
        (horatio.api.posts), and kept."""
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
            **({"post_channels": current["post_channels"]} if current.get("post_channels") else {}),
        }

    def unreachable(
        self, settings: Mapping[str, Any], character_ids: Iterable[uuid.UUID]
    ) -> set[uuid.UUID]:
        channels = (settings.get("channels") or {}) if settings.get("guild_id") else {}
        return {c for c in character_ids if not channels.get(str(c))}

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
                explained(error, target, FOR_RESULTS)
                if n:
                    error.reason = f"{error.reason} ({n} of {len(parts)} parts were sent.)"
                raise
            ids.append(str(sent.json()["id"]))
        return {"message_ids": ids}


register(DiscordConnector())
