"""Character channels Horatio makes on a troupe's Discord server (#855).

A troupe that switches it on (its Discord settings, `managed`) lets Horatio make
each character's private results channel instead of a storyteller making it by
hand. It is opt-in because the bot then needs more on the server than results
and posts do (horatio.connectors.discord.FOR_MANAGED): Manage Channels to make
channels, Manage Roles to say who sees each one, Read Message History to let the
player read theirs back, and, if the troupe wants Horatio to invite players who
aren't on the server yet, Create Invite.

A channel Horatio makes:

- sits in a "Horatio · Characters" category the bot makes, then "… 2" and so on,
  since Discord allows 50 channels in a category (and 500 in a server);
- is named for its character ("Agnès Wren" is #agnes-wren, then #agnes-wren-2…);
- keeps @everyone out, and lets in the character's player, the Horatio bot, and
  each of the server's roles the troupe lists as its staff roles (`staff_roles`,
  such as @sts);
- becomes the character's results channel at once, as one chosen by hand would,
  and is recorded as Horatio's (`made`), so keeping channels in step later
  (#856) never touches a channel someone made by hand.

The player is found on the server by the Discord account they sign in with
(`users.discord_user_id`), which is certain; or by the Discord username they typed
in Horatio (`users.discord_handle`), which nobody has checked: then a storyteller
confirms the member found is really them (`pending`, then `members`) before the
channel is made. Someone not on the server is sent an invite through the bell,
when the bot may make one. A retired, inactive or dead character's channel is
left as it is: archiving comes later.

What happened to each character is kept (`state`), for staff to read beside it;
asking for every character's channel at once queues them (`queue`) for the
delivery worker, a few each round, waiting when Discord asks it to.

Everything lives in the troupe's Discord connector settings, under `managed`, and
is changed only here; the connector's own Save keeps it (DiscordConnector.
check_settings).
"""

import copy
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.connectors import SendError, discord
from horatio.models import Character, Troupe, TroupeConnector, User
from horatio.notifications import notify

KEY = "managed"
CATEGORY_NAME = "Horatio · Characters"
# Discord's limits: channels in one category, and in one server.
CATEGORY_LIMIT = 50
SERVER_LIMIT = 500
# Who may do what in a character's channel: its player reads it back and may
# answer; the bot posts results there; staff roles read and write.
PLAYER_ALLOW = (
    discord.VIEW_CHANNEL
    | discord.SEND_MESSAGES
    | discord.READ_MESSAGE_HISTORY
    | discord.EMBED_LINKS
    | discord.ATTACH_FILES
)
BOT_ALLOW = PLAYER_ALLOW
STAFF_ALLOW = discord.VIEW_CHANNEL | discord.SEND_MESSAGES | discord.READ_MESSAGE_HISTORY
# Discord's overwrite types.
ROLE, MEMBER = 0, 1
# How many queued characters the worker takes from one troupe each round, and how
# long it waits at least when Discord asks it to slow down.
PER_ROUND = 5
SLOW_DOWN = timedelta(seconds=60)
# An invite is sent again only after this long.
INVITE_AGAIN = timedelta(days=7)

# What a character's state can be, for staff to read beside it.
MADE = "made"
QUEUED = "queued"
CONFIRM = "confirm"
INVITED = "invited"
NOT_ON_SERVER = "not_on_server"
NOT_FOUND = "not_found"
NO_DISCORD = "no_discord"
REJECTED = "rejected"
READY = "ready"
BOT_LACKS = "bot_lacks"
FAILED = "failed"


def now() -> datetime:
    """The current time; tests replace this."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Outcome:
    """What asking for a character's channel came to, in words staff read."""

    status: str
    note: str
    channel: str | None = None


def managed(settings: Mapping[str, Any]) -> dict[str, Any]:
    """The troupe's managed-channel settings, with every part present."""
    found = copy.deepcopy(dict(settings.get(KEY) or {}))
    found.setdefault("on", False)
    for part in ("staff_roles", "categories", "queue"):
        found.setdefault(part, [])
    for part in ("made", "members", "pending", "state", "invited"):
        found.setdefault(part, {})
    found.setdefault("next_at", None)
    found.setdefault("queued_by", None)
    return found


