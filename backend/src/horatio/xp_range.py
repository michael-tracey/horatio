"""A troupe's XP floor and ceiling, and a character's XP against them (issue #74).

The ceiling is the most XP a character in the troupe could have been given by
now: the troupe's starting XP, every game's XP and every downtime's XP for
completing it. The floor is the same without the downtimes. Both are kept as a
list of changes (`XpRangeEntry`) added when staff award a game's XP or close a
downtime cycle, and staff can set either figure by hand for a chronicle that
began before Horatio.

A character built for a troupe starts at its floor. One built in its player's
vault starts at the rule set's starting XP, and its player may add XP to it
themselves (self-entered). When a character asks to make a troupe its home, its
XP is set against that troupe's figures: below the floor it is offered a top-up,
above the ceiling staff are shown how far, and staff accept or remove any
self-entered XP. Each thing done is its own XP entry, never an edit to an
earlier one.

"XP given" is what the comparison counts: awards, self-entered XP, corrections
and caps. XP a flaw pays back is traded for the flaw, not given, and is left out.
"""

import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, DowntimeCycle, Troupe, User, XpEntry, XpRangeEntry

# Entries that change what a character has been given, rather than spend it.
GIVEN = ("award", "self_entered", "correction", "cap")


@dataclass
class Figures:
    starting: int
    floor: int
    ceiling: int
    # How many games and downtime cycles added to them, and how much XP in all.
    games: int
    game_xp: int
    downtimes: int
    downtime_xp: int
    # What setting them by hand added (or took away).
    set_floor: int
    set_ceiling: int


def figures(db: Session, troupe: Troupe) -> Figures:
    return figures_of(db, [troupe])[troupe.id]


def figures_of(db: Session, troupes: Sequence[Troupe]) -> dict[uuid.UUID, Figures]:
    """Each troupe's figures, asked of the database once."""
    totals: dict[uuid.UUID, dict[str, tuple[int, int, int]]] = {t.id: {} for t in troupes}
    for troupe_id, kind, count, floor, ceiling in db.execute(
        select(
            XpRangeEntry.troupe_id,
            XpRangeEntry.kind,
            func.count(),
            func.sum(XpRangeEntry.floor_change),
            func.sum(XpRangeEntry.ceiling_change),
        )
        .where(XpRangeEntry.troupe_id.in_([t.id for t in troupes]))
        .group_by(XpRangeEntry.troupe_id, XpRangeEntry.kind)
    ):
        totals[troupe_id][kind] = (count, floor or 0, ceiling or 0)
    return {t.id: summed(t, totals[t.id]) for t in troupes}


def summed(troupe: Troupe, totals: dict[str, tuple[int, int, int]]) -> Figures:
    games, game_floor, _ = totals.get("game", (0, 0, 0))
    downtimes, _, downtime_ceiling = totals.get("downtime", (0, 0, 0))
    _, set_floor, set_ceiling = totals.get("set", (0, 0, 0))
    floor = troupe.starting_xp + sum(f for _, f, _ in totals.values())
    ceiling = troupe.starting_xp + sum(c for _, _, c in totals.values())
    return Figures(
        starting=troupe.starting_xp,
        floor=floor,
        ceiling=ceiling,
        games=games,
        game_xp=game_floor,
        downtimes=downtimes,
        downtime_xp=downtime_ceiling,
        set_floor=set_floor,
        set_ceiling=set_ceiling,
    )


def entries(db: Session, troupe: Troupe) -> list[XpRangeEntry]:
    return list(
        db.scalars(
            select(XpRangeEntry)
            .where(XpRangeEntry.troupe_id == troupe.id)
            .order_by(XpRangeEntry.id)
        )
    )


def add_game(db: Session, staff: User, troupe: Troupe, amount: int, reason: str) -> None:
    """A game's XP raises the floor and the ceiling alike."""
    if amount <= 0:
        return
    db.add(
        XpRangeEntry(
            troupe_id=troupe.id,
            kind="game",
            floor_change=amount,
            ceiling_change=amount,
            reason=reason,
            entered_by=staff.id,
        )
    )
    audit.record(db, staff, "troupe.xp_range_game", troupe_id=troupe.id, amount=amount)
    # A game has passed: Out of Code counts it (horatio.location_quests).
    from horatio import location_quests

    location_quests.game_passed(db, staff, troupe)


