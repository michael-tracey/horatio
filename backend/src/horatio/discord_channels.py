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

Horatio keeps the channels it made in step with the troupe (#856), and never
touches one made by hand:

- a character renamed has its channel renamed;
- a character given to another player lets the new player in and the old one out
  (a new player known only by a typed username waits for a storyteller, as above);
- a character that leaves the troupe, or whose player does, takes its player out;
- a change to the staff roles lets the new roles into every channel and the old
  ones out;
- a retired, inactive or dead character's channel is left as it is.

Those changes are queued (`sync`) where they happen (horatio.renames,
horatio.character_moves, horatio.reconciliation, the staff roles, a player linking
their Discord account) and made by the delivery worker, waiting when Discord asks
it to. Horatio changes only what it set itself (`given`): an overwrite someone added
by hand on Discord stays, and so does a name changed by hand until the character's
own name changes.

Once a day, or when staff ask, Horatio checks each of its channels against what it
set (`problems`): one deleted, renamed or opened up by hand, the bot or a role or
the player no longer let in, a player who left the server, or a character now
using another channel. Each problem gets a fix where Horatio has one ("Make it
again", "Fix", "Send an invite", "Link it again"), and the troupe's staff hear of
each new one once through the bell, not every day. A check also queues whatever
Horatio should have changed and didn't (a player whose characters moved when two
accounts were merged, say), so nothing waits for the next change to come right.

Everything lives in the troupe's Discord connector settings, under `managed`, and
is changed only here; the connector's own Save keeps it (DiscordConnector.
check_settings).
"""

import copy
import re
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
from horatio.notifications import notify, staff_for
from horatio.permissions import TroupeAction

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
    for part in ("staff_roles", "categories", "queue", "sync"):
        found.setdefault(part, [])
    for part in ("made", "members", "pending", "state", "invited", "given", "problems"):
        found.setdefault(part, {})
    found.setdefault("next_at", None)
    found.setdefault("queued_by", None)
    found.setdefault("checked_at", None)
    found.setdefault("check_asked", False)
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
        return typed_match(parts, guild, player, character)
    member = discord.find_member(guild, member_id)
    if member is None:
        return invite(db, parts, access, guild, troupe, character, player, actor)
    return build(db, row, parts, channels, access, guild, troupe, character, player, member, actor)


def typed_match(parts: dict[str, Any], guild: str, player: User, character: Character) -> Outcome:
    """Find the member a player's typed Discord username names, for a storyteller to
    confirm is them. Raises SendError."""
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
    parts["given"][str(character.id)] = {"slug": base, "player": member.id, "roles": staff}
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
    key = str(character.id)
    made = parts["made"].get(key)
    if made and (row.settings.get("channels") or {}).get(key) == made:
        # Its channel is Horatio's already (a new player, #856): let them in.
        queue_sync(parts, key)
        outcome = Outcome(MADE, "Confirmed: Horatio lets them into its channel shortly.", made)
        set_state(parts, character.id, outcome)
        save(row, parts)
        return outcome
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
            if character.player_id == user.id and str(character.id) in parts["made"]:
                # Its channel lets in the account they linked, not the one matched (#856).
                queue_sync(parts, str(character.id))
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


# --- keeping channels in step (#856) ------------------------------------------------------

# What a check can find wrong with one of Horatio's channels, and how Horatio can put
# each right.
DELETED, NAME, ACCESS, BOT, ABSENT, UNLINKED, SERVER = (
    "deleted",
    "name",
    "access",
    "bot",
    "absent",
    "unlinked",
    "server",
)
FIX, REMAKE, INVITE, RELINK = "fix", "remake", "invite", "relink"
# How often Horatio checks its channels unasked.
CHECK_EVERY = timedelta(days=1)
# Every channel Horatio made, in the queue of channels to bring into step.
EVERY = "*"


@dataclass(frozen=True)
class Want:
    """What one of Horatio's channels should be now: named for its character (a
    slug, numbered when the name is taken), letting in its player (their Discord id;
    None when nobody is to be let in) and the troupe's staff roles."""

    slug: str
    player: str | None
    roles: tuple[str, ...]


def queue_sync(parts: dict[str, Any], key: str) -> None:
    if key not in parts["sync"] and EVERY not in parts["sync"]:
        parts["sync"].append(key)


