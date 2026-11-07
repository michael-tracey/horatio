"""What a downtime response does besides its words, applied by staff from the response
(issue #506). Storytellers and assistants choose an effect; undoing it there takes it
back.

- **Call of the Hungry Dead** (MET: VtM core p. 181): its target gains one action
  fewer the next time it gains downtime actions. It does not stack: a target already
  owing one, not yet taken off a downtime it has finished, cannot owe another;
- **an indirect influence attack** (p. 512), where the storyteller chooses the
  mechanical penalty: its target loses one downtime action for every 2 levels of the
  general influence action, or all it has. Both are owed actions on the target
  (horatio.downtimes.owe_actions), which come off its current downtime if it has not
  submitted, or else its next;
- **Crafts and Performance** (pp. 93, 96): two actions, one to make or promote and
  one to sell or perform, raise Resources or Fame by 1 for the month, even from none,
  to no more than 5. The boost lasts until the troupe's next cycle opens;
- **overtaxed Resources** (p. 103): Resources 2 lower, to no less than 0, for six
  games or three months, whichever is later; three downtime actions spent recovering
  halve both, once.

A raised or lowered background (BackgroundChange) shows on the sheet and the Play View
as "Resources 3 (+1 this month, Crafts)". It does not change the sheet, nor a
downtime allowance already worked out.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, get_args

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from horatio import audit, downtimes, influence
from horatio.influence_effects import games_since
from horatio.models import (
    AllowanceAdjustment,
    BackgroundChange,
    Character,
    CycleParticipant,
    DowntimeCycle,
    OwedAction,
    Troupe,
    User,
)
from horatio.renames import add_months
from horatio.responses import WorkItem
from horatio.sheets import conflict, rules_for, sheet_rows, unprocessable

Kind = Literal["hungry_dead", "indirect_attack", "crafts", "performance", "overtaxed", "recovery"]
KINDS: tuple[Kind, ...] = get_args(Kind)
# Effects on another character, chosen by staff; the rest are on the response's own.
AIMED = ("hungry_dead", "indirect_attack")

NAMES: dict[str, str] = {
    "hungry_dead": "Call of the Hungry Dead",
    "indirect_attack": "Indirect influence attack",
    "crafts": "Crafts",
    "performance": "Performance",
    "overtaxed": "Overtaxed",
    "recovery": "Recovering from overtaxing",
}
# What each raises or lowers, by how much, for the month or for a while.
BOOSTS = {"crafts": ("Resources", 1), "performance": ("Fame", 1)}
OVERTAXED = ("Resources", -2)
OVERTAXED_GAMES = 6
OVERTAXED_MONTHS = 3
HIGHEST = 5


def now() -> datetime:
    return datetime.now(UTC)


# --- how long a background change lasts -------------------------------------------------


@dataclass(frozen=True)
class Lasting:
    active: bool
    # Overtaxed: the games still to play, and when its time is up. None for a boost.
    games_left: int = 0
    ends_at: datetime | None = None


def games_needed(change: BackgroundChange) -> int:
    return -(-change.games // 2) if change.halved_by_response_id else change.games


def ends_at(change: BackgroundChange) -> datetime | None:
    if change.ends_at is None:
        return None
    if change.halved_by_response_id:
        return change.starts_at + (change.ends_at - change.starts_at) / 2
    return change.ends_at


def lasting(db: Session, change: BackgroundChange, at: datetime | None = None) -> Lasting:
    """A boost lasts until the troupe opens its next cycle; overtaxing until its games
    are played and its date has passed."""
    at = at or now()
    if change.ends_at is None:
        later = db.scalar(
            select(
                exists().where(
                    DowntimeCycle.troupe_id == change.troupe_id,
                    DowntimeCycle.opened_at > change.starts_at,
                    DowntimeCycle.opened_at <= at,
                )
            )
        )
        return Lasting(active=not later)
    played = games_since(db, change.character_id, change.troupe_id, change.starts_at, at)
    left = max(0, games_needed(change) - played)
    until = ends_at(change)
    assert until is not None
    return Lasting(active=left > 0 or at < until, games_left=left, ends_at=until)


@dataclass(frozen=True)
class Changed:
    """A background as it stands for now: "Resources 3 (+1 this month, Crafts)"."""

    trait: str
    rating: int
    now: int
    changes: list[tuple[BackgroundChange, Lasting]]


def changed(db: Session, character: Character) -> list[Changed]:
    """The character's backgrounds raised or lowered for now, each with its rating on
    the sheet and as it stands."""
    held = [
        (c, h)
        for c in db.scalars(
            select(BackgroundChange)
            .where(BackgroundChange.character_id == character.id)
            .order_by(BackgroundChange.starts_at)
        )
        if (h := lasting(db, c)).active
    ]
    if not held:
        return []
    ratings = {
        row.definition.name: row.trait.rating or 0
        for row in sheet_rows(db, character)
        if row.category.key == "backgrounds"
    }
    found: list[Changed] = []
    for trait in dict.fromkeys(c.trait for c, _ in held):
        mine = [(c, h) for c, h in held if c.trait == trait]
        rating = ratings.get(trait, 0)
        moved = rating + sum(c.delta for c, _ in mine)
        found.append(Changed(trait, rating, max(0, min(HIGHEST, moved)), mine))
    return found


# --- applying them from a response ------------------------------------------------------


@dataclass(frozen=True)
class Applied:
    """An effect applied from a response, as staff see it there."""

    id: uuid.UUID
    kind: str
    character_name: str
    text: str


def target_choices(db: Session, troupe: Troupe) -> list[Character]:
    """Who an effect on another character can be aimed at: the troupe's active player
    characters, whose downtimes it runs."""
    return list(
        db.scalars(
            select(Character)
            .where(
                Character.home_troupe_id == troupe.id,
                Character.kind == "pc",
                Character.status == "active",
            )
            .order_by(Character.name)
        )
    )


def indirect_cost(db: Session, item: WorkItem) -> int | None:
    """What an indirect attack through this general influence action costs its target:
    one action for every 2 levels (p. 512). None for an answer that is not one."""
    influence_type = influence.type_of(item.question.action_kind)
    if influence_type is None:
        return None
    action = influence.answer_action(
        rules_for(db, item.character), influence_type, item.answer.structured
    )
    if action is None or not action.general or action.level is None:
        return None
    return action.level // 2


def hungry_dead_owed(db: Session, target: Character) -> bool:
    """The target owes Call of the Hungry Dead's action still: not taken off yet, or
    taken off a downtime still open."""
    return (
        db.scalar(
            select(OwedAction.id)
            .outerjoin(CycleParticipant, OwedAction.participant_id == CycleParticipant.id)
            .outerjoin(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
            .where(
                OwedAction.character_id == target.id,
                OwedAction.source == "hungry_dead",
                OwedAction.participant_id.is_(None) | DowntimeCycle.status.in_(("draft", "open")),
            )
            .limit(1)
        )
        is not None
    )


def overtaxed_now(db: Session, character: Character) -> BackgroundChange | None:
    """The character's overtaxed Resources still recovering, the latest first."""
    for change in db.scalars(
        select(BackgroundChange)
        .where(
            BackgroundChange.character_id == character.id, BackgroundChange.source == "overtaxed"
        )
        .order_by(BackgroundChange.starts_at.desc())
    ):
        if lasting(db, change).active:
            return change
    return None


