"""Joining and leaving troupes, and asking for a home troupe."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from horatio import reconciliation, sheets
from horatio.api.sheets import ApprovalOut, approval_out, players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe, TroupeMembership
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["membership"])

Settlement = Literal[
    "keep_price",
    "pay_difference",
    "refund_difference",
    "remove_and_refund",
    "pay_for_dots",
    "remove_dots",
    "add_free_dots",
]


class MembershipOut(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    home: bool
    standing: str  # draft | approved


class TroupeChoice(BaseModel):
    troupe_id: uuid.UUID


class DifferenceOut(BaseModel):
    category: str
    name: str
    detail: str
    difference: str
    rating: int
    old_cost: int
    new_cost: int | None
    allowed_settlements: list[Settlement]
    # Starting-dot differences: the pool, and how much of it must be paid for or removed.
    pool_rating: int | None
    excess: int
    # Extra creation picks the troupe gives, rather than a difference in one trait.
    extra: bool


class SettlementChoice(BaseModel):
    category: str
    name: str
    detail: str = ""
    # Which difference, when a trait has both a cost and a starting-dot difference.
    difference: str = "cost_differs"
    settlement: Settlement


class HomeTroupeRequest(BaseModel):
    troupe_id: uuid.UUID
    note: str = ""
    settlements: list[SettlementChoice] = []


def running_troupe(db: DbSession, troupe_id: uuid.UUID) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or troupe.archived_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


@router.get("/troupes")
def memberships(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[MembershipOut]:
    character = visible_character(db, user, character_id)
    rows = db.execute(
        select(Troupe, TroupeMembership.standing)
        .join(TroupeMembership, TroupeMembership.troupe_id == Troupe.id)
        .where(TroupeMembership.character_id == character.id, TroupeMembership.left_at.is_(None))
        .order_by(Troupe.name)
    )
    return [
        MembershipOut(
            troupe_id=t.id,
            troupe_name=t.name,
            home=t.id == character.home_troupe_id,
            standing=standing,
        )
        for t, standing in rows
    ]


@router.post("/troupes", status_code=status.HTTP_201_CREATED)
def join_troupe(
    character_id: uuid.UUID, body: TroupeChoice, db: DbSession, user: CurrentUser
) -> MembershipOut:
    """Add the character to a troupe. Its staff can then see the sheet."""
    character = players_character(db, user, character_id)
    troupe = running_troupe(db, body.troupe_id)
    joined = reconciliation.join(db, user, character, troupe)
    db.commit()
    return MembershipOut(
        troupe_id=troupe.id, troupe_name=troupe.name, home=False, standing=joined.standing
    )


@router.delete("/troupes/{troupe_id}", status_code=status.HTTP_204_NO_CONTENT)
def leave_troupe(
    character_id: uuid.UUID, troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> None:
    """Leave a troupe. Leaving the home troupe leaves the character without one."""
    character = players_character(db, user, character_id)
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    reconciliation.leave(db, user, character, troupe)
    db.commit()


def difference_out(d: reconciliation.Difference) -> DifferenceOut:
    return DifferenceOut(
        category=d.category,
        name=d.name,
        detail=d.detail,
        difference=d.difference,
        rating=d.rating,
        old_cost=d.old_cost,
        new_cost=d.new_cost,
        allowed_settlements=list(d.allowed_settlements()),  # type: ignore[arg-type]
        pool_rating=d.pool_rating,
        excess=d.excess,
        extra=d.extra_picks > 0,
    )


@router.post("/home-troupe/preview")
def preview_home_troupe(
    character_id: uuid.UUID, body: TroupeChoice, db: DbSession, user: CurrentUser
) -> list[DifferenceOut]:
    """The differences the player must settle to make `troupe_id` the home troupe."""
    character = players_character(db, user, character_id)
    troupe = running_troupe(db, body.troupe_id)
    return [difference_out(d) for d in reconciliation.find_differences(db, character, troupe)]


@router.post("/home-troupe", status_code=status.HTTP_201_CREATED)
def request_home_troupe(
    character_id: uuid.UUID, body: HomeTroupeRequest, db: DbSession, user: CurrentUser
) -> ApprovalOut:
    character = players_character(db, user, character_id)
    troupe = running_troupe(db, body.troupe_id)
    approval = reconciliation.request_change(
        db,
        user,
        character,
        troupe,
        {
            (
                reconciliation.CREATION
                if s.difference == "creation_differs"
                else reconciliation.COST,
                s.category,
                s.name,
                s.detail,
            ): s.settlement
            for s in body.settlements
        },
        body.note,
    )
    db.commit()
    return approval_out(approval)


@router.delete("/home-troupe", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_home_troupe(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    character = players_character(db, user, character_id)
    pending = reconciliation.pending_change(db, character)
    if pending is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No home troupe request is waiting.")
    sheets.withdraw(db, user, pending[0])
    db.commit()
