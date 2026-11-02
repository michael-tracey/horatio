"""Items that expire (issue #443): "items found on a plot may have an expiration date".

A troupe switches on "Items can expire" (`Troupe.items_expire`, off by default).
While it is on, its staff give or change an item with an expiry: on a date, after a
number of its holder's games, or at the end of the downtime cycle open now, with a
note on what happens ("The blessing fades"). Its holder sees it on the item. While
the setting is off no expiry shows, warns or runs; one set before waits until the
setting is on again.

- A date is the last day the item is held: it expires once that day is over where
  its holder's player is (their time zone in Settings; for an NPC, the lead
  storyteller's), or in UTC for someone who chose none.
- "After N games" counts the games the holder comes to (horatio.checkin) that start
  after the expiry was set, and the item expires once the Nth has ended. A game it
  was given at doesn't count. `attended_games` is the one place attendance is
  counted.
- "At the end of the cycle" names the troupe's open downtime cycle, and the item
  expires when staff close it.

Its holder's player is warned once, a week before a date or a cycle's deadline, or
once a single game is left. Setting the expiry inside that window counts as the
warning, since the player is told of the expiry then.

On expiry the item is taken back as staff take one back (horatio.equipment), with the
reason EXPIRED and no one as the actor, so it stays in its history; it stops being
held, so its qualities and effects stop. Its holder's player and the troupe's staff
are told.

`check_due` finds what has expired or is due a warning. It runs from three places, so
each kind is caught whichever way it comes due: the delivery worker every few seconds
(horatio.delivery: a date passing, a game ending, a cycle closed any way), check-in
and check-out (horatio.checkin: attendance recorded by hand after a game), and
closing a cycle (horatio.downtimes).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, notifications, preferences
from horatio.models import (
    Character,
    DowntimeCycle,
    EquipmentItem,
    GameAttendance,
    ScheduledGame,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction
from horatio.sheets import unprocessable

EXPIRED = "Expired"
# The holder is warned this long before a date or a cycle's deadline.
WARN_BEFORE = timedelta(days=7)
MOST_GAMES = 100
KINDS = ("date", "games", "cycle")


def now() -> datetime:
    """The current time; tests replace this."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Expiry:
    """An expiry as staff choose it. `games` counts from when it is set."""

    kind: str
    on: date | None = None
    games: int | None = None
    note: str = ""


def home_troupe(db: Session, character: Character) -> Troupe | None:
    home = character.home_troupe_id or character.owner_troupe_id
    return db.get(Troupe, home) if home else None


def applies(troupe: Troupe | None) -> bool:
    return troupe is not None and troupe.items_expire


# --- what is counted ---------------------------------------------------------------------


def attended_games(db: Session, character_id: uuid.UUID, since: datetime, until: datetime) -> int:
    """The games the character came to that started at or after `since` and had ended
    by `until`: what "after N games" counts."""
    return (
        db.scalar(
            select(func.count())
            .select_from(GameAttendance)
            .join(ScheduledGame, GameAttendance.game_id == ScheduledGame.id)
            .where(
                GameAttendance.character_id == character_id,
                ScheduledGame.starts_at >= since,
                ScheduledGame.ends_at <= until,
            )
        )
        or 0
    )


def games_left(db: Session, item: EquipmentItem, at: datetime) -> int:
    assert item.expires_after_games is not None and item.expiry_from is not None
    done = attended_games(db, item.character_id, item.expiry_from, at)
    return max(item.expires_after_games - done, 0)


def zone_of(db: Session, character: Character, troupe: Troupe | None) -> ZoneInfo:
    """Where the holder's day ends: its player's time zone, or for an NPC its troupe's
    lead storyteller's; UTC for someone who chose none."""
    if character.kind == "pc":
        user_id: uuid.UUID | None = character.player_id
    else:
        user_id = troupe.lead_user_id if troupe else None
    user = db.get(User, user_id) if user_id else None
    zone = preferences.read(user).time_zone if user else None
    return ZoneInfo(zone or "UTC")


def day_over(day: date, zone: ZoneInfo) -> datetime:
    """When the day is over in the zone."""
    return datetime.combine(day + timedelta(days=1), time(), zone).astimezone(UTC)


@dataclass(frozen=True)
class Standing:
    """Where an item's expiry stands at a moment."""

    expired: bool
    warn: bool
    # For "games": how many are left.
    games_left: int | None = None
    cycle: DowntimeCycle | None = None


def standing(
    db: Session, item: EquipmentItem, character: Character, troupe: Troupe | None, at: datetime
) -> Standing:
    if item.expiry_kind == "date":
        assert item.expires_on is not None
        ends = day_over(item.expires_on, zone_of(db, character, troupe))
        return Standing(expired=ends <= at, warn=ends - WARN_BEFORE <= at)
    if item.expiry_kind == "games":
        left = games_left(db, item, at)
        return Standing(expired=left == 0, warn=left <= 1, games_left=left)
    cycle = db.get_one(DowntimeCycle, item.expires_cycle_id)
    closed = cycle.status in ("closed", "complete")
    return Standing(expired=closed, warn=closed or cycle.closes_at - WARN_BEFORE <= at, cycle=cycle)