def changed(db: Session, character: Character) -> int:
    """Call when a character Horatio may have made a channel for is renamed, given to
    another player, or leaves a troupe: queue its channel to be brought into step.
    Returns how many troupes' channels were queued; commits nothing."""
    key = str(character.id)
    queued = 0
    for row in db.scalars(
        select(TroupeConnector)
        .where(TroupeConnector.kind == "discord")
        .order_by(TroupeConnector.id)
        .with_for_update()
    ):
        parts = managed(row.settings)
        if key not in parts["made"]:
            continue
        queue_sync(parts, key)
        save(row, parts)
        queued += 1
    return queued


def staff_roles_changed(parts: dict[str, Any]) -> None:
    """Every channel Horatio made lets the new staff roles in and the old ones out."""
    if parts["made"]:
        parts["sync"] = [EVERY]


def slug_of(name: str) -> str:
    """A channel's name without the number Horatio adds when a name is taken."""
    return re.sub(r"-\d+$", "", name)


def fits(name: str, slug: str) -> bool:
    """Whether a channel's name is this slug, or this slug numbered."""
    return re.fullmatch(rf"{re.escape(slug)}(-\d+)?", name) is not None


def rules_of(channel: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(o.get("id")): o for o in channel.get("permission_overwrites") or []}


def allows(rule: Mapping[str, Any] | None, needs: int) -> bool:
    return (
        rule is not None
        and int(rule.get("allow", 0)) & needs == needs
        and not int(rule.get("deny", 0)) & needs
    )


def given_for(
    parts: Mapping[str, Any], key: str, channel: Mapping[str, Any] | None, access: discord.BotAccess
) -> dict[str, Any]:
    """What Horatio last set on a channel it made: recorded since #856, or read from
    the channel itself for one made before."""
    found = parts["given"].get(key)
    if found is not None:
        return {
            "slug": found.get("slug") or "",
            "player": found.get("player"),
            "roles": [str(r) for r in found.get("roles") or []],
        }
    channel = channel or {}
    rules = list(channel.get("permission_overwrites") or [])
    return {
        "slug": slug_of(str(channel.get("name", ""))),
        "player": next(
            (
                str(o["id"])
                for o in rules
                if int(o.get("type", 0)) == MEMBER
                and str(o["id"]) != access.bot_id
                and allows(o, discord.VIEW_CHANNEL)
            ),
            None,
        ),
        "roles": [
            str(o["id"])
            for o in rules
            if int(o.get("type", 0)) == ROLE
            and str(o["id"]) != access.guild_id
            and allows(o, STAFF_ALLOW)
        ],
    }


def want_for(
    db: Session,
    row: TroupeConnector,
    parts: Mapping[str, Any],
    character: Character | None,
    access: discord.BotAccess,
) -> Want | None:
    """What a channel Horatio made should be now, or None when it is to be left as
    it is: its character retired, inactive, dead or gone (archiving comes later)."""
    if character is None or character.kind != "pc" or character.status != "active":
        return None
    roles = tuple(r for r in parts["staff_roles"] if r in access.roles and r != access.guild_id)
    player_id: str | None = None
    if character.home_troupe_id == row.troupe_id and character.player_id:
        _, player_id = discord_of(parts, db.get(User, character.player_id))
    return Want(discord.channel_slug(character.name), player_id, roles)


def unique_name(slug: str, taken: set[str]) -> str:
    name, n = slug, 1
    while name in taken:
        n += 1
        name = f"{slug}-{n}"
    return name


def role_names(access: discord.BotAccess) -> dict[str, str]:
    return {r.id: r.name for r in access.named_roles}


