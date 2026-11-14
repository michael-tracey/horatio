"""The clan and discipline symbols as emoji on a troupe's Discord server (#870).

A troupe that switches it on (its Discord settings, `emoji`) lets Horatio add the
symbols the Jyhad card shows to its server as custom emoji, so players can write
`:brujah:` or `:aus_sup:` in their own messages. It is opt-in because the bot then
needs more on the server than results and posts do: Create Expressions
(horatio.connectors.discord.FOR_EMOJI), which also lets it delete the emoji it added
itself. Horatio never touches an emoji it didn't add.

The symbols are KRCG's (horatio.vtes_symbols), fetched by the custodian under the
Dark Pack Agreement: clans (with antitribu and bloodlines where KRCG has them), the
disciplines inferior and superior, and the Sabbat's paths. The troupe picks their
style: white-bordered, as printed cards and the Jyhad card draw them (`png_wb`,
which reads well on Discord's dark theme), or plain (`png`). Each is made a 128 ×
128 PNG within Discord's 256 KiB, as Discord asks of an emoji.

Each symbol has one name, so players can guess it: a clan by KRCG's name for it
(`brujah`, `banuhaqim`), an inferior discipline by its three letters (`aus`), a
superior one with `_sup` (`aus_sup`), a path with `path_` (`path_caine`). A name an
emoji Horatio didn't add already has is left alone, and that symbol skipped.

**Room.** Discord lets a server have so many static emoji by its Server Boost level
(`ROOM`: 50, 100, 150, 250; 200 at least for a server with Discord's MORE_EMOJI
feature), which its API doesn't say but its help pages do, and there are well over
a hundred symbols. So the troupe chooses which, in order, and Horatio adds them in
that order until the server is full; what didn't fit is listed. It can make room
by removing the emoji it added earlier that aren't chosen now. If the server fills
while Horatio is adding (someone added emoji meanwhile: Discord says so, code
30008), it stops, and says what wasn't added. As a fallback, a troupe may let
Horatio use emoji of its own instead (Discord's application emoji, up to 2,000 for
the app, beside no server's), which don't take the server's room but which players
can't use in their messages: only Horatio's own posts could show them. They are
shared by every troupe, so Horatio never deletes one for a troupe.

Adding and removing goes through the delivery worker (`queue`), a few a troupe each
round, waiting when Discord asks it to: its emoji routes are strictly rate limited,
per server. What happened to each symbol is kept (`state`) for staff to read, and
which emoji Horatio added (`made`), with its id, name and style, so pushing again
after a style change replaces them, and only they are ever removed. Each round's
additions and removals go in the troupe's log.

Everything lives in the troupe's Discord connector settings, under `emoji`, and is
changed only here; the connector's own Save keeps it.
"""

import copy
import io
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, jyhad_card, sheets, social_age, vtes_symbols
from horatio.connectors import SendError, discord
from horatio.models import Character, Troupe, TroupeConnector, User

KEY = "emoji"
# The styles a troupe may choose: KRCG's white-bordered PNGs, or its plain ones.
STYLES = ("png_wb", "png")
# The groups of symbol Horatio adds, in the order a troupe sees them.
GROUPS = ("clan", "disc/sup", "disc/inf", "path")
# Static emoji a server may have at each Server Boost level (Discord's help pages;
# its API doesn't say), and at least this many with the MORE_EMOJI feature.
ROOM = {0: 50, 1: 100, 2: 150, 3: 250}
MORE_EMOJI_ROOM = 200
# An emoji's image: Discord asks for 128 × 128, and at most 256 KiB.
SIZE = 128
MOST_BYTES = 256 * 1024
# How many changes the worker makes for a troupe each round, and how long it waits
# at least when Discord asks it to slow down.
PER_ROUND = 5
SLOW_DOWN = timedelta(seconds=60)

# What happened to a symbol, for staff to read.
ADDED = "added"
OWN = "own"
QUEUED = "queued"
REMOVED = "removed"
NO_ROOM = "no_room"
NAME_TAKEN = "name_taken"
FAILED = "failed"


def now() -> datetime:
    """The current time; tests replace this."""
    return datetime.now(UTC)


def emoji(settings: Mapping[str, Any]) -> dict[str, Any]:
    """The troupe's emoji settings, with every part present."""
    found = copy.deepcopy(dict(settings.get(KEY) or {}))
    found.setdefault("on", False)
    found.setdefault("style", STYLES[0])
    found.setdefault("own", False)
    found.setdefault("queue", [])
    for part in ("made", "state"):
        found.setdefault(part, {})
    found.setdefault("next_at", None)
    found.setdefault("queued_by", None)
    return found


def save(row: TroupeConnector, parts: Mapping[str, Any]) -> None:
    row.settings = {**row.settings, KEY: dict(parts)}


