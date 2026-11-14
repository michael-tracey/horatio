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

import base64
import json
import time
import unicodedata
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
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
CREATE_INSTANT_INVITE = 1 << 0
ADMINISTRATOR = 1 << 3
MANAGE_CHANNELS = 1 << 4
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
MANAGE_ROLES = 1 << 28
# To make the channel's Horatio webhook, through which a news story posts as its
# agency (#883, horatio.discord_webhooks).
MANAGE_WEBHOOKS = 1 << 29
# To add emoji to a server, and edit or delete the ones the bot added itself (#870);
# Manage Expressions (1 << 30) would be needed only for anyone else's, which Horatio
# never touches.
CREATE_EXPRESSIONS = 1 << 43
PERMISSIONS = VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | ATTACH_FILES
# What a troupe that lets Horatio make its characters' channels grants the bot as
# well (#855, horatio.discord_channels): Manage Channels to make them, Manage Roles
# to set who sees each, and Read Message History, since the bot may only let a player
# read a channel's history if it may itself. Create Invite is optional.
FOR_MANAGED = PERMISSIONS | MANAGE_CHANNELS | MANAGE_ROLES | READ_MESSAGE_HISTORY
# What a troupe that lets Horatio add the clan and discipline symbols to its server
# as emoji grants the bot as well (#870, horatio.discord_emoji).
FOR_EMOJI = CREATE_EXPRESSIONS
# What the bot needs as well in a channel where a story posts as its agency (#883,
# horatio.discord_webhooks); without it, stories there post as the bot.
FOR_WEBHOOKS = MANAGE_WEBHOOKS
# What each channel's list says the bot lacks: what it needs to post, and Manage
# Webhooks; each place that shows it picks those that matter there.
CHECKED = PERMISSIONS | FOR_WEBHOOKS
# Each of them by the name Discord shows in a server's or channel's settings, in
# that order.
PERMISSION_NAMES = {
    VIEW_CHANNEL: "View Channels",
    SEND_MESSAGES: "Send Messages",
    EMBED_LINKS: "Embed Links",
    ATTACH_FILES: "Attach Files",
    MANAGE_WEBHOOKS: "Manage Webhooks",
    READ_MESSAGE_HISTORY: "Read Message History",
    MANAGE_CHANNELS: "Manage Channels",
    MANAGE_ROLES: "Manage Roles",
    CREATE_INSTANT_INVITE: "Create Invite",
    CREATE_EXPRESSIONS: "Create Expressions",
}
# Downtime results are plain text; posts are embeds with pictures.
FOR_RESULTS = VIEW_CHANNEL | SEND_MESSAGES
FOR_POSTS = PERMISSIONS
# Every permission, as the server's owner and an administrator have.
ALL_PERMISSIONS = (1 << 64) - 1
# Discord's error code for a request the bot lacks a permission for.
MISSING_PERMISSIONS = 50013
# Discord's error codes for a server with as many emoji as it may have (static and
# animated), and for an image too big for an emoji.
MAX_EMOJI = 30008
MAX_ANIMATED_EMOJI = 30018
FILE_TOO_BIG = 50045
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


def client(bot: bool = True) -> httpx.Client:
    """Discord's API, as the bot; or with `bot` False, as nobody, for a webhook's
    own routes, whose token is in the address."""
    headers = {"User-Agent": "DiscordBot (https://github.com/michael-tracey/horatio, 0.1)"}
    if bot:
        headers["Authorization"] = f"Bot {get_settings().discord_bot_token}"
    return httpx.Client(base_url=API, transport=transport, timeout=15, headers=headers)


