"""Suspending an account, and lifting it (issue #273): the custodian's way to keep
someone out for a while without deleting anything.

While someone is suspended they are signed out everywhere and cannot sign in
by any means: `user_for_token` and `start_session` (horatio.auth.sessions) and
reset links (horatio.api.auth) all refuse them, with `message`. They get no
notification emails (horatio.notification_emails), and no downtime results by
email (horatio.delivery). Their characters stay as they are, in their troupes,
but take no new actions: no downtime answers and no Play View taps
(`refuse_character`). Staff roles stay, but do nothing while they cannot sign in.

A suspension ends when the custodian lifts it, or when its end date passes: it
stops counting at once (`live`), and the delivery worker records it as lifted
(`end_due`). Every suspension is kept, lifted or not, and each step is logged
and emailed to the person. The reason is for the custodian: the person is never
shown it.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from email.utils import formataddr
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, and_, delete, exists, func, or_, select
from sqlalchemy.orm import Session

from horatio import preferences
from horatio.audit import record
from horatio.config import get_settings
from horatio.connectors import SendError, email
from horatio.models import Character, Suspension, User
from horatio.models import Session as SignInSession

SUSPENDED = "account.suspended"
LIFTED = "account.suspension_lifted"
EMAIL_FAILED = "account.suspension_email_failed"


def now() -> datetime:
    """The current time; tests replace this."""
    return datetime.now(UTC)


def live(at: datetime | None = None) -> ColumnElement[bool]:
    """A suspension still in force: not lifted, and not past its end date."""
    return and_(
        Suspension.lifted_at.is_(None),
        or_(Suspension.ends_at.is_(None), Suspension.ends_at > (at or now())),
    )


def suspended_user() -> ColumnElement[bool]:
    """A condition on User: they are suspended now."""
    return exists().where(Suspension.user_id == User.id, live())


def current(db: Session, user_id: uuid.UUID) -> Suspension | None:
    """The suspension `user_id` is under now, if any."""
    return db.scalar(select(Suspension).where(Suspension.user_id == user_id, live()))


def suspended_ids(db: Session, user_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Which of `user_ids` are suspended now."""
    ids = list(set(user_ids))
    if not ids:
        return set()
    return set(db.scalars(select(Suspension.user_id).where(Suspension.user_id.in_(ids), live())))


def when(user: User, at: datetime) -> str:
    """`at` for a sentence to `user`, in their time zone."""
    zone = preferences.read(user).time_zone or "UTC"
    local = at.astimezone(ZoneInfo(zone))
    return f"{local.day} {local:%b %Y, %H:%M} ({zone.replace('_', ' ')})"


def contact() -> str:
    """How to reach the custodian, as the end of a sentence."""
    how = (get_settings().custodian_contact or "").strip()
    return f"contact the custodian: {how}" if how else "contact the custodian"


def message(user: User, suspension: Suspension) -> str:
    """What someone suspended is told when they try to sign in."""
    until = f" until {when(user, suspension.ends_at)}" if suspension.ends_at else ""
    return f"Your account is suspended{until}. To ask about it, {contact()}."


def refuse(db: Session, user: User) -> None:
    """Refuse with 403, saying so, if `user` is suspended. One whose end date has
    passed is recorded as lifted first."""
    end_due(db, [user.id])
    suspension = current(db, user.id)
    if suspension is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, message(user, suspension))


def refuse_character(db: Session, character: Character) -> None:
    """Refuse with 409 a new action for a PC whose player is suspended."""
    if character.kind == "pc" and current(db, character.player_id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{character.name}'s player is suspended, so {character.name} takes no new actions.",
        )


def site() -> str:
    return get_settings().public_url.rstrip("/")


