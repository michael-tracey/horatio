"""One-time password reset links, made by the custodian for someone locked out.

Like sessions, the link holds a random token and the database only its hash.
A link works once, for a day; making a new one for the same person cancels the
old one.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from horatio.auth.sessions import hash_token
from horatio.models import PasswordReset, User
from horatio.models import Session as SignInSession

RESET_HOURS = 24


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