def locked(db: Session, troupe_id: uuid.UUID) -> TroupeConnector | None:
    """The troupe's Discord connector, locked until the transaction ends."""
    return db.scalar(
        select(TroupeConnector)
        .where(TroupeConnector.troupe_id == troupe_id, TroupeConnector.kind == "discord")
        .with_for_update()
    )


def room(found: discord.EmojiRoom) -> int:
    """How many static emoji the server may have."""
    most = ROOM[min(max(found.premium_tier, 0), max(ROOM))]
    return max(most, MORE_EMOJI_ROOM) if "MORE_EMOJI" in found.features else most


def used(found: discord.EmojiRoom) -> int:
    return sum(1 for e in found.emoji if not e.animated)


# --- the symbols -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    """A symbol Horatio can add, as `clan/brujah` or `disc/sup/aus`: its group, KRCG's
    name for it, the name people know it by, and its emoji's name."""

    key: str
    group: str
    krcg: str
    label: str
    name: str


def emoji_name(group: str, krcg: str) -> str:
    """A symbol's emoji name: Discord's rules are 2 to 32 letters, digits or
    underscores."""
    base = {"disc/sup": f"{krcg}_sup", "path": f"path_{krcg}"}.get(group, krcg)
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in base)[:32]
    return cleaned if len(cleaned) >= 2 else f"{cleaned}__"[:2]


def label(group: str, krcg: str) -> str:
    """The name people know a symbol by."""
    if group == "clan":
        clans = {v: k for k, v in vtes_symbols.CLANS.items()}
        return clans.get(krcg, krcg.replace("antitribu", " antitribu").title())
    if group in ("disc/sup", "disc/inf"):
        disciplines = {v: k for k, v in vtes_symbols.DISCIPLINES.items()}
        name = disciplines.get(krcg, krcg.upper())
        return f"{name} (superior)" if group == "disc/sup" else f"{name} (inferior)"
    return krcg.title()


def available(style: str, record: Mapping[str, Any] | None = None) -> list[Symbol]:
    """Every symbol the custodian fetched in a style, clans first, then superior and
    inferior disciplines, then paths, each by name."""
    record = dict(record if record is not None else vtes_symbols.manifest())
    files = record.get("files", {})
    found: list[Symbol] = []
    for group in GROUPS:
        names = sorted(files.get(f"{style}/{group}", []))
        found += [
            Symbol(
                key=f"{group}/{n}",
                group=group,
                krcg=n,
                label=label(group, n),
                name=emoji_name(group, n),
            )
            for n in names
        ]
    return sorted(found, key=lambda s: (GROUPS.index(s.group), s.label.casefold(), s.key))


