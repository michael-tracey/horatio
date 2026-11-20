"""Limits on sign-ins and on sign-ups (#1059, #1074), kept in the database so every
instance of the app shares them and a restart forgets nothing.

A sign-in is limited by where it comes from (its IP address): how many fail there,
and how many are tried there at all, so that no one, even with an account, can make
the server check passwords without end. Failed ones are limited too by the login
tried from there: an email and a handle are counted apart, as they would be for no
account, so being turned away never shows they are one. Never by the account alone:
anyone could then lock someone out by getting their password wrong on purpose. A
sign-up is limited by where it comes from. Both are checked before any password is
hashed or checked, so being turned away costs no Argon2, and the answer is the same
whether an account uses the login or not.

Each sign-in is counted as it starts, under a lock, so requests made at once
cannot all slip under a limit; signing in stops that login's tries from there
counting as failed. Nothing typed is kept, only a hash of the login, and nothing
for more than a day.

Where a request comes from is the address uvicorn gives it. Behind nginx that is
the forwarded one, but only from the proxies `FORWARDED_ALLOW_IPS` names
(deploy/playbook.yml): any other peer's X-Forwarded-For is ignored.
"""

import ipaddress
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID

from fastapi import Request
from sqlalchemy import ColumnElement, and_, delete, exists, func, null, select, update
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.models import AuthAttempt

SIGN_IN = "sign_in"
# A sign-in that succeeded, and the failed ones before it at its login from there:
# counted among all sign-ins, no longer as failed.
SIGNED_IN = "signed_in"
SIGN_UP = "sign_up"
# The first try a limit turned away in its window, from one place (at one login, for
# a limit at one login), so the ones after it are logged at debug. Never counted.
HELD = {SIGN_IN: "sign_in_held", SIGN_UP: "sign_up_held"}
LOCK = "auth_attempts"
KEPT = timedelta(days=1)

# How many sign-ins may be tried from one place in each window and not succeed, and
# how many of them at one account. A household or a game venue may share an address.
SOURCE_LIMITS = ((timedelta(minutes=15), 20), (timedelta(days=1), 100))
ACCOUNT_LIMITS = ((timedelta(minutes=15), 5),)
# How many sign-ins may be tried from one place in each window, whether they succeed
# or not: three times the failed ones, as a venue's Wi-Fi may see a whole troupe sign
# in as a game starts, some on two devices, and sign in again after a break.
ALL_SIGN_IN_LIMITS = ((timedelta(minutes=15), 60), (timedelta(days=1), 300))
# How many sign-ups, whether they make an account or not. A troupe may sign up
# together at a game, on the venue's Wi-Fi.
SIGN_UP_LIMITS = ((timedelta(hours=1), 20), (timedelta(days=1), 50))

SIGN_IN_WAIT = "Too many failed sign-ins from here. Try again later, or reset your password."
SIGN_INS_WAIT = "Too many sign-ins from here. Try again later."
SIGN_UP_WAIT = "Too many sign-ups from here. Try again later."


def within(window: timedelta) -> str:
    """A window as words: "15 minutes", "an hour", "a day"."""
    for unit, length in (("day", timedelta(days=1)), ("hour", timedelta(hours=1))):
        if window >= length and not window % length:
            n = window // length
            return f"a{'n' if unit == 'hour' else ''} {unit}" if n == 1 else f"{n} {unit}s"
    return f"{window // timedelta(minutes=1)} minutes"


@dataclass(frozen=True)
class Limit:
    """At most `most` tries of the `counted` kinds in `window` from one place, and at
    one login if `per_login`. It holds back tries at `action`."""

    # Names it in the audit log: failed, failed_at_login, sign_ins or sign_ups.
    key: str
    # What it counts, as the custodian reads it: "failed sign-ins".
    what: str
    action: str
    counted: tuple[str, ...]
    window: timedelta
    most: int
    per_login: bool = False

    def __str__(self) -> str:
        """As the custodian reads it: "20 failed sign-ins in 15 minutes"."""
        return f"{self.most} {self.what} in {within(self.window)}"

    def counts(self, identity: str | None = None) -> ColumnElement[bool]:
        """The tries it counts, from wherever they come: for a limit at one login, at
        the login hashed as `identity` if given, otherwise at any."""
        counted = and_(
            AuthAttempt.action.in_(self.counted),
            AuthAttempt.created_at > func.now() - self.window,
        )
        if self.per_login and identity is not None:
            counted = and_(counted, AuthAttempt.identity_hash == identity)
        return counted


def limits(
    key: str,
    what: str,
    action: str,
    counted: tuple[str, ...],
    table: Collection[tuple[timedelta, int]],
    per_login: bool = False,
) -> tuple[Limit, ...]:
    return tuple(Limit(key, what, action, counted, w, most, per_login) for w, most in table)


# Each action's limits, in the order they are checked: a try over more than one is
# said to be held back by the first.
LIMITS: dict[str, tuple[Limit, ...]] = {
    SIGN_IN: (
        *limits("failed", "failed sign-ins", SIGN_IN, (SIGN_IN,), SOURCE_LIMITS),
        *limits("sign_ins", "sign-ins", SIGN_IN, (SIGN_IN, SIGNED_IN), ALL_SIGN_IN_LIMITS),
        *limits(
            "failed_at_login",
            "failed sign-ins at one login",
            SIGN_IN,
            (SIGN_IN,),
            ACCOUNT_LIMITS,
            per_login=True,
        ),
    ),
    SIGN_UP: limits("sign_ups", "sign-ups", SIGN_UP, (SIGN_UP,), SIGN_UP_LIMITS),
}


