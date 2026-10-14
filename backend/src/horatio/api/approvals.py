"""The approvals queue storytellers and assistant storytellers work from."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from horatio import sheets
from horatio.api.sheets import ApprovalOut, PendingChange, approval_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Approval, Character, Troupe
from horatio.permissions import TroupeAction, require_troupe_action

router = APIRouter(tags=["approvals"])


class QueuedApproval(ApprovalOut):
    character_name: str
    changes: list[PendingChange]


class Decision(BaseModel):
    note: str = ""


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
    rows = db.execute(
        select(Approval, Character)
        .join(Character, Approval.character_id == Character.id)
        .where(Approval.troupe_id == troupe.id, Approval.status == state)
        .order_by(Approval.id)
    )
    return [
        QueuedApproval(
            **approval_out(a).model_dump(),
            character_name=c.name,
            changes=[PendingChange(**ch) for ch in sheets.pending_changes(db, c)]
            if a.status == "pending"
            else [],
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
    sheets.decide(db, user, approval, approve, body.note)
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