def save(row: TroupeConnector, parts: Mapping[str, Any], **settings: Any) -> None:
    """Store the managed-channel settings (and any other settings given) on the row,
    as a new value so the change is saved."""
    row.settings = {**row.settings, **settings, KEY: dict(parts)}


def locked(db: Session, troupe_id: uuid.UUID) -> TroupeConnector | None:
    """The troupe's Discord connector, locked until the transaction ends, so the
    worker and staff never change its settings at once."""
    return db.scalar(
        select(TroupeConnector)
        .where(TroupeConnector.troupe_id == troupe_id, TroupeConnector.kind == "discord")
        .with_for_update()
    )


def characters(db: Session, troupe_id: uuid.UUID) -> list[Character]:
    """The characters a troupe gives channels to: its active player characters."""
    return list(
        db.scalars(
            select(Character)
            .where(
                Character.home_troupe_id == troupe_id,
                Character.kind == "pc",
                Character.status == "active",
            )
            .order_by(Character.name, Character.id)
        )
    )


def discord_of(parts: Mapping[str, Any], player: User | None) -> tuple[str, str | None]:
    """How Horatio knows the player on Discord, and their Discord id when it does:
    "verified" (they sign in with it), "confirmed" (staff confirmed the member
    their typed username found), "typed" (a username nobody has checked yet), or
    "none"."""
    if player is None:
        return "none", None
    if player.discord_user_id:
        return "verified", player.discord_user_id
    confirmed = parts["members"].get(str(player.id))
    if confirmed:
        return "confirmed", str(confirmed["id"])
    if player.discord_handle:
        return "typed", None
    return "none", None


def set_state(parts: dict[str, Any], character_id: uuid.UUID, outcome: Outcome) -> None:
    parts["state"][str(character_id)] = {
        "status": outcome.status,
        "note": outcome.note,
        "at": now().isoformat(),
    }


# --- making a channel ---------------------------------------------------------------------


def make(db: Session, troupe: Troupe, character: Character, actor: User) -> Outcome:
    """Make the character's channel, or say what stands in the way, and record what
    happened. Commits nothing. Raises SendError when Discord could not be asked and
    asking again later may help (nothing is changed then)."""
    row = locked(db, troupe.id)
    if row is None or not row.settings.get("guild_id"):
        return Outcome(FAILED, "No Discord server is connected.")
    parts = managed(row.settings)
    if not parts["on"]:
        return Outcome(FAILED, "Horatio doesn't make this troupe's channels: switch it on first.")
    channels = dict(row.settings.get("channels") or {})
    if channels.get(str(character.id)):
        outcome = Outcome(MADE, "It has a channel already.", channels[str(character.id)])
        return outcome
    try:
        outcome = attempt(db, row, parts, channels, troupe, character, actor)
    except SendError as error:
        if error.retry:
            raise
        outcome = Outcome(FAILED, error.reason)
    set_state(parts, character.id, outcome)
    save(row, parts, channels=channels)
    return outcome


def attempt(
    db: Session,
    row: TroupeConnector,
    parts: dict[str, Any],
    channels: dict[str, Any],
    troupe: Troupe,
    character: Character,
    actor: User,
) -> Outcome:
    guild = str(row.settings["guild_id"])
    access = discord.bot_access(guild)
    lacks = discord.missing(access.server_permissions(), discord.FOR_MANAGED)
    if lacks:
        return Outcome(
            BOT_LACKS,
            f"The Horatio bot needs {discord.listed(lacks)} on the server "
            "(Server Settings › Roles, on its role).",
        )
    player = db.get(User, character.player_id) if character.player_id else None
    if player is None:
        return Outcome(FAILED, "It has no player to let in.")
    kind, member_id = discord_of(parts, player)
    if kind == "none":
        return Outcome(
            NO_DISCORD,
            "Their player hasn't given Horatio a Discord username, or signed in with Discord.",
        )
    if member_id is None:
        assert player.discord_handle
        found = discord.member_by_username(guild, player.discord_handle)
        if found is None:
            return Outcome(
                NOT_FOUND,
                f"No one on the server has the Discord username @{player.discord_handle}.",
            )
        parts["pending"][str(player.id)] = {
            "id": found.id,
            "username": found.username,
            "display_name": found.display_name,
            "avatar": found.avatar,
            "character_id": str(character.id),
        }
        return Outcome(
            CONFIRM,
            f"@{found.username} on the server has the username their player gave. A "
            "storyteller confirms it's them before Horatio lets them in.",
        )
    member = discord.find_member(guild, member_id)
    if member is None:
        return invite(db, parts, access, guild, troupe, character, player, actor)
    return build(db, row, parts, channels, access, guild, troupe, character, player, member, actor)


