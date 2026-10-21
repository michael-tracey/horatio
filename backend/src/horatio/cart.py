"""A cart of sheet changes, spent together: all of them, or none.

A player gathers raises, lowers, new traits, swaps and creation picks on the
Sheet tab, and spends them in one go. Each change is made by the same code as
making it alone (`sheets.set_trait`, `sheets.change_choice`, the creation
picks), in order, as if the earlier ones had been made, so costs and checks are
the same either way and each keeps its own XP entry. A refused change is rolled
back to its own savepoint and the rest are still tried, so every refusal is
found at once; the caller then keeps all of them or none.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import creation, sheets
from horatio.models import Approval, Character, CharacterTrait, User


@dataclass(frozen=True)
class SetRating:
    """Add a trait, change its rating, or (at 0) remove it, as `PUT /traits`."""

    category: str
    name: str
    detail: str
    rating: int | None
    # The rating the cart was made from: refused if the sheet has moved on since.
    from_rating: int | None = None
    teacher: str = ""


@dataclass(frozen=True)
class Swap:
    """Swap a focus (or another swappable choice) for another, as `POST /traits/change`."""

    category: str
    from_name: str
    to_name: str


@dataclass(frozen=True)
class Pick:
    """Place a creation pick."""

    category: str
    name: str
    detail: str
    rating: int


@dataclass(frozen=True)
class Unpick:
    """Take a creation pick back."""

    category: str
    name: str
    detail: str


Change = SetRating | Swap | Pick | Unpick


@dataclass(frozen=True)
class Outcome:
    # XP the change spends (negative: refunds). For a refused change, what it
    # would have cost where that can be told, else None.
    cost: int | None
    # Why it was refused; None if it went through.
    refused: str | None = None
    # It went through but waits on the home troupe, like a discipline dot.
    needs_approval: bool = False


def held_rating(db: Session, character: Character, change: SetRating) -> int:
    definition, _ = sheets.find_definition(db, character, change.category, change.name)
    rating = db.scalar(
        select(CharacterTrait.rating).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == change.detail,
        )
    )
    return rating or 0


def make(db: Session, user: User, character: Character, change: Change) -> None:
    """Make one change, exactly as its own endpoint does."""
    if isinstance(change, SetRating):
        if change.from_rating is not None:
            now = held_rating(db, character, change)
            if now != change.from_rating:
                raise sheets.conflict(
                    f"{change.name} is at {now} now, not {change.from_rating}: "
                    "the sheet has changed since this went in the cart."
                )
        with sheets.checked(db, character, user):
            sheets.set_trait(
                db,
                user,
                character,
                change.category,
                change.name,
                change.detail,
                change.rating,
                teacher=change.teacher,
            )
    elif isinstance(change, Swap):
        with sheets.checked(db, character, user):
            sheets.change_choice(
                db, user, character, change.category, change.from_name, change.to_name
            )
    elif isinstance(change, Pick):
        with sheets.checked(db, character, user):
            creation.place_pick(
                db, user, character, change.category, change.name, change.detail, change.rating
            )
    else:
        creation.remove_pick(db, user, character, change.category, change.name, change.detail)


def would_cost(db: Session, character: Character, change: Change) -> int | None:
    """What a refused change would have cost, where that can be told."""
    try:
        if isinstance(change, SetRating):
            quote, _ = sheets.quote_change(
                db, character, change.category, change.name, change.detail, change.rating
            )
            return quote.cost if quote else 0
        if isinstance(change, Swap):
            _, category = sheets.find_definition(db, character, change.category, change.from_name)
            return category.change_cost
    except HTTPException:
        return None
    return 0


def waiting(db: Session, character: Character) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.character_id == character.id,
                Approval.status == "pending",
                Approval.kind.in_(("discipline", "review")),
            )
        )
        or 0
    )


def apply_changes(
    db: Session, user: User, character: Character, changes: Sequence[Change]
) -> list[Outcome]:
    """Make each change in turn, each as if the ones before it had been made.
    A refused change is undone and the rest still tried. Nothing is committed:
    the caller keeps the lot, or rolls it back if any was refused."""
    outcomes: list[Outcome] = []
    for change in changes:
        balance = sheets.xp_balance(db, character)
        held = waiting(db, character)
        savepoint = db.begin_nested()
        try:
            make(db, user, character, change)
            db.flush()
        except HTTPException as error:
            savepoint.rollback()
            db.expire_all()
            refused = str(error.detail)
            outcomes.append(Outcome(cost=would_cost(db, character, change), refused=refused))
            continue
        savepoint.commit()
        outcomes.append(
            Outcome(
                cost=balance - sheets.xp_balance(db, character),
                needs_approval=waiting(db, character) > held,
            )
        )
    return outcomes
