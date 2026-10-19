"""Asking the custodian for a new troupe (issue #51). Anyone signed in asks; the
custodian approves, which makes the troupe with the requester as its lead
storyteller, or declines. Each waiting request is a task on the custodian's bell
(horatio.notifications), and the requester hears the answer there."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from horatio import audit, notifications
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe, TroupeRequest, User
from horatio.permissions import require_custodian

router = APIRouter(prefix="/troupe-requests", tags=["troupe requests"])

# Decided and withdrawn requests the custodian's list shows, newest first.
DECIDED_SHOWN = 50


class NewTroupeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    # Anything the custodian should know, such as who will play.
    note: str = Field(default="", max_length=2000)


class Decline(BaseModel):
    reason: str = Field(default="", max_length=2000)


class TroupeRequestOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    note: str
    status: str
    requester_id: uuid.UUID
    requester_name: str
    created_at: datetime
    decided_at: datetime | None
    decided_by_name: str | None
    # Why it was declined, if the custodian said.
    reason: str
    # The troupe approving it made.
    troupe_id: uuid.UUID | None


Requester = aliased(User)
Decider = aliased(User)


def _listed():
    return (
        select(TroupeRequest, Requester.display_name, Decider.display_name)
        .join(Requester, TroupeRequest.requester_id == Requester.id)
        .outerjoin(Decider, TroupeRequest.decided_by_id == Decider.id)
    )


def _out(request: TroupeRequest, requester: str, decider: str | None) -> TroupeRequestOut:
    return TroupeRequestOut(
        id=request.id,
        name=request.name,
        description=request.description,
        note=request.note,
        status=request.status,
        requester_id=request.requester_id,
        requester_name=requester,
        created_at=request.created_at,
        decided_at=request.decided_at,
        decided_by_name=decider,
        reason=request.reason,
        troupe_id=request.troupe_id,
    )


def _one(db: DbSession, request_id: uuid.UUID) -> TroupeRequestOut:
    row = db.execute(_listed().where(TroupeRequest.id == request_id)).one()
    return _out(*row)


def _pending(db: DbSession, request_id: uuid.UUID) -> TroupeRequest:
    request = db.get(TroupeRequest, request_id, with_for_update=True)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such request.")
    if request.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request was already {request.status}.")
    return request


@router.post("", status_code=status.HTTP_201_CREATED)
def ask(body: NewTroupeRequest, db: DbSession, user: CurrentUser) -> TroupeRequestOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the troupe a name.")
    waiting = db.scalar(
        select(TroupeRequest.id).where(
            TroupeRequest.requester_id == user.id,
            TroupeRequest.status == "pending",
            func.lower(TroupeRequest.name) == name.lower(),
        )
    )
    if waiting is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You have already asked for a troupe of that name."
        )
    request = TroupeRequest(
        requester_id=user.id,
        name=name,
        description=body.description.strip(),
        note=body.note.strip(),
    )
    db.add(request)
    db.flush()
    audit.record(db, user, "troupe_request.made", name=name)
    db.commit()
    return _one(db, request.id)


@router.get("/mine")
def my_requests(db: DbSession, user: CurrentUser) -> list[TroupeRequestOut]:
    rows = db.execute(
        _listed()
        .where(TroupeRequest.requester_id == user.id)
        .order_by(TroupeRequest.created_at.desc(), TroupeRequest.id.desc())
    )
    return [_out(*row) for row in rows]


@router.get("")
def all_requests(db: DbSession, user: CurrentUser) -> list[TroupeRequestOut]:
    """For the custodian: what is waiting, longest waiting first, then the latest
    decided."""
    require_custodian(user)
    waiting = db.execute(
        _listed()
        .where(TroupeRequest.status == "pending")
        .order_by(TroupeRequest.created_at, TroupeRequest.id)
    )
    done = db.execute(
        _listed()
        .where(TroupeRequest.status != "pending")
        .order_by(func.coalesce(TroupeRequest.decided_at, TroupeRequest.updated_at).desc())
        .limit(DECIDED_SHOWN)
    )
    return [_out(*row) for row in [*waiting, *done]]


@router.post("/{request_id}/approve")
def approve(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeRequestOut:
    """Make the troupe as asked, led by the requester."""
    require_custodian(user)
    request = _pending(db, request_id)
    troupe = Troupe(
        name=request.name, description=request.description, lead_user_id=request.requester_id
    )
    db.add(troupe)
    db.flush()
    request.status = "approved"
    request.decided_by_id = user.id
    request.decided_at = datetime.now(UTC)
    request.troupe_id = troupe.id
    requester = db.get_one(User, request.requester_id)
    audit.record(
        db,
        user,
        "troupe_request.approved",
        troupe_id=troupe.id,
        name=troupe.name,
        member=requester.display_name,
    )
    notifications.notify(
        db,
        [request.requester_id],
        "troupe_request.approved",
        f"Your troupe {troupe.name} is ready, with you as its lead storyteller",
        f"/troupes/{troupe.id}",
        troupe_id=troupe.id,
    )
    db.commit()
    return _one(db, request.id)


@router.post("/{request_id}/decline")
def decline(
    request_id: uuid.UUID, body: Decline, db: DbSession, user: CurrentUser
) -> TroupeRequestOut:
    require_custodian(user)
    request = _pending(db, request_id)
    request.status = "declined"
    request.decided_by_id = user.id
    request.decided_at = datetime.now(UTC)
    request.reason = body.reason.strip()
    audit.record(db, user, "troupe_request.declined", name=request.name)
    because = f": {request.reason}" if request.reason else ""
    notifications.notify(
        db,
        [request.requester_id],
        "troupe_request.declined",
        f"Your request for the troupe {request.name} was declined{because}",
        "/troupes",
    )
    db.commit()
    return _one(db, request.id)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """The requester takes back a request still waiting."""
    request = db.get(TroupeRequest, request_id, with_for_update=True)
    if request is None or request.requester_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such request.")
    request = _pending(db, request_id)
    request.status = "withdrawn"
    audit.record(db, user, "troupe_request.withdrawn", name=request.name)
    db.commit()