def add_downtime(db: Session, staff: User, cycle: DowntimeCycle) -> None:
    """A downtime's XP for completing it raises only the ceiling: not every
    character completes every downtime."""
    if cycle.completion_xp <= 0:
        return
    db.add(
        XpRangeEntry(
            troupe_id=cycle.troupe_id,
            kind="downtime",
            floor_change=0,
            ceiling_change=cycle.completion_xp,
            reason=f"Downtime: {cycle.name}",
            entered_by=staff.id,
            cycle_id=cycle.id,
        )
    )
    audit.record(
        db, staff, "troupe.xp_range_downtime", troupe_id=cycle.troupe_id, amount=cycle.completion_xp
    )


def set_by_hand(
    db: Session,
    staff: User,
    troupe: Troupe,
    floor: int | None,
    ceiling: int | None,
    reason: str,
) -> None:
    """Set either figure, for a chronicle that began before Horatio: an entry
    for the difference, so what games and downtimes added stays in the record."""
    now = figures(db, troupe)
    new_floor = now.floor if floor is None else floor
    new_ceiling = now.ceiling if ceiling is None else ceiling
    if new_floor > new_ceiling:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The floor cannot be above the ceiling."
        )
    if new_floor == now.floor and new_ceiling == now.ceiling:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The floor and ceiling are already those."
        )
    db.add(
        XpRangeEntry(
            troupe_id=troupe.id,
            kind="set",
            floor_change=new_floor - now.floor,
            ceiling_change=new_ceiling - now.ceiling,
            reason=reason,
            entered_by=staff.id,
        )
    )
    audit.record(
        db,
        staff,
        "troupe.xp_range_set",
        troupe_id=troupe.id,
        floor=new_floor,
        ceiling=new_ceiling,
        reason=reason,
    )


# --- a character's XP ---------------------------------------------------------------------


def self_entered_entries(db: Session, character: Character) -> list[tuple[XpEntry, int]]:
    """Each self-entered entry, with what it gives now after corrections."""
    corrections = {
        corrects: amount
        for corrects, amount in db.execute(
            select(XpEntry.corrects_id, func.sum(XpEntry.amount))
            .where(XpEntry.character_id == character.id, XpEntry.kind == "correction")
            .group_by(XpEntry.corrects_id)
        )
    }
    found = db.scalars(
        select(XpEntry)
        .where(XpEntry.character_id == character.id, XpEntry.kind == "self_entered")
        .order_by(XpEntry.id)
    )
    return [(e, e.amount + (corrections.get(e.id) or 0)) for e in found]


def given_xp(db: Session, character: Character) -> int:
    """The XP the character has been given. A correction to a purchase takes back XP a
    flaw paid (a diablerie removing one does), which was never given, so it is left out."""
    purchases = select(XpEntry.id).where(XpEntry.kind == "purchase")
    return (
        db.scalar(
            select(func.coalesce(func.sum(XpEntry.amount), 0)).where(
                XpEntry.character_id == character.id,
                XpEntry.kind.in_(GIVEN),
                XpEntry.corrects_id.is_(None) | XpEntry.corrects_id.not_in(purchases),
            )
        )
        or 0
    )


def add_self_entered(
    db: Session, player: User, character: Character, amount: int, reason: str
) -> XpEntry:
    """XP a player gives their own character while it has no home troupe. The
    troupe it asks to join sees it apart, and accepts or removes it."""
    if character.kind != "pc":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a player character gets XP this way.")
    if character.home_troupe_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The character has a home troupe; its storytellers award its XP.",
        )
    entry = XpEntry(
        character_id=character.id,
        kind="self_entered",
        amount=amount,
        reason=reason,
        entered_by=player.id,
    )
    db.add(entry)
    db.flush()
    audit.record(
        db, player, "xp.self_entered", character_id=character.id, amount=amount, reason=reason
    )
    return entry