def invite(
    db: Session,
    parts: dict[str, Any],
    access: discord.BotAccess,
    guild: str,
    troupe: Troupe,
    character: Character,
    player: User,
    actor: User,
) -> Outcome:
    """Their player isn't on the server: send them an invite through the bell, once
    a week at most, when the bot may make one."""
    sent = parts["invited"].get(str(player.id))
    if sent and now() - datetime.fromisoformat(sent) < INVITE_AGAIN:
        return Outcome(
            INVITED,
            "Their player isn't on the server yet. Horatio has sent them an invite: "
            "make the channel again once they've joined.",
        )
    if not access.server_permissions() & discord.CREATE_INSTANT_INVITE:
        return Outcome(
            NOT_ON_SERVER,
            "Their player isn't on the server. Invite them yourself, or give the Horatio "
            "bot Create Invite and it will.",
        )
    through = invite_channel(access, guild)
    if through is None:
        return Outcome(
            NOT_ON_SERVER,
            "Their player isn't on the server, and the bot has no channel everyone can "
            "see to invite them to. Invite them yourself.",
        )
    link = discord.create_invite(through)
    parts["invited"][str(player.id)] = now().isoformat()
    notify(
        db,
        [player.id],
        "discord.invite",
        f"You're invited to {troupe.name}'s Discord server, where {character.name}'s "
        "results will go. The invite works once, for a week.",
        link,
        troupe_id=troupe.id,
        character_id=character.id,
    )
    audit.record(
        db, actor, "connector.discord_invited", troupe_id=troupe.id, character_id=character.id
    )
    return Outcome(
        INVITED,
        "Their player isn't on the server yet. Horatio sent them an invite: make the "
        "channel again once they've joined.",
    )


def invite_channel(access: discord.BotAccess, guild: str) -> str | None:
    """A channel to invite someone through: the server's system channel, or the
    first everyone can see where the bot may make invites."""
    found = discord.guild_channels(guild)
    by_id = {str(c["id"]): c for c in found}
    order = sorted(
        (c for c in found if c.get("type") in discord.TEXT_CHANNEL_TYPES),
        key=lambda c: (c.get("position", 0), str(c["id"])),
    )
    if access.system_channel and access.system_channel in by_id:
        order.insert(0, by_id[access.system_channel])
    for channel in order:
        overwrites = channel.get("permission_overwrites") or []
        everyone_out = any(
            str(o.get("id")) == guild and int(o.get("deny", 0)) & discord.VIEW_CHANNEL
            for o in overwrites
        )
        if not everyone_out and access.permissions(overwrites) & discord.CREATE_INSTANT_INVITE:
            return str(channel["id"])
    return None


def overwrites(
    guild: str, bot: str, staff_roles: Sequence[str], player: str | None
) -> list[dict[str, Any]]:
    """Who sees a character's channel (or Horatio's category): nobody but the bot,
    the staff roles, and the player."""
    found: list[dict[str, Any]] = [
        {"id": guild, "type": ROLE, "allow": "0", "deny": str(discord.VIEW_CHANNEL)},
        {"id": bot, "type": MEMBER, "allow": str(BOT_ALLOW), "deny": "0"},
    ]
    found += [{"id": r, "type": ROLE, "allow": str(STAFF_ALLOW), "deny": "0"} for r in staff_roles]
    if player is not None:
        found.append({"id": player, "type": MEMBER, "allow": str(PLAYER_ALLOW), "deny": "0"})
    return found


