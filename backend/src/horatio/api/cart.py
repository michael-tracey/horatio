"""Spending a cart of sheet changes: all of them in one transaction, or none. And
what the sheet the cart would leave could take next."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import cart, sheets
from horatio.api.sheets import FreePickIn, players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import visible_character
from horatio.trait_exceptions import Ask

router = APIRouter(prefix="/characters/{character_id}", tags=["sheets"])


class ExceptionIn(BaseModel):
    """A change asked of the home troupe's staff as an exception to the rules."""

    # Why: one line, always given.
    reason: str = Field(min_length=1, max_length=500)
    # Asked for at no XP cost; the reason says why (a plot reward, a ruling).
    free: bool = False


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
    # Asked as an exception: made at once, waiting on the home troupe's staff.
    exception: ExceptionIn | None = None
    # For a merit that gives free traits the player chooses: their choices, made with it.
    picks: list[FreePickIn] = Field(default=[], max_length=20)


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


class RepricedOut(BaseModel):
    """An earlier purchase a Generation change reprices."""

    # The purchase: "Brawl 0 → 2".
    purchase: str
    # What it costs more (negative: less) at the new Generation.
    cost: int


class CartLineOut(BaseModel):
    # XP the change spends (negative: refunds). For a refused change, what it
    # would have cost where that can be told.
    cost: int | None
    # Why the change is refused; null if it can be made.
    refused: str | None
    # Made, but waiting on the home troupe's approval.
    needs_approval: bool
    # Asked as an exception: the rules it breaks, set aside if staff approve.
    breaks: list[str] = []
    # Earlier purchases it reprices, each its own line in the XP history; their
    # total is in `cost`.
    repriced: list[RepricedOut] = []


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
                Ask(change.exception.reason.strip(), change.exception.free)
                if change.exception
                else None,
                tuple(p.to_rules() for p in change.picks),
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
            CartLineOut(
                cost=o.cost,
                refused=o.refused,
                needs_approval=o.needs_approval,
                breaks=list(o.breaks),
                repriced=[RepricedOut(purchase=r.label, cost=r.cost) for r in o.repriced],
            )
            for o in outcomes
        ],
    )


class UnavailableIn(BaseModel):
    categories: list[str] = Field(min_length=1, max_length=20)
    # The cart's changes, as they would be spent.
    changes: list[CartChangeIn] = Field(default_factory=list[CartChangeIn], max_length=100)


@router.post("/unavailable")
def unavailable_after(
    character_id: uuid.UUID, body: UnavailableIn, db: DbSession, user: CurrentUser
) -> dict[str, dict[str, str]]:
    """For each category, the traits the character cannot take, and why, with the
    sheet as the cart's changes would leave it: a discipline dot in the cart opens
    the techniques that need it straight away. Nothing is saved."""
    character = visible_character(db, user, character_id)
    rules = sheets.rules_for(db, character)
    unknown = next((c for c in body.categories if c not in rules.rule_set.categories), None)
    if unknown is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No category {unknown!r}.")
    sheet = [r.as_rules_trait() for r in sheets.sheet_rows(db, character)]
    planned = cart.planned(sheet, [to_change(c) for c in body.changes])
    return {
        category: sheets.unavailable(db, character, category, planned=planned)
        for category in dict.fromkeys(body.categories)
    }