def apply(
    db: Session,
    row: TroupeConnector,
    parts: dict[str, Any],
    character: Character,
    channel: Mapping[str, Any],
    found: Sequence[Mapping[str, Any]],
    access: discord.BotAccess,
    want: Want,
    full: bool,
) -> list[str]:
    """Bring one of Horatio's channels into step: what changed since Horatio last set
    it, or with `full`, everything Horatio sets, as when staff click Fix. Returns
    what was changed, in words. Raises SendError."""
    key = str(character.id)
    guild = access.guild_id
    channel_id = str(channel["id"])
    given = given_for(parts, key, channel, access)
    rules = rules_of(channel)
    names = role_names(access)
    done: list[str] = []

    name = str(channel.get("name", ""))
    if not fits(name, want.slug) and (full or want.slug != given["slug"]):
        taken = {str(c.get("name", "")) for c in found if str(c.get("id")) != channel_id}
        new = unique_name(want.slug, taken)
        discord.rename_channel(channel_id, new)
        done.append(f"renamed #{name} to #{new}")
        name = new

    if full:
        everyone = rules.get(guild)
        if everyone is None or not int(everyone.get("deny", 0)) & discord.VIEW_CHANNEL:
            allow = int((everyone or {}).get("allow", 0)) & ~discord.VIEW_CHANNEL
            deny = int((everyone or {}).get("deny", 0)) | discord.VIEW_CHANNEL
            discord.set_permission(channel_id, guild, ROLE, allow, deny)
            done.append("kept everyone else out")
        if not allows(rules.get(access.bot_id), BOT_ALLOW):
            discord.set_permission(channel_id, access.bot_id, MEMBER, BOT_ALLOW, 0)
            done.append("let the Horatio bot in")

    for role in given["roles"]:
        if role not in want.roles and role in rules:
            discord.remove_permission(channel_id, role)
            done.append(f"took @{names.get(role, 'a role')} out")
    for role in want.roles:
        if not allows(rules.get(role), STAFF_ALLOW) and (full or role not in given["roles"]):
            discord.set_permission(channel_id, role, ROLE, STAFF_ALLOW, 0)
            done.append(f"let @{names.get(role, 'a role')} in")

    old, new = given["player"], want.player
    placed = new
    if old and old != new and old in rules:
        discord.remove_permission(channel_id, old)
        done.append("took its former player out")
    if new and not allows(rules.get(new), PLAYER_ALLOW) and (full or new != old):
        if discord.find_member(guild, new) is None:
            placed = None
            flag(
                db,
                row,
                parts,
                character,
                ABSENT,
                "Its player isn't on the server, so Horatio can't let them in.",
                INVITE if access.server_permissions() & discord.CREATE_INSTANT_INVITE else None,
            )
        else:
            discord.set_permission(channel_id, new, MEMBER, PLAYER_ALLOW, 0)
            done.append("let its player in")
            if new != old and character.player_id:
                notify(
                    db,
                    [character.player_id],
                    "discord.channel_ready",
                    f"Your Discord channel #{name} is ready: {character.name}'s results go "
                    "there now.",
                    f"https://discord.com/channels/{guild}/{channel_id}",
                    troupe_id=row.troupe_id,
                    character_id=character.id,
                )
    parts["given"][key] = {"slug": want.slug, "player": placed, "roles": list(want.roles)}
    return done


def flag(
    db: Session,
    row: TroupeConnector,
    parts: dict[str, Any],
    character: Character | None,
    kind: str,
    note: str,
    fix: str | None,
    key: str | None = None,
) -> bool:
    """Record a problem with one of Horatio's channels. The first time it's found,
    the troupe's staff hear of it through the bell; never again while it lasts.
    Returns whether it is new."""
    key = key or str(character.id if character else "")
    problem = f"{key}:{kind}"
    if problem in parts["problems"]:
        parts["problems"][problem].update(note=note, fix=fix)
        return False
    parts["problems"][problem] = {
        "character_id": key,
        "name": character.name if character else None,
        "kind": kind,
        "note": note,
        "fix": fix,
        "since": now().isoformat(),
    }
    troupe = db.get(Troupe, row.troupe_id)
    if troupe is not None:
        about = f"{character.name}'s Discord channel" if character else "Discord channels"
        notify(
            db,
            staff_for(db, troupe, TroupeAction.MANAGE_CONNECTORS),
            "discord.channel_problem",
            f"{about}: {note}",
            f"/troupes/{troupe.id}/connectors",
            troupe_id=troupe.id,
            character_id=character.id if character else None,
        )
    return True


def settle(parts: dict[str, Any], key: str, kinds: Sequence[str] | None = None) -> None:
    """Forget a character's problems (of these kinds), once they are put right."""
    for problem in list(parts["problems"]):
        found = parts["problems"][problem]
        if found.get("character_id") == key and (kinds is None or found.get("kind") in kinds):
            del parts["problems"][problem]


