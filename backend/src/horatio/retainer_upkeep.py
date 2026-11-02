"""Retainer upkeep and growth (issue #442): house rules some troupes play, each off
unless the troupe switches it on under Customise › Rules › Retainers. The book has
neither.

Upkeep is an amount of Blood or Willpower for each Retainer (or each ghoul Retainer
only), a game or a month. A game's is taken as the character's night begins on the
Play View: at check-in (horatio.checkin), or else at the night's first tap
(horatio.play). A month's is taken at the first game of the calendar month, or is
charged as a downtime cycle closes and taken as the next night begins, as the troupe
chooses. Each is its own line in the night's log: "Retainer upkeep: −2 Blood".
Each Retainer is paid for in full or not at all, from what the night starts with; one
the character can't pay for is marked neglected, and staff are told. What follows is
the troupe's call, so nothing is lost by itself, and staff clear the mark.

Growth is XP a month for each Retainer, given as a downtime cycle closes, once for
each calendar month: to the NPC linked to the Retainer, on that NPC's XP, where staff
spend it; or banked on the Retainer, with a ledger, while none is.

A lost Retainer (core p. 104, horatio.retainers) pays no upkeep and gains nothing
while its dots are away.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, notifications, play, retainers
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    PlayEvent,
    PlayGame,
    Retainer,
    RetainerGrowth,
    Troupe,
    User,
    XpEntry,
)
from horatio.permissions import TroupeAction

Pool = Literal["blood", "willpower"]
POOL_WORDS: dict[str, str] = {"blood": "Blood", "willpower": "Willpower"}
# The most upkeep a Retainer, and the most XP a month.
MOST_UPKEEP = 10
MOST_GROWTH = 20
# Server-made lines go just before the night's first tap.
BEFORE_FIRST_TAP = timedelta(milliseconds=1)


@dataclass(frozen=True)
class Upkeep:
    amount: int
    pool: Pool
    ghouls_only: bool = False
    # "game", taken as each night begins, or "month".
    per: Literal["game", "month"] = "game"
    # A month's: taken at the month's first "game", or charged at a "downtime" cycle's close.
    month_at: Literal["game", "downtime"] = "game"

    def each(self) -> str:
        """ "1 Blood a game", for a Retainer's card."""
        return f"{self.amount} {POOL_WORDS[self.pool]} a {self.per}"

    def text(self) -> str:
        whom = "each ghoul Retainer" if self.ghouls_only else "each Retainer"
        if self.per == "game":
            when = "a game, taken as the night starts"
        elif self.month_at == "game":
            when = "a month, taken at the month's first game"
        else:
            when = "a month, charged as a downtime cycle closes and taken at the next game"
        return f"{self.amount} {POOL_WORDS[self.pool]} for {whom} {when}"


@dataclass(frozen=True)
class Rules:
    upkeep: Upkeep | None = None
    # XP a month for each Retainer.
    growth: int | None = None

    def growth_text(self) -> str | None:
        if not self.growth:
            return None
        return f"{self.growth} XP a month for each Retainer, given as a downtime cycle closes"


def rules_of(troupe: Troupe | None) -> Rules:
    stored: dict[str, Any] = troupe.retainer_rules if troupe is not None else {}
    found = stored.get("upkeep")
    return Rules(
        upkeep=Upkeep(
            amount=int(found["amount"]),
            pool=found["pool"],
            ghouls_only=bool(found.get("ghouls_only")),
            per=found.get("per", "game"),
            month_at=found.get("month_at", "game"),
        )
        if found
        else None,
        growth=int(stored["growth"]) if stored.get("growth") else None,
    )


def set_rules(db: Session, staff: User, troupe: Troupe, rules: Rules) -> None:
    if rules_of(troupe) == rules:
        return
    upkeep = rules.upkeep
    troupe.retainer_rules = {
        **(
            {
                "upkeep": {
                    "amount": upkeep.amount,
                    "pool": upkeep.pool,
                    "ghouls_only": upkeep.ghouls_only,
                    "per": upkeep.per,
                    "month_at": upkeep.month_at if upkeep.per == "month" else "game",
                }
            }
            if upkeep
            else {}
        ),
        **({"growth": rules.growth} if rules.growth else {}),
    }
    db.flush()
    audit.record(
        db,
        staff,
        "house.retainer_rules",
        troupe_id=troupe.id,
        upkeep=upkeep.text() if upkeep else "none",
        growth=rules.growth_text() or "none",
    )