def image(style: str, symbol: Symbol) -> bytes:
    """A symbol as an emoji's image: a 128 × 128 PNG, the symbol centred on
    transparency, within 256 KiB. Raises LookupError when it isn't fetched, or
    ValueError when it won't fit."""
    file = vtes_symbols.symbol_file(style, f"{symbol.group}/{symbol.krcg}.png")
    if file is None:
        raise LookupError(f"{symbol.label}'s symbol isn't fetched in that style.")
    with Image.open(file) as opened:
        picture = opened.convert("RGBA")
    picture.thumbnail((SIZE, SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(picture, ((SIZE - picture.width) // 2, (SIZE - picture.height) // 2))
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    data = out.getvalue()
    if len(data) > MOST_BYTES:
        raise ValueError(f"{symbol.label}'s image is bigger than Discord allows for an emoji.")
    return data


# --- shortcuts: what this troupe uses --------------------------------------------------------


def troupe_characters(db: Session, troupe_id: uuid.UUID) -> list[Character]:
    return list(
        db.scalars(
            select(Character)
            .where(Character.home_troupe_id == troupe_id, Character.status == "active")
            .order_by(Character.name, Character.id)
        )
    )


def shortcuts(db: Session, troupe: Troupe, symbols: Sequence[Symbol]) -> dict[str, list[str]]:
    """The symbols of the troupe's characters' clans, and of the disciplines they
    hold (superior from 4 dots, as on the Jyhad card), among those given."""
    have = {s.key for s in symbols}
    found = troupe_characters(db, troupe.id)
    ages = social_age.standings(db, [c.id for c in found]) if found else {}
    clans: list[str] = []
    used_disciplines: list[str] = []
    for character in found:
        clan = ages[character.id].clan if character.id in ages else None
        krcg = vtes_symbols.CLANS.get(clan or "")
        if krcg and f"clan/{krcg}" in have and f"clan/{krcg}" not in clans:
            clans.append(f"clan/{krcg}")
        held = [
            (row.definition.name, row.trait.rating or 0)
            for row in sheets.sheet_rows(db, character)
            if row.category.key == "disciplines"
        ]
        for discipline in jyhad_card.on_card(held):
            three = vtes_symbols.DISCIPLINES.get(discipline.name)
            group = "disc/sup" if discipline.superior else "disc/inf"
            key = f"{group}/{three}"
            if three and key in have and key not in used_disciplines:
                used_disciplines.append(key)
    order = {s.key: n for n, s in enumerate(symbols)}
    return {
        "clans": sorted(clans, key=order.__getitem__),
        "disciplines": sorted(used_disciplines, key=order.__getitem__),
    }


# --- pushing ---------------------------------------------------------------------------------


def set_state(parts: dict[str, Any], key: str, status: str, note: str) -> None:
    parts["state"][key] = {"status": status, "note": note, "at": now().isoformat()}


@dataclass(frozen=True)
class Plan:
    """What pushing a choice comes to: emoji to remove, symbols to add, and how many
    of those fit now."""

    remove: list[str]
    add: list[str]
    fits: int | None


def plan(
    parts: Mapping[str, Any],
    chosen: Sequence[str],
    style: str,
    remove_others: bool,
    free: int | None,
) -> Plan:
    """Remove the emoji Horatio added in another style (and, if asked, those no longer
    chosen); add the chosen symbols it hasn't, in the order chosen. Removing one of
    Horatio's own emoji only forgets it: they are shared, and never deleted."""
    made: Mapping[str, Any] = parts["made"]
    remove = [
        key
        for key, found in made.items()
        if found.get("style") != style and key in chosen or remove_others and key not in chosen
    ]
    add = [k for k in chosen if not (k in made and made[k].get("style") == style)]
    freed = sum(1 for k in remove if made[k].get("where") == "server")
    fits = None if free is None else min(len(add), free + freed)
    return Plan(remove=remove, add=add, fits=fits)


def queue(
    db: Session,
    troupe: Troupe,
    row: TroupeConnector,
    chosen: Sequence[str],
    remove_others: bool,
    free: int | None,
    actor: User,
) -> Plan:
    """Queue a push for the worker. Commits nothing."""
    parts = emoji(row.settings)
    style = parts["style"]
    found = plan(parts, chosen, style, remove_others, free)
    parts["queue"] = [{"do": "remove", "key": k} for k in found.remove] + [
        {"do": "add", "key": k} for k in found.add
    ]
    for key in found.add:
        set_state(parts, key, QUEUED, "Waiting for Horatio to add it.")
    parts["queued_by"] = str(actor.id)
    parts["next_at"] = None
    save(row, parts)
    audit.record(
        db,
        actor,
        "connector.discord_emoji_queued",
        troupe_id=troupe.id,
        adding=len(found.add),
        removing=len(found.remove),
    )
    return found


def due(settings: Mapping[str, Any], at: datetime) -> bool:
    parts = settings.get(KEY) or {}
    if not parts.get("queue"):
        return False
    waiting = parts.get("next_at")
    return not waiting or datetime.fromisoformat(waiting) <= at


@dataclass
class Round:
    """One troupe's round of changes: the server as Horatio last saw it this round,
    and what it added and removed, for the log."""

    room: discord.EmojiRoom | None = None
    # Discord said the server is full, whatever Horatio counted.
    full: bool = False
    own: list[discord.Emoji] | None = None
    added: list[str] | None = None
    removed: list[str] | None = None


def apply_one(parts: dict[str, Any], guild: str, step: Mapping[str, Any], seen: Round) -> None:
    """Make one queued change. Raises SendError when Discord should be asked again
    later; anything else is recorded in the symbol's state."""
    key = str(step.get("key", ""))
    symbols = {s.key: s for s in available(parts["style"])}
    if step.get("do") == "remove":
        found = parts["made"].get(key)
        if found and found.get("where") == "server":
            discord.delete_emoji(guild, str(found["id"]))
            seen.removed = [*(seen.removed or []), str(found.get("name", key))]
            seen.room = None
        parts["made"].pop(key, None)
        set_state(parts, key, REMOVED, "Horatio removed its emoji.")
        return
    symbol = symbols.get(key)
    if symbol is None:
        set_state(parts, key, FAILED, "Its symbol isn't fetched in this style any more.")
        return
    try:
        png = image(parts["style"], symbol)
    except (LookupError, ValueError, OSError) as error:
        set_state(parts, key, FAILED, str(error))
        return
    if seen.room is None:
        seen.room = discord.emoji_room(guild)
    ours = {str(f.get("id")) for f in parts["made"].values()}
    if any(e.name == symbol.name and e.id not in ours for e in seen.room.emoji):
        set_state(
            parts,
            key,
            NAME_TAKEN,
            f"The server already has an emoji called :{symbol.name}: that Horatio didn't add.",
        )
        return
    if not seen.full and used(seen.room) < room(seen.room):
        try:
            made = discord.create_emoji(guild, symbol.name, png)
        except SendError as error:
            if error.code not in (discord.MAX_EMOJI, discord.FILE_TOO_BIG) or error.retry:
                raise
            if error.code == discord.FILE_TOO_BIG:
                set_state(parts, key, FAILED, "Discord said its image was too big.")
                return
            # Full after all: someone added emoji meanwhile.
            seen.full = True
        else:
            parts["made"][key] = {
                "id": made.id,
                "name": made.name,
                "style": parts["style"],
                "where": "server",
            }
            seen.room = discord.EmojiRoom(
                premium_tier=seen.room.premium_tier,
                features=seen.room.features,
                emoji=[*seen.room.emoji, made],
            )
            seen.added = [*(seen.added or []), made.name]
            set_state(parts, key, ADDED, f"Added as :{made.name}:.")
            return
    if not parts["own"]:
        set_state(
            parts,
            key,
            NO_ROOM,
            "The server has no emoji room left. Remove some, or choose fewer.",
        )
        return
    # Horatio's own emoji are shared by every troupe, so the style is in the name.
    own_name = (symbol.name + ("_wb" if parts["style"] == "png_wb" else ""))[:32]
    if seen.own is None:
        seen.own = discord.app_emoji()
    existing = next((e for e in seen.own if e.name == own_name), None)
    if existing is None:
        existing = discord.create_app_emoji(own_name, png)
        seen.own = [*seen.own, existing]
    parts["made"][key] = {
        "id": existing.id,
        "name": existing.name,
        "style": parts["style"],
        "where": "app",
    }
    set_state(
        parts,
        key,
        OWN,
        "No room on the server: Horatio uses its own emoji for it, which only its posts can show.",
    )


def push_due(db: Session, at: datetime | None = None) -> int:
    """Make some of each troupe's queued changes, `PER_ROUND` a troupe, each in its
    own transaction. Discord asking Horatio to slow down stops that troupe's round
    and waits. Returns how many changes were tried."""
    at = at or now()
    tried = 0
    ids = [
        row.id
        for row in db.scalars(select(TroupeConnector).where(TroupeConnector.kind == "discord"))
        if due(row.settings, at)
    ]
    for row_id in ids:
        seen = Round()
        actor: User | None = None
        troupe_id: uuid.UUID | None = None
        for _ in range(PER_ROUND):
            row = db.scalar(
                select(TroupeConnector).where(TroupeConnector.id == row_id).with_for_update()
            )
            if row is None or not due(row.settings, at):
                break
            parts = emoji(row.settings)
            troupe_id = row.troupe_id
            actor = db.get(User, uuid.UUID(parts["queued_by"])) if parts["queued_by"] else None
            step = parts["queue"][0]
            guild = row.settings.get("guild_id")
            if not guild or not parts["on"] or not discord.configured():
                for each in parts["queue"]:
                    if each.get("do") == "add":
                        set_state(parts, str(each.get("key")), FAILED, "Emoji were switched off.")
                parts["queue"] = []
                save(row, parts)
                db.commit()
                break
            try:
                apply_one(parts, str(guild), step, seen)
            except SendError as error:
                db.rollback()
                row = locked(db, troupe_id)
                assert row is not None
                parts = emoji(row.settings)
                if error.retry:
                    wait = max(SLOW_DOWN, timedelta(seconds=error.retry_after or 0))
                    parts["next_at"] = (at + wait).isoformat()
                    set_state(parts, str(step.get("key")), QUEUED, f"Waiting: {error.reason}")
                else:
                    parts["queue"].pop(0)
                    set_state(parts, str(step.get("key")), FAILED, error.reason)
                save(row, parts)
                db.commit()
                tried += 1
                if error.retry:
                    break
                continue
            parts["queue"].pop(0)
            save(row, parts)
            db.commit()
            tried += 1
        if troupe_id is not None and actor is not None and (seen.added or seen.removed):
            if seen.added:
                audit.record(
                    db,
                    actor,
                    "connector.discord_emoji_added",
                    troupe_id=troupe_id,
                    names=", ".join(f":{n}:" for n in seen.added),
                )
            if seen.removed:
                audit.record(
                    db,
                    actor,
                    "connector.discord_emoji_removed",
                    troupe_id=troupe_id,
                    names=", ".join(f":{n}:" for n in seen.removed),
                )
            db.commit()
    return tried


def push_due_now() -> int:
    """`push_due` in a session of its own, for the delivery worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        return push_due(db)


def chosen_symbols(keys: Iterable[str], symbols: Sequence[Symbol]) -> list[str]:
    """The chosen keys that are symbols, once each, in the order given."""
    have = {s.key for s in symbols}
    return [k for k in dict.fromkeys(keys) if k in have]