def sync_one(
    db: Session,
    row: TroupeConnector,
    parts: dict[str, Any],
    key: str,
    found: Sequence[Mapping[str, Any]],
    access: discord.BotAccess,
) -> None:
    """Bring one of Horatio's channels into step with its character, as the worker
    does after a change. Raises SendError."""
    channel_id = parts["made"].get(key)
    if channel_id is None:
        return
    character = db.get(Character, uuid.UUID(key))
    want = want_for(db, row, parts, character, access)
    if want is None:
        return
    assert character is not None
    channel = next((c for c in found if str(c.get("id")) == channel_id), None)
    if channel is None:
        flag(
            db,
            row,
            parts,
            character,
            DELETED,
            "Its channel was deleted on Discord.",
            REMAKE if character.home_troupe_id == row.troupe_id else None,
        )
        return
    done = apply(db, row, parts, character, channel, found, access, want, full=False)
    if done:
        settle(parts, key, (NAME, ACCESS))
        audit.record(
            db,
            None,
            "connector.discord_channel_kept",
            troupe_id=row.troupe_id,
            character_id=character.id,
            changes="; ".join(done),
        )
    # A new player known only by a typed username waits for a storyteller.
    if want.player is None and character.home_troupe_id == row.troupe_id and character.player_id:
        player = db.get(User, character.player_id)
        kind, _ = discord_of(parts, player)
        if kind == "typed" and player is not None and str(player.id) not in parts["pending"]:
            set_state(parts, character.id, typed_match(parts, access.guild_id, player, character))


def expand(parts: dict[str, Any]) -> None:
    """Turn "every channel" in the queue into each channel Horatio made."""
    if EVERY in parts["sync"]:
        rest = [k for k in parts["sync"] if k != EVERY]
        parts["sync"] = list(dict.fromkeys([*parts["made"], *rest]))


def waiting(parts: Mapping[str, Any], at: datetime) -> bool:
    found = parts.get("next_at")
    return bool(found) and datetime.fromisoformat(found) > at


def server_of(
    db: Session, row: TroupeConnector, parts: dict[str, Any], at: datetime
) -> tuple[discord.BotAccess, list[dict[str, Any]]] | None:
    """The bot's place in the troupe's server and its channels, or None when Discord
    won't say: then the troupe waits (when asking again may help) or its staff hear
    why (when it won't)."""
    guild = str(row.settings.get("guild_id") or "")
    try:
        return discord.bot_access(guild), discord.guild_channels(guild)
    except SendError as error:
        if error.retry:
            wait = max(SLOW_DOWN, timedelta(seconds=error.retry_after or 0))
            parts["next_at"] = (at + wait).isoformat()
        else:
            flag(db, row, parts, None, SERVER, error.reason, None, key="server")
            parts["sync"] = []
            parts["check_asked"] = False
            parts["checked_at"] = at.isoformat()
        return None


def sync_due(db: Session, at: datetime | None = None) -> int:
    """Bring queued channels into step, `PER_ROUND` a troupe each round, each in its
    own transaction, waiting when Discord asks Horatio to. Returns how many."""
    at = at or now()
    done = 0
    ids = [
        row.id
        for row in db.scalars(
            select(TroupeConnector)
            .where(TroupeConnector.kind == "discord")
            .order_by(TroupeConnector.id)
        )
        if (row.settings.get(KEY) or {}).get("sync")
        and (row.settings.get(KEY) or {}).get("on")
        and not waiting(row.settings.get(KEY) or {}, at)
    ]
    for row_id in ids:
        row = db.scalar(
            select(TroupeConnector).where(TroupeConnector.id == row_id).with_for_update()
        )
        if row is None:
            continue
        parts = managed(row.settings)
        server = server_of(db, row, parts, at)
        save(row, parts)
        db.commit()
        if server is None:
            continue
        access, found = server
        for _ in range(PER_ROUND):
            row = db.scalar(
                select(TroupeConnector).where(TroupeConnector.id == row_id).with_for_update()
            )
            assert row is not None
            parts = managed(row.settings)
            expand(parts)
            if not parts["sync"] or not parts["on"]:
                save(row, parts)
                db.commit()
                break
            key = parts["sync"][0]
            try:
                sync_one(db, row, parts, key, found, access)
            except SendError as error:
                db.rollback()
                row = db.scalar(
                    select(TroupeConnector).where(TroupeConnector.id == row_id).with_for_update()
                )
                assert row is not None
                parts = managed(row.settings)
                expand(parts)
                if error.retry:
                    wait = max(SLOW_DOWN, timedelta(seconds=error.retry_after or 0))
                    parts["next_at"] = (at + wait).isoformat()
                    save(row, parts)
                    db.commit()
                    break
                character = db.get(Character, uuid.UUID(key))
                flag(
                    db,
                    row,
                    parts,
                    character,
                    ACCESS,
                    f"Horatio couldn't bring its channel into step: {error.reason}",
                    FIX,
                )
            if key in parts["sync"]:
                parts["sync"].remove(key)
            save(row, parts)
            db.commit()
            done += 1
    return done