def house_settings(troupe: Troupe) -> list[tuple[str, str, str]]:
    """The rules switched on, for the House rules tab: name, how it is played, the book."""
    rules = rules_of(troupe)
    found: list[tuple[str, str, str]] = []
    if rules.upkeep:
        found.append(("Retainer upkeep", rules.upkeep.text(), "No upkeep"))
    if growth := rules.growth_text():
        found.append(("Retainer growth", growth, "Retainers don't gain XP"))
    return found


# --- who pays ---------------------------------------------------------------------------


def lost(listed: retainers.Listed, today: date) -> bool:
    """Lost, with its dots away (p. 104)."""
    row = listed.row
    return bool(row and row.lost) and (listed.back is None or listed.back.away(today))


def pays(listed: retainers.Listed, upkeep: Upkeep, today: date) -> bool:
    return not lost(listed, today) and (listed.ghoul or not upkeep.ghouls_only)


def label(listed: retainers.Listed) -> str:
    if listed.name:
        return listed.name
    return f"{listed.given.kind} not yet named" if listed.given else "A Retainer not yet named"


def troupe_of(db: Session, character: Character) -> Troupe | None:
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    return db.get(Troupe, troupe_id) if troupe_id else None


def kept_row(db: Session, character: Character, listed: retainers.Listed) -> Retainer | None:
    """Its row, made for one with nothing kept yet; None for one held without a name,
    which has nothing kept for it until it is named."""
    if listed.row is not None:
        return listed.row
    if listed.given is not None:
        row = Retainer(
            character_id=character.id,
            name="",
            dots=listed.given.dots,
            from_merit=listed.given.merit,
            ghoul=listed.given.ghoul,
            position=len(retainers.rows(db, character)),
        )
    elif listed.bought and listed.name:
        row = Retainer(
            character_id=character.id,
            name=listed.name,
            dots=listed.dots,
            position=len(retainers.rows(db, character)),
        )
    else:
        return None
    db.add(row)
    db.flush()
    return row


@dataclass
class Judged:
    """Upkeep worked out for one character: who is paid for, and who is not."""

    pool: Pool
    amount: int
    paid: list[str] = field(default_factory=list[str])
    neglected: list[retainers.Listed] = field(default_factory=list[retainers.Listed])

    @property
    def total(self) -> int:
        return self.amount * len(self.paid)


def judge(
    listed: Sequence[retainers.Listed], upkeep: Upkeep, available: int, today: date
) -> Judged:
    """Pay for each Retainer in turn, in full, while what the night starts with lasts."""
    judged = Judged(upkeep.pool, upkeep.amount)
    for entry in listed:
        if not pays(entry, upkeep, today):
            continue
        if available >= upkeep.amount:
            available -= upkeep.amount
            judged.paid.append(label(entry))
        else:
            judged.neglected.append(entry)
    return judged


def neglect(
    db: Session,
    actor: User,
    character: Character,
    judged: Judged,
    today: date,
) -> list[str]:
    """Mark the Retainers not paid for as neglected, and tell staff; their names."""
    names = [label(e) for e in judged.neglected]
    if not names:
        return names
    for entry in judged.neglected:
        row = kept_row(db, character, entry)
        if row is not None and row.neglected_on is None:
            row.neglected_on = today
    troupe = troupe_of(db, character)
    cost = f"{judged.amount} {POOL_WORDS[judged.pool]}"
    for name in names:
        audit.record(
            db,
            actor,
            "retainer.neglected",
            troupe_id=troupe.id if troupe else None,
            character_id=character.id,
            name=name,
            cost=cost,
        )
    if troupe is not None:
        whom = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        notifications.notify(
            db,
            notifications.staff_for(db, troupe, TroupeAction.APPROVE_CHANGES),
            "retainer.neglected",
            f"{character.name} couldn't pay {cost} upkeep for {whom}: neglected",
            f"/characters/{character.id}",
            troupe_id=troupe.id,
            character_id=character.id,
        )
    db.flush()
    return names


