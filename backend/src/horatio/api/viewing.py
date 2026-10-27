"""Viewing as someone, read-only, for support (horatio.auth.viewing): the custodian
starts it from People with a reason, and stops it from the banner. The person sees
on their account page when the custodian viewed as them, and why."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio.api.players import player
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.sessions import hash_token
from horatio.auth.viewing import VIEW_FOR, allowed_while_viewing, end, viewing_for
from horatio.config import get_settings
from horatio.models import Session as SignInSession
from horatio.models import User, Viewing
from horatio.notifications import notify
from horatio.permissions import require_custodian

router = APIRouter(tags=["viewing"])


class ViewAsIn(BaseModel):
    # Why: for the audit log, and for the person, who is told.
    reason: str = Field(max_length=500)


class ViewingNow(BaseModel):
    user_id: uuid.UUID
    handle: str
    display_name: str
    reason: str
    # When it ends by itself.
    ends_at: datetime


class ViewedAs(BaseModel):
    """A time the custodian viewed Horatio as the person."""

    custodian: str
    reason: str
    started_at: datetime
    # When it ended, or will.
    until: datetime


def viewing_now(db: DbSession, viewing: Viewing) -> ViewingNow:
    person = db.get_one(User, viewing.user_id)
    return ViewingNow(
        user_id=person.id,
        handle=person.handle,
        display_name=person.display_name,
        reason=viewing.reason,
        ends_at=viewing.ends_at,
    )


@router.get("/view-as")
def current_viewing(request: Request, db: DbSession) -> ViewingNow | None:
    """Whom the signed-in custodian is viewing Horatio as, if anyone."""
    viewing = viewing_for(request, db)
    return viewing_now(db, viewing) if viewing else None


@router.post("/players/{user_id}/view-as", status_code=status.HTTP_201_CREATED)
def view_as(
    user_id: uuid.UUID, body: ViewAsIn, request: Request, db: DbSession, user: CurrentUser
) -> ViewingNow:
    """Start viewing Horatio as someone, read-only, for 30 minutes. Never another
    custodian. The reason goes in the audit log, and the person is told."""
    require_custodian(user)
    person = player(db, user_id)
    if person.is_custodian:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't view as a custodian.")
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Say why you're viewing as them."
        )
    token = request.cookies.get(get_settings().session_cookie_name, "")
    session_id = db.scalar(
        select(SignInSession.id).where(SignInSession.token_hash == hash_token(token))
    )
    viewing = Viewing(
        custodian_id=user.id,
        user_id=person.id,
        session_id=session_id,
        reason=reason,
        ends_at=datetime.now(UTC) + VIEW_FOR,
    )
    db.add(viewing)
    record(
        db,
        user,
        "account.view_as",
        member=person.display_name,
        user_id=person.id,
        handle=person.handle,
        reason=reason,
    )
    notify(
        db,
        [person.id],
        "account.viewed_as",
        f"{user.display_name}, the custodian, viewed Horatio as you, read-only: {reason}",
        "/account",
    )
    db.commit()
    return viewing_now(db, viewing)


@router.post("/view-as/stop", status_code=status.HTTP_204_NO_CONTENT)
@allowed_while_viewing
def stop_viewing(request: Request, db: DbSession) -> None:
    """Stop viewing as someone, and be the custodian again."""
    viewing = viewing_for(request, db)
    if viewing is not None:
        end(db, viewing, "stopped")
        db.commit()


@router.get("/account/viewed-as")
def viewed_as(db: DbSession, user: CurrentUser) -> list[ViewedAs]:
    """The times the custodian viewed Horatio as the signed-in person, newest first."""
    rows = db.execute(
        select(Viewing, User.display_name)
        .join(User, Viewing.custodian_id == User.id)
        .where(Viewing.user_id == user.id)
        .order_by(Viewing.created_at.desc())
        .limit(100)
    )
    return [
        ViewedAs(
            custodian=custodian,
            reason=v.reason,
            started_at=v.created_at,
            until=v.ended_at or v.ends_at,
        )
        for v, custodian in rows
    ]