def apply(
    db: Session,
    actor: User,
    troupe: Troupe,
    item: WorkItem,
    kind: Kind,
    target_id: uuid.UUID | None = None,
) -> None:
    character = item.character
    response_id = item.response.id
    if kind in AIMED:
        target = db.get(Character, target_id) if target_id else None
        if target is None or target not in target_choices(db, troupe):
            raise unprocessable("Choose a character of this troupe.")
        if kind == "hungry_dead":
            if hungry_dead_owed(db, target):
                raise conflict(
                    f"{target.name} already loses an action to Call of the Hungry Dead; "
                    "it doesn't stack."
                )
            amount, reason = 1, "Call of the Hungry Dead against you"
        else:
            cost = indirect_cost(db, item)
            if cost is None:
                raise unprocessable("Only a general influence action makes an indirect attack.")
            if cost == 0:
                raise unprocessable("A level-1 action costs its target no actions.")
            amount, reason = cost, "Indirect influence attack against you"
        downtimes.owe_actions(
            db, actor, target, amount, reason, source=kind, response_id=response_id
        )
        what, subject = f"{NAMES[kind]} (−{amount})", target
    elif kind in BOOSTS:
        trait, delta = BOOSTS[kind]
        db.add(
            BackgroundChange(
                character_id=character.id,
                troupe_id=troupe.id,
                trait=trait,
                delta=delta,
                source=kind,
                response_id=response_id,
                starts_at=now(),
                added_by=actor.id,
            )
        )
        what, subject = f"{NAMES[kind]}: {trait} +{delta} this month", character
    elif kind == "overtaxed":
        trait, delta = OVERTAXED
        starts = now()
        db.add(
            BackgroundChange(
                character_id=character.id,
                troupe_id=troupe.id,
                trait=trait,
                delta=delta,
                source=kind,
                response_id=response_id,
                starts_at=starts,
                games=OVERTAXED_GAMES,
                ends_at=datetime.combine(
                    add_months(starts.date(), OVERTAXED_MONTHS), starts.timetz()
                ),
                added_by=actor.id,
            )
        )
        what, subject = f"Overtaxed Resources ({delta})", character
    else:
        change = overtaxed_now(db, character)
        if change is None:
            raise unprocessable(f"{character.name}'s Resources are not recovering from overtaxing.")
        if change.halved_by_response_id is not None:
            raise conflict("Its recovery is already halved.")
        change.halved_by_response_id = response_id
        what, subject = "Recovering from overtaxing (the wait halved)", character
    db.flush()
    audit.record(
        db,
        actor,
        "downtime.effect_applied",
        troupe_id=troupe.id,
        character_id=subject.id,
        what=what,
    )