@dataclass
class Review:
    """A character's XP against a troupe's floor and ceiling, and, once decided,
    what was done about it."""

    given: int
    # The part of `given` its player entered themselves.
    self_entered: int
    floor: int
    ceiling: int
    # The player's choice: top up to the floor if below it.
    top_up_asked: bool
    # Once decided:
    self_entered_removed: int | None = None
    topped_up: int | None = None
    above_ceiling_removed: int | None = None
    extra: int | None = None

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


def review(db: Session, character: Character, troupe: Troupe, top_up_asked: bool) -> Review:
    now = figures(db, troupe)
    return Review(
        given=given_xp(db, character),
        self_entered=sum(gives for _, gives in self_entered_entries(db, character)),
        floor=now.floor,
        ceiling=now.ceiling,
        top_up_asked=top_up_asked,
    )


@dataclass
class Decision:
    """What staff decide about the character's XP as it joins."""

    self_entered: Literal["keep", "remove"] = "keep"
    # None goes with the player's choice.
    top_up: bool | None = None
    above_ceiling: Literal["keep", "remove"] = "keep"
    # More XP for this character beyond the floor, such as for a returning player.
    extra: int = 0
    extra_reason: str = ""


@dataclass
class Plan:
    self_entered_removed: int = 0
    topped_up: int = 0
    above_ceiling_removed: int = 0
    extra: int = 0

    @property
    def delta(self) -> int:
        return self.topped_up + self.extra - self.self_entered_removed - self.above_ceiling_removed


def plan(found: Review, decision: Decision) -> Plan:
    """Removing self-entered XP comes first, so the floor and ceiling are measured
    against what the character keeps."""
    removed = found.self_entered if decision.self_entered == "remove" else 0
    given = found.given - removed
    top_up = found.top_up_asked if decision.top_up is None else decision.top_up
    return Plan(
        self_entered_removed=removed,
        topped_up=found.floor - given if top_up and given < found.floor else 0,
        above_ceiling_removed=given - found.ceiling
        if decision.above_ceiling == "remove" and given > found.ceiling
        else 0,
        extra=decision.extra,
    )


def remove_self_entered(db: Session, staff: User, character: Character, troupe: Troupe) -> None:
    """A correction for each self-entered entry, bringing it to nothing."""
    for entry, gives in self_entered_entries(db, character):
        if gives <= 0:
            continue
        db.add(
            XpEntry(
                character_id=character.id,
                kind="correction",
                amount=-gives,
                reason=f"Self-entered XP not accepted by {troupe.name}",
                entered_by=staff.id,
                corrects_id=entry.id,
            )
        )
    db.flush()


def remove_above_ceiling(
    db: Session, staff: User, character: Character, troupe: Troupe, amount: int, ceiling: int
) -> None:
    if amount <= 0:
        return
    db.add(
        XpEntry(
            character_id=character.id,
            kind="cap",
            amount=-amount,
            reason=f"XP above {troupe.name}'s ceiling of {ceiling}",
            entered_by=staff.id,
        )
    )
    db.flush()


def top_up(
    db: Session, staff: User, character: Character, troupe: Troupe, amount: int, floor: int
) -> None:
    if amount <= 0:
        return
    db.add(
        XpEntry(
            character_id=character.id,
            kind="award",
            amount=amount,
            reason=f"Top-up to {troupe.name}'s XP floor of {floor}",
            entered_by=staff.id,
        )
    )
    db.flush()


def give_extra(
    db: Session, staff: User, character: Character, troupe: Troupe, amount: int, reason: str
) -> None:
    if amount <= 0:
        return
    db.add(
        XpEntry(
            character_id=character.id,
            kind="award",
            amount=amount,
            reason=f"Extra XP on joining {troupe.name}" + (f": {reason}" if reason else ""),
            entered_by=staff.id,
        )
    )
    db.flush()
