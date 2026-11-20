"""Who the limits on sign-ins and sign-ups hold back now, for the custodian, and
unblocking them (#1074): the Throttled now card on Custodian › Audit. Wrong
second-step codes (#1057) are limited at an account from anywhere too, and password
changes (#1095) only there.

An address is shown only while the custodian records IP addresses with sign-in
events (#1066); otherwise only its start, as 198.51.x.x. Unblocking works either
way: each entry is named by its limit and the newest try it counts, never by its
address."""

import ipaddress
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from horatio import audit
from horatio.auth import attempts
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import User
from horatio.permissions import require_custodian

router = APIRouter(prefix="/throttled", tags=["custodian"])

# What is held back: sign-ins, sign-ups, second steps or password changes (#1095).
Kind = Literal["sign_in", "sign_up", "second_step", "password_change"]


class ThrottledOut(BaseModel):
    # Names it to unblock.
    id: str
    held: Kind
    # The IP address (an IPv6 /64), or its start while sign-in events keep no IP
    # addresses; None for requests that came with none.
    address: str | None
    masked: bool
    # For a limit at one login: whose it is, "@agnes" or an email, or None for a
    # login no account uses.
    per_login: bool
    # For a limit at one account from anywhere (wrong second-step codes, password
    # changes): no address.
    anywhere: bool
    login: str | None
    # "20 failed sign-ins in 15 minutes".
    limit: str
    clears: datetime


HELD: dict[str, Kind] = {
    attempts.SIGN_IN: "sign_in",
    attempts.SIGN_UP: "sign_up",
    attempts.SECOND_STEP: "second_step",
    attempts.PASSWORD_CHANGE: "password_change",
}


class Unblock(BaseModel):
    id: str


def masked(ip: str) -> str:
    """The start of an address, enough to tell most apart: "198.51.x.x"."""
    try:
        network = ipaddress.ip_network(ip, strict=False)
    except ValueError:
        return "hidden"
    if network.version == 4:
        return ".".join(str(network.network_address).split(".")[:2] + ["x", "x"])
    return ":".join(network.network_address.exploded.split(":")[:2]) + ":x:x::/64"


def logins(db: DbSession, hashed: set[str]) -> dict[str, str]:
    """Whose each hashed login is: an account's "@handle" or email; for second steps
    and password changes, counted by account, its "@handle"."""
    found: dict[str, str] = {}
    if not hashed:
        return found
    users = db.execute(
        select(User.id, User.email, User.handle).where(User.merged_into_id.is_(None))
    )
    for user_id, email, handle in users:
        for login in (email, f"@{handle}"):
            if (key := attempts.login_key(login)) in hashed:
                found[key] = login
        if (key := attempts.account_key(user_id)) in hashed:
            found[key] = f"@{handle}"
    return found


def held_now(db: DbSession, user: User) -> tuple[list[attempts.Throttle], bool, dict[str, str]]:
    require_custodian(user)
    throttles = attempts.throttled(db)
    shown = audit.settings(db).sign_in_ips
    whose = logins(db, {t.identity for t in throttles if t.identity is not None})
    return throttles, shown, whose


@router.get("")
def throttled(db: DbSession, user: CurrentUser) -> list[ThrottledOut]:
    """For the custodian: every address a limit on sign-ins or sign-ups holds back
    now, and when each clears, the soonest first."""
    throttles, shown, whose = held_now(db, user)
    return [
        ThrottledOut(
            id=t.id,
            held=HELD[t.limit.action],
            address=t.ip if t.ip is None or shown else masked(t.ip),
            masked=t.ip is not None and not shown,
            per_login=t.limit.per_login,
            anywhere=t.limit.anywhere,
            login=whose.get(t.identity) if t.identity else None,
            limit=str(t.limit),
            clears=t.clears,
        )
        for t in throttles
    ]


@router.post("/unblock", status_code=status.HTTP_204_NO_CONTENT)
def unblock(body: Unblock, db: DbSession, user: CurrentUser) -> None:
    """For the custodian: forget the tries that hold an address back (at a login, for
    a limit at one login), so it may try again at once. Recorded as a notice."""
    throttles, shown, whose = held_now(db, user)
    throttle = next((t for t in throttles if t.id == body.id), None)
    if throttle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That address isn't held back any more.")
    attempts.unblock(db, throttle)
    limit = throttle.limit
    data: dict[str, Any] = {"limit": limit.key, "rule": str(limit)}
    if limit.action == attempts.SIGN_UP:
        data["kind"] = "sign_up"
    elif limit.action == attempts.SECOND_STEP:
        data["kind"] = "second_step"
        if limit.per_login:
            data["kind"] = "second_step_account"
            data["login"] = whose.get(throttle.identity or "", "an account no longer here")
    elif limit.action == attempts.PASSWORD_CHANGE:
        data["kind"] = "password_change"
        data["login"] = whose.get(throttle.identity or "", "an account no longer here")
    elif limit.per_login:
        data["kind"] = "login"
        data["login"] = whose.get(throttle.identity or "", "a login no account uses")
    if throttle.ip and shown:
        data["ip"] = throttle.ip
    audit.record(db, user, "account.throttle_lifted", **data)
    db.commit()