# --- checking (#856) ---------------------------------------------------------------------


def check(db: Session, row: TroupeConnector, at: datetime) -> int:
    """Check every channel Horatio made in the troupe's server against what it set,
    record what's wrong (the staff hear of each new problem once), and queue what
    Horatio should have changed and didn't. Commits nothing. Returns how many
    problems there are; raises SendError when Discord can't be asked now."""
    parts = managed(row.settings)
    guild = str(row.settings.get("guild_id") or "")
    access = discord.bot_access(guild)
    found = discord.guild_channels(guild)
    by_id = {str(c.get("id")): c for c in found}
    channels = row.settings.get("channels") or {}
    server = access.server_permissions()
    can_fix = bool(server & discord.MANAGE_ROLES and server & discord.MANAGE_CHANNELS)
    names = role_names(access)
    seen: set[str] = set()

    def problem(character: Character, kind: str, note: str, fix: str | None) -> None:
        flag(db, row, parts, character, kind, note, fix)
        seen.add(f"{character.id}:{kind}")

    for key, channel_id in list(parts["made"].items()):
        character = db.get(Character, uuid.UUID(key))
        want = want_for(db, row, parts, character, access)
        if want is None:
            continue
        assert character is not None
        home = character.home_troupe_id == row.troupe_id
        channel = by_id.get(str(channel_id))
        if channel is None:
            problem(
                character,
                DELETED,
                "Its channel was deleted on Discord.",
                REMAKE if home else None,
            )
            continue
        given = given_for(parts, key, channel, access)
        if (given["slug"], given["player"], tuple(given["roles"])) != (
            want.slug,
            want.player,
            want.roles,
        ):
            queue_sync(parts, key)
        name = str(channel.get("name", ""))
        if not fits(name, given["slug"]):
            problem(
                character,
                NAME,
                f"Its channel #{name} was renamed on Discord.",
                FIX if can_fix else None,
            )
        rules = rules_of(channel)
        lacks = discord.missing(access.permissions(list(rules.values())), discord.PERMISSIONS)
        if lacks:
            problem(
                character,
                BOT,
                f"The Horatio bot needs {discord.listed(lacks)} in #{name}.",
                FIX if can_fix else None,
            )
        shut: list[str] = []
        everyone = rules.get(access.guild_id)
        if everyone is None or not int(everyone.get("deny", 0)) & discord.VIEW_CHANNEL:
            shut.append("everyone can see it")
        for role in given["roles"]:
            if role in want.roles and not allows(rules.get(role), STAFF_ALLOW):
                shut.append(f"@{names.get(role, 'a staff role')} isn't let in")
        if (
            given["player"]
            and given["player"] == want.player
            and not allows(rules.get(given["player"]), PLAYER_ALLOW)
        ):
            shut.append("its player isn't let in")
        if shut:
            problem(
                character,
                ACCESS,
                f"#{name} was changed on Discord: {'; '.join(shut)}.",
                FIX if can_fix else None,
            )
        if want.player and discord.find_member(access.guild_id, want.player) is None:
            problem(
                character,
                ABSENT,
                "Its player isn't on the server, so Horatio can't let them in.",
                INVITE if server & discord.CREATE_INSTANT_INVITE else None,
            )
        if home and channels.get(key) != channel_id:
            problem(
                character,
                UNLINKED,
                f"Its results go to another channel now, not #{name}.",
                RELINK,
            )
    parts["problems"] = {k: v for k, v in parts["problems"].items() if k in seen}
    parts["checked_at"] = at.isoformat()
    parts["check_asked"] = False
    save(row, parts)
    return len(parts["problems"])


def check_due(db: Session, at: datetime | None = None) -> int:
    """Check the troupes whose channels are due a check: those whose staff asked,
    and the rest once a day. Each in its own transaction. Returns how many."""
    at = at or now()
    checked = 0
    for row_id in [
        row.id
        for row in db.scalars(
            select(TroupeConnector)
            .where(TroupeConnector.kind == "discord")
            .order_by(TroupeConnector.id)
        )
        if due_check(row.settings, at)
    ]:
        row = db.scalar(
            select(TroupeConnector).where(TroupeConnector.id == row_id).with_for_update()
        )
        if row is None or not due_check(row.settings, at):
            continue
        try:
            check(db, row, at)
        except SendError as error:
            db.rollback()
            row = db.scalar(
                select(TroupeConnector).where(TroupeConnector.id == row_id).with_for_update()
            )
            assert row is not None
            parts = managed(row.settings)
            if error.retry:
                wait = max(SLOW_DOWN, timedelta(seconds=error.retry_after or 0))
                parts["next_at"] = (at + wait).isoformat()
            else:
                flag(db, row, parts, None, SERVER, error.reason, None, key="server")
                parts["checked_at"] = at.isoformat()
                parts["check_asked"] = False
            save(row, parts)
        db.commit()
        checked += 1
    return checked


