"""Traits held by exception: asked of the home troupe's staff, or given by them.

Sometimes a character should have something the rules refuse, or have it at no
XP cost: a plot reward, a storyteller's ruling, a fix after a mistake. There
are two ways to it.

- **Asked.** The player puts the change in the cart as an exception line, saying
  why, and perhaps asking for it free. Spending the cart makes it at once, as if
  the checks it breaks were set to review for this one change: it waits on an
  approval of the kind "exception". Approving keeps it; approving a free request
  at normal cost keeps it but charges the XP; declining takes it back and
  refunds the XP, as for any held dots (`sheets.undo_discipline`).
- **Given.** A storyteller or assistant storyteller gives a trait, or raises
  one, free, despite the rules, or both, always with a reason. Staff are the
  approvers, so nothing waits; it is in the audit log, and the player is told.
  Approving a free request writes the same records as a Give.

Either way a `TraitException` is kept against the trait and the checks it
breaks, and `sheets.sheet_violations` leaves those checks out for that trait,
up to the rating it was given at. Any other check it breaks is still flagged,
and raising it further is judged as normal. It goes when the trait does.

Free dots are free dots (CONTEXT.md: Free Rating): a later raise is priced from
them, and the player cannot take them away for XP back. A free exception still
writes its line in the XP history, at 0 XP, with the reason, and owes no
downtime actions for learning.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, true
from sqlalchemy.orm import Session

from horatio import audit, notifications, sheets
from horatio.models import (
    Approval,
    Character,
    CharacterTrait,
    DisciplinePurchase,
    TraitCategory,
    TraitDefinition,
    TraitException,
    User,
    XpEntry,
)
from horatio.rules.checks import Violation
from horatio.sheets import SheetState, TraitKey, conflict, unprocessable


@dataclass(frozen=True)
class Ask:
    """A cart line asked as an exception: why, and whether at no XP cost."""

    reason: str
    free: bool = False


def checks_of(broken: Sequence[Violation]) -> list[dict[str, str]]:
    """The checks an exception sets aside, as it keeps them: once each."""
    found: dict[str, str] = {}
    for violation in broken:
        found.setdefault(violation.check.key, violation.message)
    return [{"key": key, "message": message} for key, message in found.items()]


def named(key: TraitKey) -> str:
    return f"{key[1]}: {key[2]}" if key[2] else key[1]


def can_ask(character: Character) -> None:
    """Refuse an exception line for a character no staff can approve it for."""
    if character.kind != "pc":
        raise conflict("An NPC is its staff's to build as they like; it needs no exception.")
    if character.home_troupe_id is None:
        raise conflict(
            "Only a home troupe's staff can make an exception; ask once the character has one."
        )


def spent_since(
    db: Session, character: Character, definition: TraitDefinition, xp_before: set[uuid.UUID]
) -> int:
    """XP spent on a trait since `xp_before`, the XP history's entries then."""
    return -sum(
        db.scalars(
            select(XpEntry.amount).where(
                XpEntry.character_id == character.id,
                XpEntry.trait_definition_id == definition.id,
                XpEntry.id.not_in(xp_before) if xp_before else true(),
            )
        )
    )


def ask(
    db: Session,
    player: User,
    character: Character,
    key: TraitKey,
    asked: Ask,
    broken: Sequence[Violation],
    before: SheetState,
    normal_cost: int | None,
) -> bool:
    """A change asked as an exception has been made: raise the approval it waits
    on, and keep the exception, so the checks it breaks are set aside for it
    while it waits. Says whether it did: not if the trait was not raised."""
    row = next((r for r in sheets.sheet_rows(db, character) if r.key == key), None)
    rating = (row.trait.rating or 0) if row else 0
    from_rating = before.ratings.get(key, 0)
    if row is None or rating <= from_rating:
        return False
    assert character.home_troupe_id is not None
    spent = spent_since(db, character, row.definition, before.xp)
    approval = Approval(
        character_id=character.id,
        troupe_id=character.home_troupe_id,
        kind="exception",
        requested_by=player.id,
        player_note=asked.reason,
    )
    db.add(approval)
    db.flush()
    db.add(
        DisciplinePurchase(
            approval_id=approval.id,
            trait_definition_id=row.definition.id,
            detail=row.trait.detail,
            from_rating=from_rating,
            to_rating=rating,
            cost=spent,
        )
    )
    db.add(
        TraitException(
            character_id=character.id,
            character_trait_id=row.trait.id,
            rating=rating,
            checks=checks_of(broken),
            free=asked.free,
            normal_cost=normal_cost if asked.free else spent,
            reason=asked.reason,
            requested_by=player.id,
            approval_id=approval.id,
        )
    )
    db.flush()
    audit.record(
        db,
        player,
        "approval.request",
        troupe_id=approval.troupe_id,
        character_id=character.id,
        approval_id=approval.id,
        kind="exception",
        name=named(key),
        rating=rating,
        free=asked.free,
        reason=asked.reason,
    )
    notifications.approval_waiting(db, approval)
    return True


def asked_for(db: Session, approval: Approval) -> TraitException | None:
    return db.scalar(select(TraitException).where(TraitException.approval_id == approval.id))