@dataclass(frozen=True)
class Held:
    """A try turned away: by which limit, and whether it is the first turned away from
    there (at that login, for a limit at one login) in the limit's window."""

    limit: Limit
    first: bool

    @property
    def wait(self) -> str:
        """What the person turned away is told."""
        if self.limit.action == SIGN_UP:
            return SIGN_UP_WAIT
        return SIGN_INS_WAIT if self.limit.key == "sign_ins" else SIGN_IN_WAIT


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


def by(identity: str | None) -> ColumnElement[bool]:
    if identity is None:
        return AuthAttempt.identity_hash.is_(None)
    return AuthAttempt.identity_hash == identity


def held_back(db: Session, action: str, ip: str | None, identity: str | None = None) -> Held | None:
    """The limit, if any, that a try at `action` from `ip`, at the login hashed as
    `identity`, is over, counted in one query. The first try a limit turns away in
    its window is noted, so the caller logs only that one at info."""
    checked = LIMITS[action]
    counts = db.execute(
        select(*(func.count().filter(limit.counts(identity)) for limit in checked)).where(
            at(ip), AuthAttempt.created_at > func.now() - max(c.window for c in checked)
        )
    ).one()
    for limit, count in zip(checked, counts, strict=True):
        if count >= limit.most:
            whose = identity if limit.per_login else None
            noted = exists().where(
                AuthAttempt.action == HELD[action],
                at(ip),
                by(whose),
                AuthAttempt.created_at > func.now() - limit.window,
            )
            first = not db.scalar(select(noted))
            if first:
                db.add(AuthAttempt(action=HELD[action], identity_hash=whose, ip_address=ip))
            return Held(limit, first)
    return None


def lock(db: Session) -> None:
    """Hold the lock until the transaction ends, and forget tries over a day old."""
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(LOCK))))
    db.execute(delete(AuthAttempt).where(AuthAttempt.created_at <= func.now() - KEPT))


def sign_in_held_back(db: Session, login: str, ip: str | None) -> Held | None:
    """What holds back someone at `ip` from trying to sign in with `login` now, if
    anything. If nothing, the try is counted, as failed until signed_in says
    otherwise, and committed, which lets go of the lock before the password is
    checked. If something, the try is not counted, and the lock is held until the
    caller commits."""
    if not get_settings().auth_limits:
        return None
    lock(db)
    identity = login_key(login)
    held = held_back(db, SIGN_IN, ip, identity)
    if held is None:
        db.add(AuthAttempt(action=SIGN_IN, identity_hash=identity, ip_address=ip))
        db.commit()
    return held


def signed_in(db: Session, login: str, ip: str | None) -> None:
    """Count this login's tries from `ip`, the one that just succeeded included, as
    sign-ins, no longer as failed ones."""
    db.execute(
        update(AuthAttempt)
        .where(AuthAttempt.action == SIGN_IN, AuthAttempt.identity_hash == login_key(login), at(ip))
        .values(action=SIGNED_IN)
    )


def sign_up_held_back(db: Session, ip: str | None) -> Held | None:
    """What holds back someone at `ip` from signing up now, if anything. If nothing,
    the try is counted and committed, so it counts even if the account is then
    refused (an email already used). If something, the try is not counted, and the
    lock is held until the caller commits."""
    if not get_settings().auth_limits:
        return None
    lock(db)
    held = held_back(db, SIGN_UP, ip)
    if held is None:
        db.add(AuthAttempt(action=SIGN_UP, ip_address=ip))
        db.commit()
    return held


# --- the custodian's view (Custodian › Audit's Throttled now card) -------------------------


@dataclass(frozen=True)
class Throttle:
    """A place, and a login for a limit at one login, that a limit holds back now."""

    limit: Limit
    ip: str | None
    identity: str | None
    # When it is under the limit again, if nothing more is tried from there.
    clears: datetime
    # The newest try it counts.
    newest: UUID

    @property
    def id(self) -> str:
        """Names it to unblock, giving nothing of the address away: one place may be
        over more than one limit, and their newest try may be the same."""
        return f"{self.limit.key}.{self.limit.window // timedelta(minutes=1)}.{self.newest}"


def throttled(db: Session) -> list[Throttle]:
    """Every place a limit holds back now, the soonest to clear first."""
    found: list[Throttle] = []
    for limit in (limit for checked in LIMITS.values() for limit in checked):
        # Grouped by login too for a limit at one login.
        login = AuthAttempt.identity_hash if limit.per_login else null()
        group = (AuthAttempt.ip_address, login) if limit.per_login else (AuthAttempt.ip_address,)
        newest = AuthAttempt.created_at.desc(), AuthAttempt.id.desc()
        rows = db.execute(
            select(
                AuthAttempt.ip_address,
                login,
                func.array_agg(aggregate_order_by(AuthAttempt.created_at, *newest)),
                func.array_agg(aggregate_order_by(AuthAttempt.id, *newest)),
            )
            .where(limit.counts())
            .group_by(*group)
            .having(func.count() >= limit.most)
        )
        for ip, identity, times, ids in rows:
            found.append(
                Throttle(
                    limit=limit,
                    ip=ip,
                    identity=identity,
                    # Once the `most`th newest is out of the window, fewer are left in it.
                    clears=times[limit.most - 1] + limit.window,
                    newest=ids[0],
                )
            )
    return sorted(found, key=lambda t: t.clears)


def unblock(db: Session, throttle: Throttle) -> None:
    """Forget every try of the kind from this place, or for a limit at one login, every
    try at that login from there: it starts afresh."""
    action = throttle.limit.action
    kinds = {kind for limit in LIMITS[action] for kind in limit.counted} | {HELD[action]}
    query = delete(AuthAttempt).where(AuthAttempt.action.in_(kinds), at(throttle.ip))
    if throttle.limit.per_login:
        query = query.where(AuthAttempt.identity_hash == throttle.identity)
    db.execute(query)