def due_check(settings: Mapping[str, Any], at: datetime) -> bool:
    parts = settings.get(KEY) or {}
    if not parts.get("on") or not settings.get("guild_id") or waiting(parts, at):
        return False
    if parts.get("check_asked"):
        return True
    if not parts.get("made"):
        return False
    last = parts.get("checked_at")
    return not last or at - datetime.fromisoformat(last) >= CHECK_EVERY


def ask_check(db: Session, troupe: Troupe, actor: User) -> None:
    """Staff ask Horatio to check the troupe's channels now; the worker does."""
    row = locked(db, troupe.id)
    if row is None:
        return
    parts = managed(row.settings)
    parts["check_asked"] = True
    parts["next_at"] = None
    save(row, parts)
    audit.record(db, actor, "connector.discord_channels_checked", troupe_id=troupe.id)


def keep_in_step_now() -> int:
    """Bring queued channels into step, then check those due, in a session of their
    own, for the delivery worker."""
    from horatio.db import get_sessionmaker

    if not discord.configured():
        return 0
    with get_sessionmaker()() as db:
        return sync_due(db) + check_due(db)


# --- fixing (#856) -----------------------------------------------------------------------

FIX_WORDS = {
    REMAKE: "made its channel again",
    FIX: "put its channel right",
    INVITE: "invited its player to the server",
    RELINK: "sent its results to its channel again",
}


def fix(db: Session, troupe: Troupe, character: Character, how: str, actor: User) -> Outcome:
    """Put one of Horatio's channels right, as staff ask (`how` is one of FIX,
    REMAKE, INVITE, RELINK). Commits nothing. Raises LookupError when the character
    has no channel Horatio made, ValueError for an unknown fix, and SendError when
    Discord could not be asked."""
    if how not in FIX_WORDS:
        raise ValueError("Horatio has no such fix.")
    row = locked(db, troupe.id)
    parts = managed(row.settings) if row is not None else managed({})
    key = str(character.id)
    channel_id = parts["made"].get(key)
    if row is None or channel_id is None:
        raise LookupError("Horatio didn't make a channel for this character.")
    guild = str(row.settings["guild_id"])
    channels = dict(row.settings.get("channels") or {})
    if how == REMAKE:
        if character not in characters(db, troupe.id):
            raise LookupError("Only a character active in the troupe gets its channel again.")
        parts["made"].pop(key, None)
        parts["given"].pop(key, None)
        if channels.get(key) == channel_id:
            channels.pop(key)
        settle(parts, key)
        save(row, parts, channels=channels)
        outcome = make(db, troupe, character, actor)
    elif how == RELINK:
        channels[key] = channel_id
        settle(parts, key, (UNLINKED,))
        save(row, parts, channels=channels)
        outcome = Outcome(MADE, "Its results go to its channel again.", channel_id)
    elif how == INVITE:
        player = db.get(User, character.player_id) if character.player_id else None
        if player is None:
            raise LookupError("This character has no player to invite.")
        access = discord.bot_access(guild)
        outcome = invite(db, parts, access, guild, troupe, character, player, actor)
        save(row, parts)
    else:
        access = discord.bot_access(guild)
        found = discord.guild_channels(guild)
        channel = next((c for c in found if str(c.get("id")) == channel_id), None)
        want = want_for(db, row, parts, character, access)
        if channel is None or want is None:
            raise LookupError("There's nothing of this channel for Horatio to put right.")
        settle(parts, key, (NAME, ACCESS, BOT))
        done = apply(db, row, parts, character, channel, found, access, want, full=True)
        save(row, parts)
        outcome = Outcome(
            MADE,
            f"Horatio {'; '.join(done)}." if done else "Nothing needed putting right.",
            channel_id,
        )
    audit.record(
        db,
        actor,
        "connector.discord_channel_fixed",
        troupe_id=troupe.id,
        character_id=character.id,
        what=FIX_WORDS[how],
    )
    return outcome
