"""The approvals queue storytellers and assistant storytellers work from."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from horatio import pictures, sheets, social_age
from horatio.api.sheets import ApprovalOut, approval_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Approval, Character, DisciplinePurchase, TraitDefinition, Troupe
from horatio.permissions import TroupeAction, require_troupe_action
from horatio.reconciliation import allowed_settlements, items_for

router = APIRouter(tags=["approvals"])


class ReconciliationOut(BaseModel):
    id: uuid.UUID
    trait: str
    category: str | None
    pool_rating: int | None
    detail: str
    difference: str
    rating: int
    old_cost: int
    new_cost: int | None
    proposed_settlement: str
    settlement: str | None
    allowed_settlements: list[str]
    # Extra creation picks the troupe gives, rather than a difference in one trait.
    extra: bool


class DisciplineOut(BaseModel):
    name: str
    detail: str
    from_rating: int
    to_rating: int
    cost: int
    teacher: str


class QueuedApproval(ApprovalOut):
    character_name: str
    # The character's picture (horatio.pictures) and clan, for its placeholder.
    picture: str | None
    clan: str | None
    # For a discipline: the dots bought and what they cost.
    discipline: DisciplineOut | None
    # For a home troupe change: each difference and how it is to be settled.
    reconciliation: list[ReconciliationOut]


class SettlementOverride(BaseModel):
    item_id: uuid.UUID
    settlement: Literal[
        "keep_price",
        "pay_difference",
        "refund_difference",
        "remove_and_refund",
        "pay_for_dots",
        "remove_dots",
        "add_free_dots",
    ]


class Decision(BaseModel):
    note: str = ""
    # Home troupe changes only: settle these differences differently from the player's proposal.
    settlements: list[SettlementOverride] = []


def reconciliation_out(db: DbSession, approval: Approval) -> list[ReconciliationOut]:
    if approval.kind != "home_troupe_change":
        return []
    character = db.get_one(Character, approval.character_id)
    return [
        ReconciliationOut(
            id=item.id,
            trait=(
                db.get_one(TraitDefinition, item.trait_definition_id).name
                if item.trait_definition_id
                else item.detail
            ),
            category=item.pool_category,
            pool_rating=item.pool_rating,
            detail=item.detail if item.trait_definition_id else "",
            difference=item.difference,
            rating=item.rating,
            old_cost=item.old_cost,
            new_cost=item.new_cost,
            proposed_settlement=item.proposed_settlement,
            settlement=item.settlement,
            extra=item.difference == "creation_differs" and item.trait_definition_id is None,
            allowed_settlements=list(allowed_settlements(db, approval, item, character))
            if approval.status == "pending"
            else [],
        )
        for item in items_for(db, approval)
    ]


def discipline_out(db: DbSession, approval: Approval) -> DisciplineOut | None:
    if approval.kind not in ("discipline", "review"):
        return None
    found = db.execute(
        select(DisciplinePurchase, TraitDefinition.name)
        .join(TraitDefinition, DisciplinePurchase.trait_definition_id == TraitDefinition.id)
        .where(DisciplinePurchase.approval_id == approval.id)
    ).one()
    bought, name = found
    return DisciplineOut(
        name=name,
        detail=bought.detail,
        from_rating=bought.from_rating,
        to_rating=bought.to_rating,
        cost=bought.cost,
        teacher=bought.teacher,
    )


@router.get("/troupes/{troupe_id}/approvals")
def troupe_approvals(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    state: Literal["pending", "approved", "declined", "withdrawn"] = "pending",
) -> list[QueuedApproval]:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    require_troupe_action(db, user, troupe, TroupeAction.APPROVE_CHANGES)
    rows = list(
        db.execute(
            select(Approval, Character)
            .join(Character, Approval.character_id == Character.id)
            .where(Approval.troupe_id == troupe.id, Approval.status == state)
            .order_by(Approval.id)
        )
    )
    standing = social_age.standings(db, list({c.id for _, c in rows}))
    return [
        QueuedApproval(
            **approval_out(a).model_dump(),
            character_name=c.name,
            picture=pictures.picture_url(c.id, c.picture_id),
            clan=standing[c.id].clan,
            discipline=discipline_out(db, a),
            reconciliation=reconciliation_out(db, a),
        )
        for a, c in rows
    ]


def decide(
    approval_id: uuid.UUID, approve: bool, body: Decision, db: DbSession, user: CurrentUser
) -> ApprovalOut:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such request.")
    troupe = db.get_one(Troupe, approval.troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.APPROVE_CHANGES)
    sheets.decide(
        db,
        user,
        approval,
        approve,
        body.note,
        {o.item_id: o.settlement for o in body.settlements},
    )
    db.commit()
    return approval_out(approval)


@router.post("/approvals/{approval_id}/approve")
def approve(
    approval_id: uuid.UUID, body: Decision, db: DbSession, user: CurrentUser
) -> ApprovalOut:
    return decide(approval_id, True, body, db, user)


@router.post("/approvals/{approval_id}/decline")
def decline(
    approval_id: uuid.UUID, body: Decision, db: DbSession, user: CurrentUser
) -> ApprovalOut:
    return decide(approval_id, False, body, db, user)