# --- the night ---------------------------------------------------------------------------


def month_start(at: datetime) -> datetime:
    return datetime.combine(at.astimezone(UTC).date().replace(day=1), time(), UTC)


def paid_this_month(db: Session, character: Character, at: datetime) -> bool:
    """A month's upkeep was taken already in the calendar month of `at`."""
    return (
        db.scalar(
            select(PlayEvent.id)
            .join(PlayGame, PlayEvent.game_id == PlayGame.id)
            .where(
                PlayGame.character_id == character.id,
                PlayEvent.upkeep["per"].astext == "month",
                PlayEvent.happened_at >= month_start(at),
            )
            .limit(1)
        )
        is not None
    )


def begin(db: Session, character: Character, actor: User, game: PlayGame, *, at: datetime) -> None:
    """Take the night's upkeep as `game` begins, once: a game's, a month's at its first
    game, and what a downtime charged. `at` is when the night began; the lines go
    just before it. The caller holds the character's lock."""
    if game.upkeep is not None or game.ended_at is not None:
        return
    game.upkeep = {}
    charged: list[dict[str, Any]] = (character.upkeep_next_game or {}).get("charges", [])
    character.upkeep_next_game = None
    upkeep = rules_of(troupe_of(db, character)).upkeep
    due = upkeep is not None and (
        upkeep.per == "game"
        or (upkeep.month_at == "game" and not paid_this_month(db, character, at))
    )
    if not due and not charged:
        return
    limits = play.limits(db, character, game)
    start = limits.start()
    available = {pool: start[pool] for pool in POOL_WORDS if limits.most(pool) is not None}
    when = at - BEFORE_FIRST_TAP
    taken: list[dict[str, Any]] = []

    def line(kind: str, pool: str, amount: int, facts: dict[str, Any]) -> None:
        db.add(
            PlayEvent(
                game_id=game.id,
                client_id=uuid.uuid4(),
                actor_id=actor.id,
                happened_at=when,
                kind=kind,
                tracker=pool if kind == "change" else "",
                amount=-amount if kind == "change" else 0,
                upkeep=facts,
            )
        )

    for charge in charged:
        pool, amount = charge["pool"], int(charge["amount"])
        if pool not in available or amount <= 0:
            continue
        line("change", pool, amount, {"per": "downtime", "retainers": charge["retainers"]})
        available[pool] = max(0, available[pool] - amount)
        taken.append({"pool": pool, "amount": amount, "per": "downtime"})
    if due and upkeep is not None and upkeep.pool in available:
        # The day as the server has it, as for when a lost Retainer's dots are back.
        today = date.today()
        judged = judge(retainers.read(db, character), upkeep, available[upkeep.pool], today)
        if judged.paid:
            facts = {"per": upkeep.per, "retainers": judged.paid}
            line("change", upkeep.pool, judged.total, facts)
            taken.append({"pool": upkeep.pool, "amount": judged.total, "per": upkeep.per})
        neglected = neglect(db, actor, character, judged, today)
        if neglected:
            line("note", upkeep.pool, 0, {"per": upkeep.per, "retainers": neglected})
            game.upkeep = {"neglected": neglected}
    if taken:
        game.upkeep = {**game.upkeep, "taken": taken}
    db.flush()
    play.refresh(db, game, limits)


# --- a downtime cycle's close -----------------------------------------------------------


def cycle_closed(db: Session, staff: User, cycle: DowntimeCycle) -> None:
    """Charge a month's upkeep kept as a downtime cost, and give each Retainer its
    month's growth, for each character taking part in the cycle."""
    troupe = db.get(Troupe, cycle.troupe_id)
    rules = rules_of(troupe)
    upkeep = rules.upkeep
    charges = upkeep is not None and upkeep.per == "month" and upkeep.month_at == "downtime"
    if not charges and not rules.growth:
        return
    today = date.today()
    ids = db.scalars(
        select(CycleParticipant.character_id)
        .where(CycleParticipant.cycle_id == cycle.id)
        .order_by(CycleParticipant.id)
    )
    for character_id in list(ids):
        character = db.get(Character, character_id, with_for_update=True)
        if character is None:
            continue
        listed = retainers.read(db, character)
        if not listed:
            continue
        if charges and upkeep is not None:
            charge(db, staff, cycle, character, listed, upkeep, today)
        if rules.growth:
            grow(db, staff, cycle, character, listed, rules.growth, today)
    db.flush()


