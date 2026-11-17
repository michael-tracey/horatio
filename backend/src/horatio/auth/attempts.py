"""Shared, short-lived throttles for sign-in and account creation."""

from datetime import timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from horatio.models import AuthAttempt

LOGIN_FAILED = "login_failed"
LOGIN_PENDING = "login_pending"
SIGNUP = "signup"
LOCK = "auth_attempts"

LOGIN_WAIT = "Too many sign-in attempts. Try again later."
SIGNUP_WAIT = "Too many sign-up attempts. Try again later."


def login_key(login: str) -> str:
    """Normalize a login the same way the auth lookup does, then avoid storing it."""
    normalized = login.strip()
    if "@" in normalized.removeprefix("@"):
        normalized = normalized.lower()
    else:
        normalized = normalized.removeprefix("@").lower()
    return sha256(normalized.encode()).hexdigest()


def _count(
    db: Session,
    action: str,
    since: timedelta,
    *,
    ip: str | None = None,
    identity: str | None = None,
) -> int:
    query = (
        select(func.count())
        .select_from(AuthAttempt)
        .where(
            AuthAttempt.action == action,
            AuthAttempt.created_at > func.now() - since,
        )
    )
    query = query.where(
        AuthAttempt.ip_address == ip if ip is not None else AuthAttempt.ip_address.is_(None)
    )
    if identity is not None:
        query = query.where(AuthAttempt.identity_hash == identity)
    return db.scalar(query) or 0


def _lock_and_prune(db: Session) -> None:
    # Serialize checks and writes so simultaneous requests cannot all pass a limit.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(LOCK))))
    db.execute(delete(AuthAttempt).where(AuthAttempt.created_at <= func.now() - timedelta(days=1)))


def begin_login(db: Session, login: str, ip: str | None) -> UUID | None:
    """Reserve a login attempt under the shared lock, then release it before Argon2."""
    _lock_and_prune(db)
    if ip is None:
        db.commit()
        return None
    identity = login_key(login)
    actions = (LOGIN_FAILED, LOGIN_PENDING)
    recent = sum(_count(db, action, timedelta(minutes=15), ip=ip) for action in actions)
    daily = sum(_count(db, action, timedelta(days=1), ip=ip) for action in actions)
    pair = sum(
        _count(db, action, timedelta(minutes=15), ip=ip, identity=identity) for action in actions
    )
    if recent >= 20 or daily >= 100 or pair >= 5:
        db.commit()
        return None
    attempt = AuthAttempt(action=LOGIN_PENDING, identity_hash=identity, ip_address=ip)
    db.add(attempt)
    db.flush()
    attempt_id = attempt.id
    db.commit()
    return attempt_id


def failed_login(db: Session, attempt_id: UUID | None) -> None:
    if attempt_id is None:
        return
    db.execute(update(AuthAttempt).where(AuthAttempt.id == attempt_id).values(action=LOGIN_FAILED))
    # The failed-password response is an HTTPException, so persist the failure first.
    db.commit()


def successful_login(db: Session, attempt_id: UUID | None, login: str, ip: str | None) -> None:
    if attempt_id is None:
        return
    # Clear failures for this account and source, then remove this successful reservation.
    db.execute(
        delete(AuthAttempt).where(
            AuthAttempt.action == LOGIN_FAILED,
            AuthAttempt.identity_hash == login_key(login),
            AuthAttempt.ip_address == ip if ip is not None else AuthAttempt.ip_address.is_(None),
        )
    )
    db.execute(delete(AuthAttempt).where(AuthAttempt.id == attempt_id))


def check_signup(db: Session, ip: str | None) -> bool:
    """Count all signup submissions by source, including duplicate-account attempts."""
    _lock_and_prune(db)
    if ip is None:
        return True
    if _count(db, SIGNUP, timedelta(hours=1), ip=ip) >= 5:
        return False
    return _count(db, SIGNUP, timedelta(days=1), ip=ip) < 20


def signup_attempt(db: Session, ip: str | None) -> None:
    db.add(AuthAttempt(action=SIGNUP, ip_address=ip))
    # Keep attempts even when the signup route later returns a conflict.
    db.commit()