def notify(db: Session, user: User, by: User | None, subject: str, text: str) -> str | None:
    """Email `user` about their suspension. Logs a refusal, and returns it."""
    if not email.configured():
        return None
    mail = email.new_message(formataddr((user.display_name, user.email)), subject)
    mail.set_content(f"Hello {user.display_name},\n\n{text}\n\n-- \nSent by Horatio, {site()}\n")
    try:
        email.deliver(mail)
    except SendError as error:
        record(db, by, EMAIL_FAILED, member=user.display_name, user_id=user.id, error=str(error))
        return str(error)
    return None


def suspend(
    db: Session, by: User, user: User, reason: str, ends_at: datetime | None
) -> tuple[Suspension, str | None]:
    """Suspend `user`, sign them out everywhere, log it and email them. The
    suspension, and why the email could not be sent, if it could not."""
    reason = reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a reason.")
    if user.id == by.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't suspend yourself.")
    if ends_at is not None and ends_at <= now():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The end date has to be in the future."
        )
    end_due(db, [user.id])
    if current(db, user.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{user.display_name} is suspended already.")
    if user.is_custodian:
        others = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_custodian, User.id != user.id, ~suspended_user())
        )
        if not others:
            raise HTTPException(status.HTTP_409_CONFLICT, "You can't suspend the last custodian.")
    suspension = Suspension(user_id=user.id, reason=reason, ends_at=ends_at, suspended_by_id=by.id)
    db.add(suspension)
    db.execute(delete(SignInSession).where(SignInSession.user_id == user.id))
    db.flush()
    about = {"member": user.display_name, "user_id": user.id, "reason": reason}
    if ends_at is None:
        record(db, by, SUSPENDED, **about)
    else:
        record(db, by, SUSPENDED, **about, kind="until", until=when(by, ends_at))
    until = f" until {when(user, ends_at)}" if ends_at else ""
    error = notify(
        db,
        user,
        by,
        "Your Horatio account is suspended",
        f"Horatio's custodian has suspended your account{until}. While it is suspended you "
        "can't sign in, and Horatio sends you no notifications. Your characters stay as "
        f"they are.\n\nTo ask about it, {contact()}.",
    )
    return suspension, error


def lifted(db: Session, user: User, by: User | None, text: str) -> str | None:
    return notify(
        db,
        user,
        by,
        "Your Horatio account is no longer suspended",
        f"{text} You can sign in again: {site()}",
    )


def lift(db: Session, by: User, user: User, reason: str) -> str | None:
    """Lift `user`'s suspension by hand, log it and email them. Why the email could
    not be sent, if it could not."""
    reason = reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a reason.")
    end_due(db, [user.id])
    suspension = current(db, user.id)
    if suspension is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{user.display_name} is not suspended.")
    suspension.lifted_at = now()
    suspension.lifted_by_id = by.id
    suspension.lift_reason = reason
    db.flush()
    record(db, by, LIFTED, member=user.display_name, user_id=user.id, reason=reason)
    return lifted(db, user, by, "Horatio's custodian has lifted the suspension of your account.")


def end_due(db: Session, user_ids: Iterable[uuid.UUID] | None = None) -> int:
    """Record as lifted the suspensions whose end date has passed (only `user_ids`'
    when given), logging and emailing each. Returns how many ended."""
    at = now()
    query = (
        select(Suspension)
        .where(Suspension.lifted_at.is_(None), Suspension.ends_at <= at)
        .with_for_update(skip_locked=True)
    )
    if user_ids is not None:
        query = query.where(Suspension.user_id.in_(list(user_ids)))
    ended = list(db.scalars(query))
    for suspension in ended:
        assert suspension.ends_at is not None
        suspension.lifted_at = suspension.ends_at
        user = db.get_one(User, suspension.user_id)
        record(db, None, LIFTED, member=user.display_name, user_id=user.id, kind="ended")
        lifted(db, user, None, "The suspension of your account has ended.")
    db.flush()
    return len(ended)


def end_due_now() -> int:
    """`end_due` in a session of its own, for the delivery worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        ended = end_due(db)
        db.commit()
        return ended