def build(
    db: Session,
    row: TroupeConnector,
    parts: dict[str, Any],
    channels: dict[str, Any],
    access: discord.BotAccess,
    guild: str,
    troupe: Troupe,
    character: Character,
    player: User,
    member: discord.Member,
    actor: User,
) -> Outcome:
    found = discord.guild_channels(guild)
    staff = [r for r in parts["staff_roles"] if r in access.roles and r != guild]
    category = category_for(parts, found, guild, access, staff)
    if category is None or len(found) >= SERVER_LIMIT - 1:
        return Outcome(FAILED, "The server has as many channels as Discord allows (500).")
    taken = {str(c.get("name", "")) for c in found}
    base = discord.channel_slug(character.name)
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}-{n}"
    made = discord.create_channel(
        guild,
        {
            "name": name,
            "type": 0,
            "parent_id": category,
            "topic": f"{character.name}'s downtime results, from Horatio.",
            "permission_overwrites": overwrites(guild, access.bot_id, staff, member.id),
        },
    )
    channel = str(made["id"])
    channels[str(character.id)] = channel
    parts["made"][str(character.id)] = channel
    parts["pending"].pop(str(player.id), None)
    parts["invited"].pop(str(player.id), None)
    audit.record(
        db,
        actor,
        "connector.discord_channel_made",
        troupe_id=troupe.id,
        character_id=character.id,
        channel=name,
    )
    notify(
        db,
        [player.id],
        "discord.channel_ready",
        f"Your Discord channel #{name} is ready: {character.name}'s results go there now.",
        f"https://discord.com/channels/{guild}/{channel}",
        troupe_id=troupe.id,
        character_id=character.id,
    )
    return Outcome(MADE, f"Made #{name}.", channel)


def category_for(
    parts: dict[str, Any],
    found: Sequence[Mapping[str, Any]],
    guild: str,
    access: discord.BotAccess,
    staff: Sequence[str],
) -> str | None:
    """Horatio's category with room for another channel, made when none has.
    None when the server can take no more."""
    existing = {str(c["id"]) for c in found if c.get("type") == 4}
    parts["categories"] = [c for c in parts["categories"] if c in existing]
    children = Counter(str(c.get("parent_id") or "") for c in found)
    for category in parts["categories"]:
        if children[category] < CATEGORY_LIMIT:
            return category
    if len(found) >= SERVER_LIMIT - 1:
        return None
    count = len(parts["categories"])
    made = discord.create_channel(
        guild,
        {
            "name": CATEGORY_NAME if not count else f"{CATEGORY_NAME} {count + 1}",
            "type": 4,
            "permission_overwrites": overwrites(guild, access.bot_id, staff, None),
        },
    )
    parts["categories"].append(str(made["id"]))
    return str(made["id"])


# --- confirming a typed username ------------------------------------------------------------


def confirm(
    db: Session, troupe: Troupe, character: Character, actor: User, its_them: bool
) -> Outcome:
    """A storyteller says whether the member a typed username found is really the
    character's player. Yes makes the channel; no forgets the match. Raises
    LookupError when nothing waits to be confirmed, and SendError as `make`."""
    row = locked(db, troupe.id)
    parts = managed(row.settings) if row is not None else managed({})
    player_id = str(character.player_id) if character.player_id else ""
    match = parts["pending"].get(player_id)
    if row is None or match is None:
        raise LookupError("Nothing is waiting to be confirmed for this character.")
    parts["pending"].pop(player_id)
    if not its_them:
        outcome = Outcome(
            REJECTED,
            f"A storyteller said @{match['username']} isn't their player. Check the "
            "Discord username their player gave Horatio.",
        )
        audit.record(
            db,
            actor,
            "connector.discord_match_rejected",
            troupe_id=troupe.id,
            character_id=character.id,
            username=match["username"],
        )
        set_state(parts, character.id, outcome)
        save(row, parts)
        return outcome
    parts["members"][player_id] = {
        "id": match["id"],
        "username": match["username"],
        "by": str(actor.id),
        "at": now().isoformat(),
    }
    audit.record(
        db,
        actor,
        "connector.discord_match_confirmed",
        troupe_id=troupe.id,
        character_id=character.id,
        username=match["username"],
    )
    save(row, parts)
    return make(db, troupe, character, actor)


# --- every character at once, through the worker --------------------------------------------