def request(method: str, path: str, *, bot: bool = True, **kwargs: Any) -> httpx.Response:
    """One call to Discord's API, sitting out short rate limits. Raises SendError,
    saying whether trying again later could help."""
    with client(bot) as http:
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
                raise SendError(
                    "Discord refused Horatio's bot token.",
                    retry=False,
                    status=401,
                    code=error_code(response),
                )
            if response.status_code == 403:
                reason = (
                    "The Horatio bot is missing a permission in that channel."
                    if error_code(response) == MISSING_PERMISSIONS
                    else "The Horatio bot cannot see or post in that channel."
                )
                raise SendError(reason, retry=False, status=403, code=error_code(response))
            if response.status_code == 404:
                raise SendError(
                    "That channel or server no longer exists.",
                    retry=False,
                    status=404,
                    code=error_code(response),
                )
            if response.is_error:
                raise SendError(
                    f"Discord refused the message ({response.status_code}).",
                    retry=False,
                    status=response.status_code,
                    code=error_code(response),
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
    # Of the permissions Horatio checks for (CHECKED), those the bot lacks in this
    # channel; None when they weren't checked or couldn't be.
    missing: tuple[str, ...] | None = None


def guild_channels(guild_id: str) -> list[dict[str, Any]]:
    """Every channel in the server, as Discord gives them. Raises SendError."""
    return list(request("GET", f"/guilds/{guild_id}/channels").json())


def text_channels(
    guild_id: str, permissions: bool = False, access: "BotAccess | None" = None
) -> list[Channel]:
    """The server's text channels, in Discord's order, with whether each is private,
    and with `permissions`, which of the permissions Horatio needs the bot lacks in
    each (from `access`, when the caller has it already). A failure to check them
    leaves them unchecked rather than failing."""
    found = guild_channels(guild_id)
    categories = {c["id"]: c["name"] for c in found if c.get("type") == 4}
    if permissions and access is None:
        try:
            access = bot_access(guild_id)
        except SendError:
            access = None
    elif not permissions:
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
            else tuple(missing(access.permissions(c.get("permission_overwrites", [])), CHECKED)),
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
class Role:
    """One of a server's roles, as staff pick them (#855): never @everyone, nor a
    role a bot or integration manages."""

    id: str
    name: str


@dataclass(frozen=True)
class BotAccess:
    """What decides the bot's permissions in a server's channels: the server, its
    owner and roles (role id to permissions), and the bot's id and roles. With them,
    the server's roles by name and its system channel, for horatio.discord_channels."""

    guild_id: str
    owner_id: str
    roles: Mapping[str, int]
    bot_id: str
    bot_roles: Sequence[str]
    named_roles: Sequence[Role] = field(default_factory=tuple)
    system_channel: str | None = None

    def server_permissions(self) -> int:
        """The bot's permissions across the server, before any channel's overwrites."""
        return self.permissions([])

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
        roles = guild.get("roles", [])
        return BotAccess(
            guild_id=guild_id,
            owner_id=str(guild.get("owner_id", "")),
            roles={str(r["id"]): int(r.get("permissions", 0)) for r in roles},
            bot_id=bot_id,
            bot_roles=[str(r) for r in member.get("roles", [])],
            named_roles=tuple(
                Role(id=str(r["id"]), name=str(r.get("name", "")))
                for r in sorted(roles, key=lambda r: (-int(r.get("position", 0)), str(r["id"])))
                if str(r["id"]) != guild_id and not r.get("managed")
            ),
            system_channel=str(guild["system_channel_id"])
            if guild.get("system_channel_id")
            else None,
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


# --- members and channels, for the channels Horatio makes (#855) -----------------------------


@dataclass(frozen=True)
class Member:
    """Someone in a server: their Discord id and username, the name the server shows
    for them, and their picture."""

    id: str
    username: str
    display_name: str
    avatar: str | None


def member_from(found: Mapping[str, Any]) -> Member:
    user = found.get("user") or {}
    user_id = str(user["id"])
    avatar = user.get("avatar")
    return Member(
        id=user_id,
        username=str(user.get("username") or ""),
        display_name=str(
            found.get("nick") or user.get("global_name") or user.get("username") or ""
        ),
        avatar=f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png?size=64"
        if avatar
        else None,
    )


def find_member(guild_id: str, user_id: str) -> Member | None:
    """The server's member with this Discord id, or None when they aren't in it.
    Needs no privileged intent. Raises SendError."""
    try:
        found = request("GET", f"/guilds/{guild_id}/members/{user_id}").json()
    except SendError as error:
        if error.status == 404:
            return None
        raise
    try:
        return member_from(found)
    except (KeyError, TypeError) as error:
        raise SendError(
            "Discord's answer about a member was not as expected.", retry=False
        ) from error


def member_by_username(guild_id: str, username: str) -> Member | None:
    """The server's member whose Discord username is exactly this one, from Discord's
    member search (which matches the start of usernames and nicknames, and, unlike
    listing every member, needs no privileged intent). Raises SendError."""
    wanted = username.strip().lstrip("@").casefold()
    if not wanted:
        return None
    found = request(
        "GET", f"/guilds/{guild_id}/members/search", params={"query": wanted, "limit": 100}
    ).json()
    for each in found:
        try:
            member = member_from(each)
        except (KeyError, TypeError):
            continue
        if member.username.casefold() == wanted:
            return member
    return None


def create_channel(guild_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
    """Make a channel or category in the server; returns it. Raises SendError."""
    return dict(request("POST", f"/guilds/{guild_id}/channels", json=dict(body)).json())


def rename_channel(channel_id: str, name: str) -> None:
    """Rename a channel (#856). Needs Manage Channels. Raises SendError."""
    request("PATCH", f"/channels/{channel_id}", json={"name": name})


def set_permission(channel_id: str, overwrite_id: str, kind: int, allow: int, deny: int) -> None:
    """Set one role's or member's permission overwrite on a channel (#856), leaving
    the others as they are. Needs Manage Roles. Raises SendError."""
    request(
        "PUT",
        f"/channels/{channel_id}/permissions/{overwrite_id}",
        json={"type": kind, "allow": str(allow), "deny": str(deny)},
    )


def remove_permission(channel_id: str, overwrite_id: str) -> None:
    """Take one role's or member's overwrite off a channel (#856); one already gone
    is fine. Needs Manage Roles. Raises SendError."""
    try:
        request("DELETE", f"/channels/{channel_id}/permissions/{overwrite_id}")
    except SendError as error:
        if error.status != 404:
            raise


def create_invite(channel_id: str, max_age: int = 7 * 24 * 3600) -> str:
    """A single-use invite to the server, through a channel; returns its link.
    Raises SendError."""
    found = request(
        "POST",
        f"/channels/{channel_id}/invites",
        json={"max_age": max_age, "max_uses": 1, "unique": True},
    ).json()
    return f"https://discord.gg/{found['code']}"


# --- emoji, for the clan and discipline symbols Horatio adds to a server (#870) ----------------


@dataclass(frozen=True)
class Emoji:
    """One of a server's (or the bot's own) custom emoji."""

    id: str
    name: str
    animated: bool


@dataclass(frozen=True)
class EmojiRoom:
    """A server's custom emoji and its Server Boost level, which says how many it may
    have."""

    premium_tier: int
    features: Sequence[str]
    emoji: Sequence[Emoji]


def emoji_of(found: Iterable[Mapping[str, Any]]) -> list[Emoji]:
    return [
        Emoji(id=str(e["id"]), name=str(e.get("name") or ""), animated=bool(e.get("animated")))
        for e in found
        if e.get("id")
    ]


def emoji_room(guild_id: str) -> EmojiRoom:
    """The server's emoji and boost level, from Discord: two calls. Raises SendError."""
    try:
        guild = request("GET", f"/guilds/{guild_id}").json()
        listed = request("GET", f"/guilds/{guild_id}/emojis").json()
        return EmojiRoom(
            premium_tier=int(guild.get("premium_tier") or 0),
            features=[str(f) for f in guild.get("features") or []],
            emoji=emoji_of(listed),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SendError(
            "Discord's answer about the server's emoji was not as expected.", retry=False
        ) from error


def image_data(png: bytes) -> str:
    """A PNG as the data URI Discord takes for an emoji's image."""
    return "data:image/png;base64," + base64.b64encode(png).decode()


def create_emoji(guild_id: str, name: str, png: bytes) -> Emoji:
    """Add an emoji to the server. Needs Create Expressions. Raises SendError: a
    server with no room left is `code` MAX_EMOJI."""
    made = request(
        "POST",
        f"/guilds/{guild_id}/emojis",
        json={"name": name, "image": image_data(png)},
        headers={"X-Audit-Log-Reason": "Horatio: the troupe's clan and discipline symbols"},
    ).json()
    return emoji_of([made])[0]


def delete_emoji(guild_id: str, emoji_id: str) -> None:
    """Delete an emoji the bot added; one already gone is fine. Raises SendError."""
    try:
        request("DELETE", f"/guilds/{guild_id}/emojis/{emoji_id}")
    except SendError as error:
        if error.status != 404:
            raise


def app_emoji() -> list[Emoji]:
    """The bot's own emoji (its application's), which only it can use. Raises
    SendError."""
    found = request("GET", f"/applications/{get_settings().discord_client_id}/emojis").json()
    return emoji_of(found.get("items") or [])


def create_app_emoji(name: str, png: bytes) -> Emoji:
    """Add one of the bot's own emoji. Raises SendError."""
    made = request(
        "POST",
        f"/applications/{get_settings().discord_client_id}/emojis",
        json={"name": name, "image": image_data(png)},
    ).json()
    return emoji_of([made])[0]


def channel_slug(name: str) -> str:
    """A name as Discord writes a text channel's: lower case, words joined by dashes,
    no accents or punctuation. "Agnès Wren" is "agnes-wren"."""
    decomposed = unicodedata.normalize("NFKD", name)
    words = "".join(c if c.isalnum() else " " for c in decomposed if not unicodedata.combining(c))
    return "-".join(words.casefold().split())[:90] or "character"


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
        (horatio.api.posts), and kept, as is what Horatio does with the server's
        character channels (horatio.discord_channels)."""
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
            # The In-Character channel too (horatio.in_character).
            **(
                {"in_character_channel": current["in_character_channel"]}
                if current.get("in_character_channel")
                else {}
            ),
            # What Horatio does with the server's character channels (#855) is
            # changed only through horatio.discord_channels.
            **({"managed": current["managed"]} if current.get("managed") else {}),
            # And so is what it does with the server's emoji (#870), through
            # horatio.discord_emoji.
            **({"emoji": current["emoji"]} if current.get("emoji") else {}),
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
