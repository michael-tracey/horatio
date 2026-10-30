"""Changing someone's email, confirmed at the new address (issue #274).

The custodian changes it for someone who has lost their old address, with a
reason; or the person changes their own, giving their password. Either way the
change waits until the link emailed to the new address is opened, for 7 days.
Where Horatio can't send email, the custodian gets the link to send on
themselves; a person can't change their own. Like reset links
(horatio.auth.resets), the link holds a random token and the database only its
hash, and a new link replaces the old.

An address another account uses is refused, both when the change starts and
when it is confirmed. Once confirmed, the old address is told, with who to
contact if it wasn't them, and the unsubscribe key is renewed, so unsubscribe
links sent to the old address stop working. Sign-in through Discord or Google is
separate from the email, and stays as it was. Every step is in the audit log,
with both addresses, for the custodian.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import formataddr
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from horatio.audit import record
from horatio.auth.sessions import hash_token
from horatio.config import get_settings
from horatio.connectors import SendError, email
from horatio.models import EmailChange, User

CHANGE_DAYS = 7

STARTED = "account.email_change_started"
RESENT = "account.email_change_resent"
EMAIL_FAILED = "account.email_change_email_failed"
CANCELLED = "account.email_change_cancelled"
CHANGED = "account.email_changed"
NOTICE_FAILED = "account.email_change_notice_failed"
ACTIONS = (STARTED, RESENT, EMAIL_FAILED, CANCELLED, CHANGED, NOTICE_FAILED)


def site() -> str:
    return get_settings().public_url.rstrip("/")


def confirm_url(token: str) -> str:
    return f"{site()}/confirm-email/{token}"


def live_change(db: Session, user: User) -> EmailChange | None:
    """`user`'s change waiting to be confirmed, if it hasn't expired."""
    return db.scalar(
        select(EmailChange).where(
            EmailChange.user_id == user.id, EmailChange.expires_at > datetime.now(UTC)
        )
    )


def taken(db: Session, address: str, user: User) -> User | None:
    """Another open account that uses `address`, whatever its case. A merged one
    keeps its email only for the record (horatio.account_merges)."""
    return db.scalar(
        select(User).where(
            func.lower(User.email) == address.lower(),
            User.id != user.id,
            User.merged_into_id.is_(None),
        )
    )


def refuse_taken(db: Session, address: str, user: User, by: User) -> None:
    other = taken(db, address, user)
    if other is None:
        return
    if by.is_custodian and by.id != user.id:
        detail = (
            f"{other.display_name} (@{other.handle}) uses {address} already. If both "
            "accounts are the same person's, merge them instead."
        )
    else:
        detail = (
            "Another Horatio account uses that address. If it's yours too, ask the "
            "custodian to merge the two."
        )
    raise HTTPException(status.HTTP_409_CONFLICT, detail)


def about(user: User, change: EmailChange) -> dict[str, Any]:
    return {"member": user.display_name, "user_id": user.id, "to_email": change.new_email}


def mine(by: User, user: User) -> dict[str, Any]:
    """Marks an event as the person's own doing, for the log's wording."""
    return {"kind": "self"} if by.id == user.id else {}


def new_link(db: Session, change: EmailChange) -> str:
    """A new token for `change`, good for 7 days from now; the old one stops working."""
    token = secrets.token_urlsafe(32)
    change.token_hash = hash_token(token)
    change.expires_at = datetime.now(UTC) + timedelta(days=CHANGE_DAYS)
    db.flush()
    return confirm_url(token)


def start(
    db: Session, by: User, user: User, address: str, reason: str | None
) -> tuple[EmailChange, str]:
    """Start changing `user`'s email to `address`, replacing any change waiting, and
    log it. The change and the link that confirms it."""
    address = address.strip()
    if address.lower() == user.email.lower():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{address} is the account's email already."
        )
    refuse_taken(db, address, user, by)
    db.execute(delete(EmailChange).where(EmailChange.user_id == user.id))
    change = EmailChange(
        user_id=user.id,
        new_email=address,
        token_hash="",
        expires_at=datetime.now(UTC),
        created_by_id=by.id,
        reason=reason,
    )
    db.add(change)
    url = new_link(db, change)
    data: dict[str, Any] = about(user, change) | {"from_email": user.email}
    if by.id == user.id:
        record(db, by, STARTED, **data, kind="self")
    else:
        record(db, by, STARTED, **data, reason=reason)
    return change, url


def resend(db: Session, by: User, user: User) -> tuple[EmailChange, str]:
    """A new link for `user`'s change waiting, which replaces the old one."""
    change = live_change(db, user)
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no email change waiting.")
    url = new_link(db, change)
    record(db, by, RESENT, **about(user, change), **mine(by, user))
    return change, url