def charge(
    db: Session,
    staff: User,
    cycle: DowntimeCycle,
    character: Character,
    listed: Sequence[retainers.Listed],
    upkeep: Upkeep,
    today: date,
) -> None:
    """The month's upkeep as a downtime cost: judged against what the next game starts
    with, and taken from it as that night begins."""
    game = play.current_game(db, character)
    untouched = game is not None and game.upkeep is None and not play.game_events(db, game)
    limits = play.limits(db, character, game if untouched else None)
    if limits.most(upkeep.pool) is None:
        return
    kept: list[dict[str, Any]] = (character.upkeep_next_game or {}).get("charges", [])
    owed = sum(int(c["amount"]) for c in kept if c["pool"] == upkeep.pool)
    available = max(0, limits.start()[upkeep.pool] - owed)
    judged = judge(listed, upkeep, available, today)
    if judged.paid:
        kept = [
            *kept,
            {"pool": upkeep.pool, "amount": judged.total, "retainers": judged.paid},
        ]
        character.upkeep_next_game = {"charges": kept}
        troupe = troupe_of(db, character)
        audit.record(
            db,
            staff,
            "retainer.upkeep_charged",
            troupe_id=troupe.id if troupe else None,
            character_id=character.id,
            amount=f"{judged.total} {POOL_WORDS[upkeep.pool]}",
            cycle=cycle.name,
        )
    neglect(db, staff, character, judged, today)


def grow(
    db: Session,
    staff: User,
    cycle: DowntimeCycle,
    character: Character,
    listed: Sequence[retainers.Listed],
    xp: int,
    today: date,
) -> None:
    """Each Retainer's month of growth, once a calendar month: on its NPC, or banked."""
    month = today.replace(day=1)
    troupe = troupe_of(db, character)
    for entry in listed:
        if lost(entry, today):
            continue
        row = kept_row(db, character, entry)
        if row is None:
            continue
        given = db.scalar(
            select(RetainerGrowth.id).where(
                RetainerGrowth.retainer_id == row.id, RetainerGrowth.month == month
            )
        )
        if given is not None:
            continue
        npc = db.get(Character, row.npc_id) if row.npc_id else None
        award: XpEntry | None = None
        if npc is not None:
            award = XpEntry(
                character_id=npc.id,
                kind="award",
                amount=xp,
                reason=f"Retainer growth: {cycle.name}",
                entered_by=staff.id,
            )
            db.add(award)
            db.flush()
        db.add(
            RetainerGrowth(
                retainer_id=row.id,
                cycle_id=cycle.id,
                month=month,
                amount=xp,
                banked=npc is None,
                npc_id=npc.id if npc else None,
                xp_entry_id=award.id if award else None,
            )
        )
        audit.record(
            db,
            staff,
            "retainer.grew",
            troupe_id=troupe.id if troupe else None,
            character_id=character.id,
            name=label(entry),
            xp=xp,
            where=f"on {npc.name}" if npc else "banked",
        )
    db.flush()


def banked(db: Session, retainer_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    """XP banked on each Retainer, given while no NPC was linked to it."""
    if not retainer_ids:
        return {}
    rows = db.execute(
        select(RetainerGrowth.retainer_id, func.sum(RetainerGrowth.amount))
        .where(RetainerGrowth.retainer_id.in_(retainer_ids), RetainerGrowth.banked)
        .group_by(RetainerGrowth.retainer_id)
    )
    return {retainer_id: int(total or 0) for retainer_id, total in rows}


def clear_neglect(db: Session, staff: User, character: Character, row: Retainer) -> None:
    if row.neglected_on is None:
        return
    row.neglected_on = None
    troupe = troupe_of(db, character)
    audit.record(
        db,
        staff,
        "retainer.neglect_cleared",
        troupe_id=troupe.id if troupe else None,
        character_id=character.id,
        name=row.name or "A Retainer not yet named",
    )
    db.flush()
