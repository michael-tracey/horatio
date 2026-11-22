"""Server-side sign-in sessions. The cookie holds a random token; the database
holds only its hash, so a leaked database cannot be used to sign in.

Each keeps the browser it was started from, the address while the custodian records
them with sign-in events, and when it was last used (#1193), so the person can see
where they're signed in (horatio.api.account_security) and sign out there."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import ColumnElement, select, update
from sqlalchemy.orm import Session

from horatio import suspensions
from horatio.audit import sign_in_ip
from horatio.config import get_settings
from horatio.models import Session as SignInSession
from horatio.models import User


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# A session's last use is written at most this often, so a page asking for many
# things at once writes nothing more than once in a while.
ACTIVE_EVERY = timedelta(minutes=5)
# As much of a User-Agent as is kept: enough to tell the browser and system.
USER_AGENT_LENGTH = 512


def start_session(db: Session, user: User, request: Request) -> str:
    """Start a session for `user` and return the token for the cookie. Refused,
    saying why, while they are suspended, however they signed in. It keeps the
    browser `request` came from, and its address only while the custodian records
    addresses with sign-in events."""
    suspensions.refuse(db, user)
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(
        SignInSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(days=get_settings().session_days),
            user_agent=(request.headers.get("user-agent") or "")[:USER_AGENT_LENGTH] or None,
            ip_address=sign_in_ip(db, request).get("ip"),
            last_active_at=now,
        )
    )
    db.flush()
    return token


def live() -> list[ColumnElement[bool]]:
    """What makes a session one that still signs someone in."""
    return [SignInSession.revoked_at.is_(None), SignInSession.expires_at > datetime.now(UTC)]


def user_for_token(db: Session, token: str, *, touch: bool = False) -> User | None:
    """The user a live session token belongs to, or None. Never a merged account,
    nor someone suspended: their sessions are ended, and this makes sure.

    With `touch`, for a request the person makes, the session's last use is moved to
    now if it is more than ACTIVE_EVERY old, and committed: at most one write in a
    while, as the time comes with the same query."""
    row = db.execute(
        select(User, SignInSession.id, SignInSession.last_active_at)
        .join(SignInSession, SignInSession.user_id == User.id)
        .where(
            SignInSession.token_hash == hash_token(token),
            *live(),
            User.merged_into_id.is_(None),
            ~suspensions.suspended_user(),
        )
    ).first()
    if row is None:
        return None
    user, session_id, last_active_at = row
    now = datetime.now(UTC)
    if touch and (last_active_at is None or last_active_at <= now - ACTIVE_EVERY):
        db.execute(
            update(SignInSession).where(SignInSession.id == session_id).values(last_active_at=now)
        )
        db.commit()
    return user


def end_session(db: Session, token: str) -> None:
    session = db.scalar(select(SignInSession).where(SignInSession.token_hash == hash_token(token)))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.flush()


def end_other_sessions(db: Session, user: User, keep: str | None) -> None:
    """End every session `user` has but the one with the token `keep`: after they
    change their password, so whoever else had it is signed out."""
    others = [SignInSession.user_id == user.id, *live()]
    if keep:
        others.append(SignInSession.token_hash != hash_token(keep))
    db.execute(update(SignInSession).where(*others).values(revoked_at=datetime.now(UTC)))
    db.flush()
