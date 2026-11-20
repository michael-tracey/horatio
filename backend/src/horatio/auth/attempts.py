"""Limits on failed sign-ins and on sign-ups (#1059), kept in the database so every
instance of the app shares them and a restart forgets nothing.

A sign-in is limited by where it comes from (its IP address), and by the login
tried from there: an email and a handle are counted apart, as they would be for
no account, so being turned away never shows they are one. Never by the account
alone: anyone could then lock someone out by getting their password wrong on
purpose. A sign-up is limited by where it comes from. Both are checked before any
password is hashed or checked, so being turned away costs no Argon2, and the
answer is the same whether an account uses the login or not.

Each sign-in is counted as it starts, under a lock, so requests made at once
cannot all slip under a limit; signing in clears that login's tries from
there. Nothing typed is kept, only a hash of the login, and nothing for more
than a day.

Where a request comes from is the address uvicorn gives it. Behind nginx that is
the forwarded one, but only from the proxies `FORWARDED_ALLOW_IPS` names
(deploy/playbook.yml): any other peer's X-Forwarded-For is ignored.
"""

import ipaddress
from collections.abc import Collection
from datetime import timedelta
from hashlib import sha256

from fastapi import Request
from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.models import AuthAttempt

SIGN_IN = "sign_in"
SIGN_UP = "sign_up"
LOCK = "auth_attempts"
KEPT = timedelta(days=1)

# How many sign-ins may be tried from one place in each window and not succeed, and
# how many of them at one account. A household or a game venue may share an address.
SOURCE_LIMITS = ((timedelta(minutes=15), 20), (timedelta(days=1), 100))
ACCOUNT_LIMITS = ((timedelta(minutes=15), 5),)
# How many sign-ups, whether they make an account or not. A troupe may sign up
# together at a game, on the venue's Wi-Fi.
SIGN_UP_LIMITS = ((timedelta(hours=1), 20), (timedelta(days=1), 50))

SIGN_IN_WAIT = "Too many failed sign-ins from here. Try again later, or reset your password."
SIGN_UP_WAIT = "Too many sign-ups from here. Try again later."


def source(request: Request) -> str | None:
    """Where a request comes from. An IPv6 address counts as its /64, which one
    household or one server usually has the whole of."""
    host = request.client.host if request.client else None
    try:
        address = ipaddress.ip_address(host or "")
    except ValueError:
        return host
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network(f"{address}/64", strict=False))
    return str(address)


def login_key(login: str) -> str:
    """A hash of the login, read as horatio.api.auth.user_by_login reads it, so
    " Bob@Example.com" and "bob@example.com", or "@Bob" and "bob", count as one."""
    login = login.strip()
    if "@" not in login.removeprefix("@"):
        login = login.removeprefix("@")
    return sha256(login.lower().encode()).hexdigest()


def at(ip: str | None) -> ColumnElement[bool]:
    return AuthAttempt.ip_address == ip if ip is not None else AuthAttempt.ip_address.is_(None)


def over(
    db: Session,
    action: str,
    ip: str | None,
    limits: Collection[tuple[timedelta, int]],
    identity: str | None = None,
) -> bool:
    """Whether as many tries as a limit allows were made from `ip` within its window."""
    for window, most in limits:
        query = (
            select(func.count())
            .select_from(AuthAttempt)
            .where(
                AuthAttempt.action == action,
                at(ip),
                AuthAttempt.created_at > func.now() - window,
            )
        )
        if identity is not None:
            query = query.where(AuthAttempt.identity_hash == identity)
        if (db.scalar(query) or 0) >= most:
            return True
    return False


def lock(db: Session) -> None:
    """Hold the lock until the transaction ends, and forget tries over a day old."""
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(LOCK))))
    db.execute(delete(AuthAttempt).where(AuthAttempt.created_at <= func.now() - KEPT))


def may_sign_in(db: Session, login: str, ip: str | None) -> bool:
    """Whether someone at `ip` may try to sign in with `login` now. If so the try is
    counted, as failed until signed_in says otherwise, and committed, which lets go
    of the lock before the password is checked. If not, nothing is counted, and the
    lock is held until the caller commits."""
    if not get_settings().auth_limits:
        return True
    lock(db)
    identity = login_key(login)
    if over(db, SIGN_IN, ip, SOURCE_LIMITS) or over(db, SIGN_IN, ip, ACCOUNT_LIMITS, identity):
        return False
    db.add(AuthAttempt(action=SIGN_IN, identity_hash=identity, ip_address=ip))
    db.commit()
    return True


def signed_in(db: Session, login: str, ip: str | None) -> None:
    """Forget this login's tries from `ip`, the one that just succeeded included."""
    db.execute(
        delete(AuthAttempt).where(
            AuthAttempt.action == SIGN_IN,
            AuthAttempt.identity_hash == login_key(login),
            at(ip),
        )
    )


def may_sign_up(db: Session, ip: str | None) -> bool:
    """Whether someone at `ip` may sign up now. If so the try is counted and
    committed, so it counts even if the account is then refused (an email already
    used). If not, nothing is counted, and the lock is held until the caller commits."""
    if not get_settings().auth_limits:
        return True
    lock(db)
    if over(db, SIGN_UP, ip, SIGN_UP_LIMITS):
        return False
    db.add(AuthAttempt(action=SIGN_UP, ip_address=ip))
    db.commit()
    return True