def applied(db: Session, item: WorkItem) -> list[Applied]:
    """The effects applied from this response."""
    response_id = item.response.id
    found: list[Applied] = []
    for debt, name in db.execute(
        select(OwedAction, Character.name)
        .join(Character, OwedAction.character_id == Character.id)
        .where(OwedAction.response_id == response_id)
        .order_by(OwedAction.created_at)
    ):
        kind = debt.source or ""
        found.append(
            Applied(debt.id, kind, name, f"{NAMES.get(kind, kind)}: {name} −{debt.amount}")
        )
    for change in db.scalars(
        select(BackgroundChange)
        .where(
            (BackgroundChange.response_id == response_id)
            | (BackgroundChange.halved_by_response_id == response_id)
        )
        .order_by(BackgroundChange.created_at)
    ):
        name = item.character.name
        if change.response_id != response_id:
            text = "Recovering from overtaxing: the wait halved"
            found.append(Applied(change.id, "recovery", name, text))
        elif change.source == "overtaxed":
            text = f"Overtaxed: {change.trait} {change.delta} for six games or three months"
            found.append(Applied(change.id, "overtaxed", name, text))
        else:
            text = f"{NAMES[change.source]}: {change.trait} +{change.delta} this month"
            found.append(Applied(change.id, change.source, name, text))
    return found


def remove(db: Session, actor: User, troupe: Troupe, item: WorkItem, effect_id: uuid.UUID) -> None:
    """Take back an effect applied from this response: owed actions given back, a
    background put back, or the recovery's wait no longer halved."""
    response_id = item.response.id
    debt = db.get(OwedAction, effect_id)
    if debt is not None and debt.response_id == response_id:
        for adjustment in db.scalars(
            select(AllowanceAdjustment).where(AllowanceAdjustment.owed_action_id == debt.id)
        ):
            db.delete(adjustment)
        what = f"{NAMES.get(debt.source or '', 'Owed actions')} (−{debt.amount})"
        subject_id = debt.character_id
        db.delete(debt)
    else:
        change = db.get(BackgroundChange, effect_id)
        if change is None:
            raise unprocessable("No such effect on this response.")
        subject_id = change.character_id
        if change.halved_by_response_id == response_id and change.response_id != response_id:
            change.halved_by_response_id = None
            what = "Recovering from overtaxing (the wait halved)"
        elif change.response_id == response_id:
            what = f"{NAMES[change.source]}: {change.trait} {change.delta:+d}"
            db.delete(change)
        else:
            raise unprocessable("No such effect on this response.")
    db.flush()
    audit.record(
        db,
        actor,
        "downtime.effect_removed",
        troupe_id=troupe.id,
        character_id=subject_id,
        what=what,
    )
