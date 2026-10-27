"""Server-side sign-in sessions. The cookie holds a random token; the database
holds only its hash, so a leaked database cannot be used to sign in."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import suspensions
from horatio.config import get_settings
from horatio.models import Session as SignInSession
from horatio.models import User


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User) -> str:
    """Start a session for `user` and return the token for the cookie. Refused,
    saying why, while they are suspended, however they signed in."""
    suspensions.refuse(db, user)
    token = secrets.token_urlsafe(32)
    db.add(
        SignInSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=get_settings().session_days),
        )
    )
    db.flush()
    return token


def user_for_token(db: Session, token: str) -> User | None:
    """The user a live session token belongs to, or None. Never a merged account,
    nor someone suspended: their sessions are ended, and this makes sure."""
    return db.scalar(
        select(User)
        .join(SignInSession, SignInSession.user_id == User.id)
        .where(
            SignInSession.token_hash == hash_token(token),
            SignInSession.revoked_at.is_(None),
            SignInSession.expires_at > datetime.now(UTC),
            User.merged_into_id.is_(None),
            ~suspensions.suspended_user(),
        )
    )


def end_session(db: Session, token: str) -> None:
    session = db.scalar(select(SignInSession).where(SignInSession.token_hash == hash_token(token)))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.flush()