def cancel(db: Session, by: User, user: User) -> None:
    """Cancel `user`'s change waiting, so its link no longer works."""
    change = live_change(db, user)
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no email change waiting.")
    record(db, by, CANCELLED, **about(user, change), **mine(by, user))
    db.delete(change)
    db.flush()


def change_for(db: Session, token: str) -> EmailChange | None:
    """The live change this token confirms, or None."""
    return db.scalar(
        select(EmailChange).where(
            EmailChange.token_hash == hash_token(token),
            EmailChange.expires_at > datetime.now(UTC),
        )
    )


def confirm(db: Session, change: EmailChange) -> tuple[User, str, User | None]:
    """Make the change, now its link has been opened: the person, their old email,
    and the custodian who made the change, if one did."""
    user = db.get_one(User, change.user_id)
    made_by = None if change.created_by_id == user.id else db.get(User, change.created_by_id)
    refuse_taken(db, change.new_email, user, user)
    old = user.email
    user.email = change.new_email
    # Unsubscribe links sent to the old address stop working (horatio.notification_emails).
    user.unsubscribe_key = uuid.uuid4()
    data: dict[str, Any] = about(user, change) | {"from_email": old, "reason": change.reason}
    if made_by is None:
        record(db, user, CHANGED, **data, kind="self")
    else:
        record(db, user, CHANGED, **data, made_by=made_by.display_name, made_by_id=made_by.id)
    db.delete(change)
    db.flush()
    return user, old, made_by


def deliver(mail_to: str, name: str, subject: str, text: str) -> None:
    mail = email.new_message(formataddr((name, mail_to)), subject)
    mail.set_content(f"Hello {name},\n\n{text}\n\n-- \nSent by Horatio, {site()}\n")
    email.deliver(mail)


def email_link(db: Session, by: User, user: User, change: EmailChange, url: str) -> str | None:
    """Email the link to the new address. The mail server's refusal, if it refused,
    which is logged."""
    if by.id == user.id:
        opening = "You asked to change the email of your Horatio account"
    else:
        opening = (
            f"{by.display_name}, Horatio's custodian, is changing the email of your Horatio account"
        )
    text = (
        f"{opening} (@{user.handle}) to this address. Follow this link to confirm it:\n\n{url}\n\n"
        f"It works for the next {CHANGE_DAYS} days. Until it's opened, your account keeps "
        "its old address. If you weren't expecting this, ignore this email."
    )
    try:
        deliver(change.new_email, user.display_name, "Confirm your new Horatio email", text)
    except SendError as error:
        record(db, by, EMAIL_FAILED, **about(user, change), error=str(error))
        return str(error)
    return None


def custodians(db: Session) -> str:
    """Who the custodian is, for someone to contact: "Ann (@ann)", or several."""
    named = [
        f"{c.display_name} (@{c.handle})"
        for c in db.scalars(
            select(User).where(User.is_custodian).order_by(func.lower(User.display_name))
        )
    ]
    return ", ".join(named)


def email_notice(db: Session, user: User, old: str, made_by: User | None) -> None:
    """Tell the old address the email changed, and who to contact if it wasn't them.
    A refusal is logged."""
    if not email.configured():
        return
    by = f" {made_by.display_name}, Horatio's custodian, made the change." if made_by else ""
    who = custodians(db)
    text = (
        f"The email of your Horatio account (@{user.handle}) has been changed from this "
        f"address to {user.email}, and confirmed there.{by} Horatio's emails go there from "
        "now on, and you sign in with it.\n\n"
        "If you didn't want this, contact Horatio's custodian straight away"
        f"{': ' + who if who else ''}."
    )
    try:
        deliver(old, user.display_name, "Your Horatio email has changed", text)
    except SendError as error:
        data = {"member": user.display_name, "user_id": user.id, "from_email": old}
        record(db, user, NOTICE_FAILED, **data, error=str(error))