def approve_asked(
    db: Session, staff: User, character: Character, approval: Approval, at_cost: bool
) -> None:
    """Keep a trait asked for by exception. `at_cost`, for one asked free: charge
    the XP it costs at the normal price, refusing if the character lacks it."""
    bought = db.scalars(
        select(DisciplinePurchase).where(DisciplinePurchase.approval_id == approval.id)
    ).one()
    definition = db.get_one(TraitDefinition, bought.trait_definition_id)
    category = db.get_one(TraitCategory, definition.category_id)
    exception = asked_for(db, approval)
    if exception is None:
        raise conflict(f"{definition.name} is no longer on the sheet; decline this instead.")
    gained = bought.to_rating - bought.from_rating
    if at_cost:
        if not exception.free:
            raise unprocessable("This was not asked for free, so it is already at normal cost.")
        cost = exception.normal_cost
        if cost is None:
            raise conflict(
                f"{definition.name} has no normal cost under the troupe's rules: "
                "approve it free, or decline it."
            )
        balance = sheets.xp_balance(db, character)
        if balance < cost:
            raise conflict(
                f"At normal cost {definition.name} is {cost} XP, and {character.name} "
                f"has {balance}: approve it free, or decline it."
            )
        trait = db.get_one(CharacterTrait, exception.character_trait_id)
        trait.free_rating = max(0, trait.free_rating - gained)
        db.add(
            XpEntry(
                character_id=character.id,
                kind="purchase",
                amount=-cost,
                reason=f"{definition.name} {bought.from_rating} → {bought.to_rating}"
                ", by exception at normal cost",
                entered_by=staff.id,
                trait_definition_id=definition.id,
                detail=bought.detail or None,
                from_rating=bought.from_rating,
                to_rating=bought.to_rating,
                cost_basis={"exception": "at normal cost"},
            )
        )
        bought.cost = cost
        exception.free = False
    exception.given_by = staff.id
    exception.given_at = datetime.now(UTC)
    db.flush()
    if not exception.free:
        whole = definition.properties.get("rating") is not None
        actions = sheets.owed_for(db, character, category, gained, whole)
        doing = f"Gaining {definition.name}" if whole else f"Learning {definition.name}"
        sheets.owe(db, staff, character, actions, f"{doing} {bought.to_rating}")


@dataclass(frozen=True)
class Given:
    """What a Give did, or (as a trial) would do."""

    # XP it spends.
    cost: int
    # The checks it breaks, that it is given despite.
    breaks: list[str]
    # Why it cannot be given, if it cannot.
    refused: str | None


def give(
    db: Session,
    staff: User,
    character: Character,
    key: TraitKey,
    rating: int,
    *,
    free: bool,
    despite: bool,
    reason: str,
    trial: bool = False,
) -> Given:
    """Staff give a player's character a trait, or raise one, by exception: `free`
    at no XP cost, `despite` the checks it breaks. A `trial` only says what it
    would cost and break, and why it would be refused, saving nothing; otherwise a
    refusal is raised."""
    category, name, detail = key
    if character.kind != "pc":
        raise conflict("Set an NPC's ratings directly; it needs no exception.")
    if character.home_troupe_id is None:
        raise conflict("Only a home troupe's staff give a character traits.")
    before = sheets.sheet_state(db, character)
    balance = sheets.xp_balance(db, character)
    held = before.ratings.get(key, 0)
    if rating <= held:
        raise unprocessable(f"Give adds {name} or raises it; it is at {held}.")
    savepoint = db.begin_nested()
    try:
        change = sheets.set_trait(
            db,
            staff,
            character,
            category,
            name,
            detail,
            rating,
            free=reason if free else None,
            by_exception="given",
        )
        sheets.apply_grants(db, staff, character)
    except HTTPException as error:
        savepoint.rollback()
        if trial:
            return Given(cost=0, breaks=[], refused=str(error.detail))
        raise
    judged = sheets.broken_since(db, None, character, before, excepting=[key])
    broken = judged.excepted.get(key, [])
    refusals = [] if despite else [sheets.problem(v) for v in broken]
    refusals += judged.refused
    outcome = Given(
        cost=balance - sheets.xp_balance(db, character),
        breaks=[c["message"] for c in checks_of(broken)],
        refused=sheets.refusal(refusals) if refusals else None,
    )
    if trial or refusals:
        savepoint.rollback()
        db.expire_all()
        if refusals and not trial:
            raise conflict(outcome.refused or "")
        return outcome
    savepoint.commit()
    row = next(r for r in sheets.sheet_rows(db, character) if r.key == key)
    db.add(
        TraitException(
            character_id=character.id,
            character_trait_id=row.trait.id,
            rating=rating,
            checks=checks_of(broken),
            free=free,
            normal_cost=change.normal_cost if free else outcome.cost,
            reason=reason,
            requested_by=staff.id,
            given_by=staff.id,
            given_at=datetime.now(UTC),
        )
    )
    db.flush()
    audit.record(
        db,
        staff,
        "sheet.give",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        name=named(key),
        from_rating=held,
        rating=rating,
        free=free,
        cost=outcome.cost,
        breaks="; ".join(outcome.breaks) or "nothing",
        reason=reason,
    )
    notifications.notify(
        db,
        [character.player_id],
        "sheet.given",
        f"{staff.display_name} gave {character.name} {named(key)} {rating}"
        + (", free" if free else "")
        + f": {reason}",
        f"/characters/{character.id}",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
    )
    return outcome