def queue_all(db: Session, troupe: Troupe, actor: User) -> int:
    """Queue every character without a channel for the worker. Returns how many."""
    row = locked(db, troupe.id)
    if row is None:
        return 0
    parts = managed(row.settings)
    channels = row.settings.get("channels") or {}
    added = 0
    for character in characters(db, troupe.id):
        key = str(character.id)
        if channels.get(key) or key in parts["queue"]:
            continue
        parts["queue"].append(key)
        set_state(parts, character.id, Outcome(QUEUED, "Waiting for Horatio to make it."))
        added += 1
    parts["queued_by"] = str(actor.id)
    parts["next_at"] = None
    save(row, parts)
    if added:
        audit.record(
            db, actor, "connector.discord_channels_queued", troupe_id=troupe.id, count=added
        )
    return added


def due(settings: Mapping[str, Any], at: datetime) -> bool:
    parts = settings.get(KEY) or {}
    if not parts.get("queue"):
        return False
    waiting = parts.get("next_at")
    return not waiting or datetime.fromisoformat(waiting) <= at


def make_due(db: Session, at: datetime | None = None) -> int:
    """Make some of the queued channels, `PER_ROUND` a troupe, each in its own
    transaction. Discord asking Horatio to slow down stops that troupe's round and
    waits. Returns how many characters were tried."""
    at = at or now()
    tried = 0
    ids = [
        row.id
        for row in db.scalars(select(TroupeConnector).where(TroupeConnector.kind == "discord"))
        if due(row.settings, at)
    ]
    for row_id in ids:
        for _ in range(PER_ROUND):
            row = db.scalar(
                select(TroupeConnector).where(TroupeConnector.id == row_id).with_for_update()
            )
            if row is None or not due(row.settings, at):
                break
            parts = managed(row.settings)
            key = parts["queue"][0]
            troupe = db.get(Troupe, row.troupe_id)
            actor = db.get(User, uuid.UUID(parts["queued_by"])) if parts["queued_by"] else None
            character = db.get(Character, uuid.UUID(key))
            if (
                troupe is None
                or actor is None
                or character is None
                or character.home_troupe_id != troupe.id
                or not parts["on"]
            ):
                parts["queue"].pop(0)
                if character is not None and not parts["on"]:
                    set_state(
                        parts, character.id, Outcome(FAILED, "Managed channels were switched off.")
                    )
                save(row, parts)
                db.commit()
                continue
            try:
                make(db, troupe, character, actor)
            except SendError as error:
                db.rollback()
                row = db.scalar(
                    select(TroupeConnector).where(TroupeConnector.id == row_id).with_for_update()
                )
                assert row is not None
                parts = managed(row.settings)
                wait = max(SLOW_DOWN, timedelta(seconds=error.retry_after or 0))
                parts["next_at"] = (at + wait).isoformat()
                set_state(parts, character.id, Outcome(QUEUED, f"Waiting: {error.reason}"))
                save(row, parts)
                db.commit()
                tried += 1
                break
            row = locked(db, troupe.id)
            assert row is not None
            parts = managed(row.settings)
            if key in parts["queue"]:
                parts["queue"].remove(key)
            save(row, parts)
            db.commit()
            tried += 1
    return tried


def make_due_now() -> int:
    """`make_due` in a session of its own, for the delivery worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        return make_due(db)


# --- for #857: a player links their Discord account -----------------------------------------


def linked(db: Session, user: User) -> int:
    """Call when `user` has just linked (verified) their Discord account (#857): any
    match a storyteller was still to confirm for them, or had confirmed, gives way
    to the verified account, and their characters' channels can be made at once.
    Returns how many troupes this touched; commits nothing."""
    touched = 0
    key = str(user.id)
    for row in db.scalars(
        select(TroupeConnector).where(TroupeConnector.kind == "discord").with_for_update()
    ):
        parts = managed(row.settings)
        if key not in parts["pending"] and key not in parts["members"]:
            continue
        parts["pending"].pop(key, None)
        parts["members"].pop(key, None)
        for character in characters(db, row.troupe_id):
            state = parts["state"].get(str(character.id)) or {}
            if character.player_id == user.id and state.get("status") in (
                CONFIRM,
                NOT_FOUND,
                NO_DISCORD,
                REJECTED,
            ):
                set_state(
                    parts,
                    character.id,
                    Outcome(READY, "Their player linked their Discord account: make the channel."),
                )
        save(row, parts)
        touched += 1
    return touched