# --- in words ------------------------------------------------------------------------------


def day_text(day: date) -> str:
    return f"{day:%-d %B %Y}"


def recorded(db: Session, item: EquipmentItem, at: datetime) -> dict[str, Any] | None:
    """The expiry as the item's history keeps it, games as those left at `at`."""
    if item.expiry_kind is None:
        return None
    found: dict[str, Any] = {"kind": item.expiry_kind, "note": item.expiry_note}
    if item.expiry_kind == "date":
        assert item.expires_on is not None
        found["on"] = item.expires_on.isoformat()
    elif item.expiry_kind == "games":
        found["games"] = games_left(db, item, at)
    else:
        found["cycle"] = db.get_one(DowntimeCycle, item.expires_cycle_id).name
    return found


def when_text(kept: dict[str, Any]) -> str:
    """When a recorded expiry comes: "on 30 November 2026", "after 2 more games",
    "when the downtime cycle October 2026 closes"."""
    if kept["kind"] == "date":
        return f"on {day_text(date.fromisoformat(kept['on']))}"
    if kept["kind"] == "games":
        games = kept["games"]
        return "after its next game" if games == 1 else f"after {games} more games"
    return f"when the downtime cycle {kept['cycle']} closes"


def change_text(old: dict[str, Any] | None, new: dict[str, Any] | None) -> str:
    """A change of expiry, as the history and the holder's player read it."""
    if new is None:
        return "no longer expires"
    if old is not None and {**old, "note": ""} == {**new, "note": ""}:
        return "a new note on what happens when it expires"
    return f"now expires {when_text(new)}"


# --- set by staff --------------------------------------------------------------------------


def open_cycle(db: Session, troupe: Troupe) -> DowntimeCycle | None:
    return db.scalar(
        select(DowntimeCycle).where(
            DowntimeCycle.troupe_id == troupe.id, DowntimeCycle.status == "open"
        )
    )


def same(db: Session, item: EquipmentItem, expiry: Expiry, troupe: Troupe, at: datetime) -> bool:
    """The item already expires as asked, its note aside: the same day, as many games
    left, or the cycle open now."""
    if item.expiry_kind != expiry.kind:
        return False
    if expiry.kind == "date":
        return item.expires_on == expiry.on
    if expiry.kind == "games":
        return games_left(db, item, at) == expiry.games
    cycle = open_cycle(db, troupe)
    return cycle is not None and item.expires_cycle_id == cycle.id


def checked(db: Session, troupe: Troupe, expiry: Expiry, at: datetime) -> Expiry:
    """The expiry, its note trimmed, or 422."""
    if not troupe.items_expire:
        raise unprocessable(
            f"Items don't expire in {troupe.name}: switch on Items can expire in its settings."
        )
    if expiry.kind not in KINDS:
        raise unprocessable("An item expires on a date, after a number of games, or with a cycle.")
    if expiry.kind == "date" and (expiry.on is None or expiry.on < at.date()):
        raise unprocessable("Choose a day from today on for it to expire.")
    if expiry.kind == "games" and not (expiry.games and 1 <= expiry.games <= MOST_GAMES):
        raise unprocessable(f"It expires after 1 to {MOST_GAMES} games.")
    if expiry.kind == "cycle" and open_cycle(db, troupe) is None:
        raise unprocessable(
            f"No downtime cycle is open in {troupe.name}, so it can't expire at the end of one."
        )
    return Expiry(expiry.kind, expiry.on, expiry.games, expiry.note.strip())


def planned(
    db: Session,
    troupe: Troupe,
    item: EquipmentItem,
    expiry: Expiry | None,
    at: datetime | None = None,
) -> dict[str, Any] | None:
    """What setting the item's expiry to `expiry` (None: removing it) would change,
    {"from": ..., "to": ...}, as the item's history keeps it; None for nothing. A bad
    expiry is refused (422). Nothing is changed yet: `set_expiry` does that."""
    at = at or now()
    before = recorded(db, item, at)
    if expiry is None:
        return None if before is None else {"from": before, "to": None}
    expiry = checked(db, troupe, expiry, at)
    after: dict[str, Any] = {"kind": expiry.kind, "note": expiry.note}
    if expiry.kind == "date":
        assert expiry.on is not None
        after["on"] = expiry.on.isoformat()
    elif expiry.kind == "games":
        after["games"] = expiry.games
    else:
        cycle = open_cycle(db, troupe)
        assert cycle is not None
        after["cycle"] = cycle.name
    return None if after == before else {"from": before, "to": after}


