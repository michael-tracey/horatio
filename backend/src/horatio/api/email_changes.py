"""Changing someone's email (horatio.email_changes): the custodian for anyone, with a
reason, or a person for themself, with their password. The link to confirm it is
opened without signing in, since the person may have lost the old address."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import aliased

from horatio import email_changes
from horatio.api.roster import LogEntry, log_entries
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.passwords import verify_password
from horatio.connectors import email
from horatio.models import AuditEvent, EmailChange, User
from horatio.permissions import require_custodian

router = APIRouter(tags=["players"])

NO_EMAIL = "Horatio can't send email here, so ask the custodian to change your email."


class EmailChangeIn(BaseModel):
    email: EmailStr
    # Why, when the custodian changes someone else's.
    reason: str | None = None
    # Their password, when someone changes their own (unless they have none).
    password: str | None = None


class PendingEmail(BaseModel):
    """A change of email waiting to be confirmed at the new address."""

    new_email: str
    expires_at: datetime
    # Who started it: the custodian's name, or the person's own.
    made_by: str
    asked_themselves: bool


class EmailChangeOut(PendingEmail):
    # Where the link was emailed, or why it could not be.
    emailed_to: str | None = None
    email_error: str | None = None
    # The link itself, for the custodian to send on when Horatio can't email it.
    url: str | None = None


class PendingEmailFor(PendingEmail):
    user_id: uuid.UUID
    display_name: str
    email: str


class EmailChanges(BaseModel):
    pending: list[PendingEmailFor]
    # Changes started, confirmed and cancelled, newest first.
    log: list[LogEntry]


class ConfirmFor(BaseModel):
    display_name: str
    handle: str
    new_email: str


class Confirmed(BaseModel):
    email: str


def pending(db: DbSession, user: User, change: EmailChange | None = None) -> PendingEmail | None:
    """`user`'s change waiting, for the person themself and the custodian."""
    change = change or email_changes.live_change(db, user)
    if change is None:
        return None
    made_by = user if change.created_by_id == user.id else db.get_one(User, change.created_by_id)
    return PendingEmail(
        new_email=change.new_email,
        expires_at=change.expires_at,
        made_by=made_by.display_name,
        asked_themselves=made_by.id == user.id,
    )


def whose(db: DbSession, user: User, user_id: uuid.UUID) -> User:
    """The person whose email `user` may change: their own, or anyone's for the custodian."""
    if user_id != user.id:
        require_custodian(user)
    found = db.get(User, user_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player.")
    return found


def send(db: DbSession, by: User, target: User, change: EmailChange, url: str) -> EmailChangeOut:
    """Email the link to the new address if Horatio can; if not, the custodian gets
    it to send on. Someone changing their own never sees it."""
    shown = pending(db, target, change)
    assert shown is not None
    out = EmailChangeOut(**shown.model_dump())
    if email.configured():
        out.email_error = email_changes.email_link(db, by, target, change, url)
        out.emailed_to = None if out.email_error else change.new_email
    if by.id != target.id and out.emailed_to is None:
        out.url = url
    return out


@router.post("/players/{user_id}/email-change", status_code=status.HTTP_201_CREATED)
def change_email(
    user_id: uuid.UUID, body: EmailChangeIn, db: DbSession, user: CurrentUser
) -> EmailChangeOut:
    """Start changing someone's email: it changes when the link sent to the new
    address is opened. The custodian gives a reason; someone changing their own
    gives their password, and needs Horatio to be able to email."""
    target = whose(db, user, user_id)
    reason = None
    if target.id == user.id:
        if not email.configured():
            raise HTTPException(status.HTTP_409_CONFLICT, NO_EMAIL)
        if target.password_hash is not None:
            ok, _ = verify_password(body.password or "", target.password_hash)
            if not ok:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "That's not your password.")
    else:
        reason = (body.reason or "").strip()
        if not reason:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a reason.")
    change, url = email_changes.start(db, user, target, body.email, reason)
    out = send(db, user, target, change, url)
    db.commit()
    return out


@router.post("/players/{user_id}/email-change/resend")
def resend_email_change(user_id: uuid.UUID, db: DbSession, user: CurrentUser) -> EmailChangeOut:
    """A new link for the change waiting, good for another 7 days; the old one stops
    working."""
    target = whose(db, user, user_id)
    if target.id == user.id and not email.configured():
        raise HTTPException(status.HTTP_409_CONFLICT, NO_EMAIL)
    change, url = email_changes.resend(db, user, target)
    out = send(db, user, target, change, url)
    db.commit()
    return out


@router.delete("/players/{user_id}/email-change", status_code=status.HTTP_204_NO_CONTENT)
def cancel_email_change(user_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Cancel the change waiting: the email stays as it is, and the link stops working."""
    email_changes.cancel(db, user, whose(db, user, user_id))
    db.commit()


@router.get("/email-changes")
def list_email_changes(db: DbSession, user: CurrentUser, limit: int = 50) -> EmailChanges:
    """For the custodian: the changes waiting to be confirmed, and every step of
    changes made, with both addresses."""
    require_custodian(user)
    maker = aliased(User)
    waiting = db.execute(
        select(EmailChange, User, maker.display_name)
        .join(User, EmailChange.user_id == User.id)
        .join(maker, EmailChange.created_by_id == maker.id)
        .where(EmailChange.expires_at > datetime.now(UTC))
        .order_by(EmailChange.expires_at)
    )
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(AuditEvent.action.in_(email_changes.ACTIONS))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(min(max(limit, 1), 500))
    )
    return EmailChanges(
        pending=[
            PendingEmailFor(
                user_id=u.id,
                display_name=u.display_name,
                email=u.email,
                new_email=change.new_email,
                expires_at=change.expires_at,
                made_by=made_by,
                asked_themselves=change.created_by_id == u.id,
            )
            for change, u, made_by in waiting
        ],
        log=log_entries(db, query),
    )


def live(db: DbSession, token: str) -> EmailChange:
    change = email_changes.change_for(db, token)
    if change is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This link has expired, been used or been replaced by a newer one.",
        )
    return change


@router.get("/auth/email-change/{token}")
def email_change_for(token: str, db: DbSession) -> ConfirmFor:
    """Whose email a link changes, and to what, so the page can ask first."""
    change = live(db, token)
    user = db.get_one(User, change.user_id)
    return ConfirmFor(
        display_name=user.display_name, handle=user.handle, new_email=change.new_email
    )


@router.post("/auth/email-change/{token}")
def confirm_email_change(token: str, db: DbSession) -> Confirmed:
    """Confirm a change from the link sent to the new address: the email changes,
    and the old address is told."""
    user, old, made_by = email_changes.confirm(db, live(db, token))
    db.commit()
    email_changes.email_notice(db, user, old, made_by)
    db.commit()
    return Confirmed(email=user.email)
