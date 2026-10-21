"""Spending a cart of sheet changes: all of them in one transaction, or none."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import cart, sheets
from horatio.api.sheets import players_character
from horatio.auth.deps import CurrentUser, DbSession

router = APIRouter(prefix="/characters/{character_id}", tags=["sheets"])


class SetChangeIn(BaseModel):
    """Add a trait, change its rating, or (at 0) remove it, as `PUT /traits`."""

    kind: Literal["set"]
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    rating: int | None = Field(default=None, ge=0)
    # The rating the cart was made from: refused if the sheet has moved on since.
    from_rating: int | None = Field(default=None, ge=0)
    teacher: str = Field(default="", max_length=200)


class SwapChangeIn(BaseModel):
    """Swap a focus (or another swappable choice), as `POST /traits/change`."""

    kind: Literal["swap"]
    category: str
    from_name: str
    to_name: str


class PickChangeIn(BaseModel):
    """Place a creation pick, as `PUT /creation/picks`."""

    kind: Literal["pick"]
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    rating: int = Field(default=1, ge=1)


class UnpickChangeIn(BaseModel):
    """Take a creation pick back, as `POST /creation/picks/remove`."""

    kind: Literal["unpick"]
    category: str
    name: str
    detail: str = ""


CartChangeIn = Annotated[
    SetChangeIn | SwapChangeIn | PickChangeIn | UnpickChangeIn, Field(discriminator="kind")
]


class CartIn(BaseModel):
    changes: list[CartChangeIn] = Field(min_length=1, max_length=100)
    # Price the changes and find any refusals, saving nothing.
    dry_run: bool = False


class CartLineOut(BaseModel):
    # XP the change spends (negative: refunds). For a refused change, what it
    # would have cost where that can be told.
    cost: int | None
    # Why the change is refused; null if it can be made.
    refused: str | None
    # Made, but waiting on the home troupe's approval.
    needs_approval: bool


class CartOut(BaseModel):
    # Whether the changes were made: never on a dry run, nor if any was refused.
    applied: bool
    # The character's XP before the changes.
    balance: int
    # One per change, in the order given.
    lines: list[CartLineOut]


def to_change(change: CartChangeIn) -> cart.Change:
    match change:
        case SetChangeIn():
            return cart.SetRating(
                change.category,
                change.name,
                change.detail,
                change.rating,
                change.from_rating,
                change.teacher,
            )
        case SwapChangeIn():
            return cart.Swap(change.category, change.from_name, change.to_name)
        case PickChangeIn():
            return cart.Pick(change.category, change.name, change.detail, change.rating)
        case UnpickChangeIn():
            return cart.Unpick(change.category, change.name, change.detail)


@router.post("/cart")
def spend_cart(character_id: uuid.UUID, body: CartIn, db: DbSession, user: CurrentUser) -> CartOut:
    """Make a list of sheet changes in one transaction, each priced as if the
    earlier ones had been made, and the sheet they end with checked against the
    one they started from. If any is refused, none is made, and each line says
    what it costs or why it is refused. A dry run says the same, saving nothing."""
    character = players_character(db, user, character_id)
    balance = sheets.xp_balance(db, character)
    savepoint = db.begin_nested()
    outcomes = cart.apply_changes(db, user, character, [to_change(c) for c in body.changes])
    applied = not body.dry_run and all(o.refused is None for o in outcomes)
    if applied:
        savepoint.commit()
        db.commit()
    else:
        savepoint.rollback()
    return CartOut(
        applied=applied,
        balance=balance,
        lines=[
            CartLineOut(cost=o.cost, refused=o.refused, needs_approval=o.needs_approval)
            for o in outcomes
        ],
    )