def set_expiry(
    db: Session,
    troupe: Troupe,
    item: EquipmentItem,
    character: Character,
    expiry: Expiry | None,
    at: datetime | None = None,
) -> dict[str, Any] | None:
    """Set, change or remove the item's expiry. Returns the change, as `planned` says;
    None if nothing changed. A new expiry already inside the warning window counts
    as warned: its holder's player is told of it as it is set."""
    at = at or now()
    found = planned(db, troupe, item, expiry, at)
    if found is None:
        return None
    if expiry is None:
        item.expiry_kind = None
        item.expires_on = item.expires_after_games = item.expires_cycle_id = None
        item.expiry_from = item.expiry_warned_at = None
        item.expiry_note = ""
        return found
    if not same(db, item, expiry, troupe, at):
        cycle = open_cycle(db, troupe) if expiry.kind == "cycle" else None
        item.expiry_kind = expiry.kind
        item.expires_on = expiry.on if expiry.kind == "date" else None
        item.expires_after_games = expiry.games if expiry.kind == "games" else None
        item.expires_cycle_id = cycle.id if cycle else None
        item.expiry_from = at
        db.flush()
        item.expiry_warned_at = at if standing(db, item, character, troupe, at).warn else None
    item.expiry_note = expiry.note.strip()
    return found


# --- warned, and expired -------------------------------------------------------------------


def holder_link(character: Character) -> str:
    return f"/characters/{character.id}/equipment"


def warn(
    db: Session, item: EquipmentItem, character: Character, troupe: Troupe, at: datetime
) -> None:
    """Tell the holder's player the item is about to expire."""
    item.expiry_warned_at = at
    kept = recorded(db, item, at)
    if character.kind != "pc" or kept is None:
        return
    notifications.notify(
        db,
        [character.player_id],
        "equipment.expiring",
        f"{character.name}'s {item.name} expires {when_text(kept)}.",
        holder_link(character),
        troupe_id=troupe.id,
        character_id=character.id,
    )


def expire(
    db: Session, item: EquipmentItem, character: Character, troupe: Troupe, at: datetime
) -> None:
    """Take the item back as expired: as staff take one back, with the reason EXPIRED,
    kept in its history. Its holder's player and the troupe's staff are told."""
    from horatio import equipment

    kept = recorded(db, item, at)
    item.status = "taken_back"
    equipment.record(
        db,
        item,
        "taken_back",
        None,
        troupe,
        before=character,
        reason=EXPIRED,
        changes={"expired": kept},
    )
    audit.record(
        db,
        None,
        "equipment.expired",
        troupe_id=troupe.id,
        character_id=character.id,
        item=item.name,
        note=item.expiry_note,
    )
    then = f" {item.expiry_note}" if item.expiry_note else ""
    if character.kind == "pc":
        notifications.notify(
            db,
            [character.player_id],
            "equipment.expired",
            f"{character.name}'s {item.name} has expired and is no longer held.{then}",
            holder_link(character),
            troupe_id=troupe.id,
            character_id=character.id,
        )
    notifications.notify(
        db,
        notifications.staff_for(db, troupe, TroupeAction.MANAGE_EQUIPMENT),
        "equipment.expired",
        f"{character.name}'s {item.name} has expired, and was taken back.",
        f"/troupes/{troupe.id}/equipment",
        troupe_id=troupe.id,
        character_id=character.id,
    )
    db.flush()


def check_due(
    db: Session,
    at: datetime | None = None,
    *,
    character_ids: Sequence[uuid.UUID] | None = None,
    cycle_ids: Sequence[uuid.UUID] | None = None,
) -> int:
    """Take back each held item whose expiry has come, and warn the holders of those
    about to expire, in running troupes that let items expire: only those of
    `character_ids`, or ending with `cycle_ids`, when given. Rows another worker holds
    are left to it. Returns how many expired."""
    at = at or now()
    query = (
        select(EquipmentItem, Character, Troupe)
        .join(Character, EquipmentItem.character_id == Character.id)
        .join(
            Troupe,
            Troupe.id == func.coalesce(Character.home_troupe_id, Character.owner_troupe_id),
        )
        .where(
            EquipmentItem.status == "held",
            EquipmentItem.expiry_kind.is_not(None),
            Troupe.items_expire,
            Troupe.archived_at.is_(None),
        )
        .order_by(EquipmentItem.id)
        .with_for_update(of=EquipmentItem, skip_locked=True)
    )
    if character_ids is not None:
        query = query.where(EquipmentItem.character_id.in_(list(character_ids)))
    if cycle_ids is not None:
        query = query.where(EquipmentItem.expires_cycle_id.in_(list(cycle_ids)))
    expired = 0
    for item, character, troupe in db.execute(query).all():
        found = standing(db, item, character, troupe, at)
        if found.expired:
            expire(db, item, character, troupe, at)
            expired += 1
        elif found.warn and item.expiry_warned_at is None:
            warn(db, item, character, troupe, at)
    db.flush()
    return expired


def check_due_now() -> int:
    """`check_due` in a session of its own, for the delivery worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        expired = check_due(db)
        db.commit()
        return expired
