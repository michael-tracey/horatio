"""One-time password reset links, for someone locked out.

The custodian makes one for someone, to copy or to have Horatio email; or
someone asks for one themselves from the sign-in page, and Horatio emails it to
their account's address. Like sessions, the link holds a random token and the
database only its hash. A link works once, for a day; making a new one for the
same person cancels the old one.

Asking for a link yourself never says whether an account uses the address, and
is limited per address and per IP address. The limits count the requests kept
in the audit log (`account.reset_requested`), whether an account matched or
not, so being turned away says nothing either.
"""

import re
import secrets
from datetime import UTC, datetime, timedelta
from email.utils import formataddr
from urllib.parse import quote, unquote

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from horatio import suspensions
from horatio.audit import record
from horatio.auth.sessions import hash_token
from horatio.config import get_settings
from horatio.connectors import SendError, email
from horatio.models import AuditEvent, PasswordReset, User
from horatio.models import Session as SignInSession

RESET_HOURS = 24
REQUESTED = "account.reset_requested"

# How many links may be asked for in each window: per address, and per IP address
# (a household or a game venue may share one).
ADDRESS_LIMITS = ((timedelta(minutes=5), 1), (timedelta(days=1), 5))
IP_LIMITS = ((timedelta(minutes=5), 5), (timedelta(days=1), 20))

ADDRESS_WAIT = (
    "A reset link was asked for that address recently. Check your email, spam folder "
    "included, or try again later."
)
IP_WAIT = "Too many reset links have been asked for from here. Try again later."


def issue_reset(db: Session, user: User, by: User) -> tuple[str, datetime]:
    """A new reset token for `user`, and when it expires."""
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=RESET_HOURS)
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=expires_at,
            created_by_id=by.id,
        )
    )
    db.flush()
    return token, expires_at


# A tab, newline, backslash or the like, which could turn a path into another site.
UNSAFE_IN_PATH = re.compile(r"[\\\s\x00-\x1f\x7f]")


def same_site_path(raw: str | None) -> str | None:
    """`raw` if it is a path on this site, to go on to after the reset: a single
    leading `/`, never `//host` or `/\\host`, even once decoded. The page checks it
    again before it follows it."""
    if not raw or len(raw) > 2000 or not raw.startswith("/") or raw.startswith("//"):
        return None
    decoded = unquote(raw)
    if UNSAFE_IN_PATH.search(raw) or decoded.startswith("//") or UNSAFE_IN_PATH.search(decoded):
        return None
    return raw


def reset_url(token: str, next_path: str | None = None) -> str:
    url = f"{get_settings().public_url.rstrip('/')}/reset-password/{token}"
    safe = same_site_path(next_path)
    return f"{url}?next={quote(safe, safe='')}" if safe else url


def live_reset(db: Session, user: User) -> PasswordReset | None:
    """`user`'s unused, unexpired link, if they have one."""
    return db.scalar(
        select(PasswordReset).where(
            PasswordReset.user_id == user.id, PasswordReset.expires_at > datetime.now(UTC)
        )
    )


def cancel_reset(db: Session, user: User) -> bool:
    """Cancel `user`'s link. Whether there was a live one to cancel."""
    live = live_reset(db, user) is not None
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db.flush()
    return live


def user_for_reset(db: Session, token: str) -> User | None:
    """Whose live reset token this is, or None."""
    return db.scalar(
        select(User)
        .join(PasswordReset, PasswordReset.user_id == User.id)
        .where(
            PasswordReset.token_hash == hash_token(token),
            PasswordReset.expires_at > datetime.now(UTC),
        )
    )


def use_reset(db: Session, user: User) -> None:
    """Spend `user`'s reset link and end every session they had."""
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db.execute(
        update(SignInSession)
        .where(SignInSession.user_id == user.id, SignInSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.flush()


def requests_since(db: Session, key: str, value: str, window: timedelta) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == REQUESTED,
                AuditEvent.data[key].astext == value,
                AuditEvent.created_at > func.now() - window,
            )
        )
        or 0
    )


def limited(db: Session, address: str, ip: str | None) -> str | None:
    """Why someone asking for a link to `address` from `ip` must wait, or None.

    Takes a lock until the transaction ends, so two requests at once cannot both
    slip under a limit."""
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(REQUESTED))))
    address = address.strip().lower()
    if any(requests_since(db, "email", address, w) >= most for w, most in ADDRESS_LIMITS):
        return ADDRESS_WAIT
    if ip and any(requests_since(db, "ip", ip, w) >= most for w, most in IP_LIMITS):
        return IP_WAIT
    return None


def request_reset(
    db: Session, address: str, ip: str | None, next_path: str | None = None
) -> tuple[User, str] | None:
    """Someone asks for a link to `address` themselves. Logs the request, and if an
    account uses the address, makes it a link: the account and the link, to email.
    The link goes on to `next_path` once the password is set, if that is a path on
    this site (where they were going when they found they had forgotten it)."""
    address = address.strip().lower()
    user = db.scalar(
        select(User).where(func.lower(User.email) == address, User.merged_into_id.is_(None))
    )
    if user is None:
        record(db, None, REQUESTED, kind="unknown", email=address, ip=ip)
        return None
    record(db, user, REQUESTED, email=address, ip=ip, member=user.display_name, user_id=user.id)
    if suspensions.current(db, user.id) is not None:
        # The link would not work; the answer is the same as ever.
        return None
    token, _ = issue_reset(db, user, user)
    return user, reset_url(token, next_path)


def reset_email_text(user: User, url: str, by: User | None) -> str:
    if by is None:
        opening = (
            "Someone, hopefully you, asked to reset the password for your Horatio "
            f"account ({user.email}). Follow this link to set a new one:"
        )
        ignore = "If you didn't ask for it, ignore this email: your password stays as it is."
    else:
        opening = (
            f"{by.display_name}, Horatio's custodian, made you a link to set a new password "
            f"for your Horatio account ({user.email}):"
        )
        ignore = "Your password stays as it is until you use it."
    return (
        f"Hello {user.display_name},\n\n{opening}\n\n{url}\n\n"
        "It works once, for the next 24 hours, and signs you out everywhere else. "
        f"{ignore}\n\n-- \nSent by Horatio, {get_settings().public_url.rstrip('/')}\n"
    )


def email_reset(db: Session, user: User, url: str, by: User | None) -> str | None:
    """Email `user` their link, made by the custodian `by` or asked for by themselves
    (None), and log it. The mail server's refusal, if it refused."""
    mail = email.new_message(
        formataddr((user.display_name, user.email)), "Reset your Horatio password"
    )
    mail.set_content(reset_email_text(user, url, by))
    about = {"member": user.display_name, "user_id": user.id}
    try:
        email.deliver(mail)
    except SendError as error:
        record(db, by or user, "account.reset_email_failed", **about, error=str(error))
        return str(error)
    kind = "custodian" if by is not None else "self"
    record(db, by or user, "account.reset_sent", **about, kind=kind, to=user.email)
    return None
