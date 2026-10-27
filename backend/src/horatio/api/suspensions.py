"""The custodian suspending an account, and lifting it (horatio.suspensions)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import aliased

from horatio import suspensions
from horatio.api.players import player
from horatio.api.roster import LogEntry, log_entries
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import AuditEvent, Suspension, Troupe, User
from horatio.permissions import require_custodian

router = APIRouter(tags=["suspensions"])

ACTIONS = (suspensions.SUSPENDED, suspensions.LIFTED, suspensions.EMAIL_FAILED)


class SuspendIn(BaseModel):
    # Why, for the custodian only: the person is never shown it.
    reason: str = Field(min_length=1, max_length=2000)
    # When it ends by itself; None until it is lifted by hand.
    ends_at: datetime | None = None


class LiftIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class Emailed(BaseModel):
    # Why the person could not be emailed about it, if they could not.
    email_error: str | None = None


class LedTroupe(BaseModel):
    id: uuid.UUID
    name: str


class Suspended(BaseModel):
    user_id: uuid.UUID
    display_name: str
    handle: str
    reason: str
    since: datetime
    ends_at: datetime | None
    suspended_by: str
    # The troupes they lead, which need a new lead storyteller while they are away.
    leads: list[LedTroupe]


class Suspensions(BaseModel):
    suspended: list[Suspended]
    # Suspensions made, lifted and ended, newest first.
    log: list[LogEntry]


@router.post("/players/{user_id}/suspension", status_code=status.HTTP_201_CREATED)
def suspend(user_id: uuid.UUID, body: SuspendIn, db: DbSession, user: CurrentUser) -> Emailed:
    """Suspend someone: signed out everywhere at once, and kept out until the
    custodian lifts it or `ends_at` passes. They are emailed, without the reason."""
    require_custodian(user)
    _, error = suspensions.suspend(db, user, player(db, user_id), body.reason, body.ends_at)
    db.commit()
    return Emailed(email_error=error)


@router.post("/players/{user_id}/suspension/lift")
def lift(user_id: uuid.UUID, body: LiftIn, db: DbSession, user: CurrentUser) -> Emailed:
    """Lift someone's suspension, so they can sign in again. They are emailed."""
    require_custodian(user)
    error = suspensions.lift(db, user, player(db, user_id), body.reason)
    db.commit()
    return Emailed(email_error=error)


@router.get("/suspensions")
def list_suspensions(db: DbSession, user: CurrentUser, limit: int = 50) -> Suspensions:
    """For the custodian: who is suspended now, and the log of suspensions."""
    require_custodian(user)
    by = aliased(User)
    rows = list(
        db.execute(
            select(Suspension, User, by.display_name)
            .join(User, Suspension.user_id == User.id)
            .join(by, Suspension.suspended_by_id == by.id)
            .where(suspensions.live())
            .order_by(Suspension.created_at.desc())
        )
    )
    led: dict[uuid.UUID, list[LedTroupe]] = {}
    for troupe in db.scalars(
        select(Troupe)
        .where(
            Troupe.lead_user_id.in_([u.id for _, u, _ in rows]),
            Troupe.archived_at.is_(None),
        )
        .order_by(Troupe.name)
    ):
        led.setdefault(troupe.lead_user_id, []).append(LedTroupe(id=troupe.id, name=troupe.name))
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(AuditEvent.action.in_(ACTIONS))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(min(max(limit, 1), 500))
    )
    return Suspensions(
        suspended=[
            Suspended(
                user_id=u.id,
                display_name=u.display_name,
                handle=u.handle,
                reason=s.reason,
                since=s.created_at,
                ends_at=s.ends_at,
                suspended_by=suspended_by,
                leads=led.get(u.id, []),
            )
            for s, u, suspended_by in rows
        ],
        log=log_entries(db, query),
    )
