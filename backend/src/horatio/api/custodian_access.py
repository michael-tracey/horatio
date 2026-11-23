"""Switching custodian access on and off (horatio.auth.custodian_access): the custodian
gives their second step again, and a reason, to use the custodian's powers for an hour
from their last use of them; a banner shows while it is on, with Switch off."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from horatio.api.two_step import check_password, this_session, used_up
from horatio.audit import record, sign_in_ip
from horatio.auth import attempts, passkeys, two_step
from horatio.auth import custodian_access as access_on
from horatio.auth.deps import CurrentUser, DbSession, MaybeUser
from horatio.auth.two_step import allowed_first
from horatio.models import CustodianAccess, User
from horatio.permissions import acting_of

router = APIRouter(prefix="/custodian-access", tags=["custodian access"])

NOT_CUSTODIAN = "Only the custodian can switch on custodian access."


class CustodianAccessOut(BaseModel):
    """The custodian's own: whether custodian access is on for this sign-in."""

    on: bool
    # Why they switched it on, and when it ends unless they use it again.
    reason: str | None = None
    ends_at: datetime | None = None
    # What switching it on asks for: their second steps ("app", "passkey",
    # "recovery_code"), or none, for their password.
    second_step: list[str]


class SwitchOn(BaseModel):
    # Why: for the audit log, and for the lead storyteller of a troupe they play in.
    reason: str = Field(max_length=500)
    # Six digits from their authenticator app, or a recovery code.
    code: str | None = Field(default=None, max_length=64)
    # A passkey's answer to /custodian-access/passkey/options, as JSON.
    credential: dict[str, Any] | None = None
    # Only with no second step set up.
    password: str | None = Field(default=None, max_length=1024)


def state(db: DbSession, user: User, access: CustodianAccess | None) -> CustodianAccessOut:
    return CustodianAccessOut(
        on=access is not None,
        reason=access.reason if access else None,
        ends_at=access_on.ends_at(access) if access else None,
        second_step=two_step.methods(db, user),
    )


def custodian(user: User) -> None:
    if not user.is_custodian:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_CUSTODIAN)


@router.get("")
@allowed_first
def custodian_access(db: DbSession, user: MaybeUser) -> CustodianAccessOut | None:
    """Whether the signed-in custodian has custodian access on; None for anyone else."""
    if user is None or not user.is_custodian:
        return None
    acting = acting_of(user)
    access = db.get(CustodianAccess, acting.access_id) if acting and acting.access_id else None
    return state(db, user, access)


@router.post("/passkey/options")
def passkey_options(request: Request, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    """What the browser needs to give one of the custodian's passkeys, to switch on
    custodian access: WebAuthn's PublicKeyCredentialRequestOptions, as JSON."""
    custodian(user)
    if not two_step.passkey_count(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "You have no passkey set up.")
    options = passkeys.asking_options(db, this_session(request, db, user), user)
    db.commit()
    return options


@router.post("", status_code=status.HTTP_201_CREATED)
def switch_on(
    body: SwitchOn, request: Request, db: DbSession, user: CurrentUser
) -> CustodianAccessOut:
    """Switch custodian access on for this sign-in, giving a second step again (a code,
    a recovery code or a passkey) or, with none set up, the password, and a reason. Wrong
    second steps count against the same limits as signing in."""
    custodian(user)
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Say why you're switching it on."
        )
    session = this_session(request, db, user)
    methods = two_step.methods(db, user)
    if methods:
        given_second_step(request, db, user, body, methods)
    else:
        check_password(request, db, user, body.password or "")
        used_up(request, db, user)
    access = access_on.switch_on(db, user, session.id, reason)
    db.commit()
    return state(db, user, access)


def given_second_step(
    request: Request, db: DbSession, user: User, body: SwitchOn, methods: list[str]
) -> None:
    """Check the second step given, under the limits on second steps (horatio.auth.attempts),
    and record a wrong one."""
    ip = attempts.source(request)
    whose: dict[str, Any] = {"member": user.display_name, "user_id": user.id}
    if body.credential is not None:
        method = "passkey"
    elif body.code and two_step.is_app_code(body.code):
        method = "app"
    elif body.code:
        method = "recovery_code"
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give your second step.")
    if (held := attempts.second_step_held_back(db, user.id, ip)) is not None:
        record(
            db,
            user,
            "account.second_step_throttled"
            if held.first
            else "account.second_step_throttled_again",
            limit=held.limit.key,
            **whose,
            **sign_in_ip(request),
        )
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, held.wait)
    if method == "passkey":
        assert body.credential is not None
        right = passkeys.check_asked(db, this_session(request, db, user), user, body.credential)
    elif method == "app":
        right = method in methods and two_step.check_app(db, user, body.code or "")
    else:
        right = two_step.use_recovery_code(db, user, body.code or "")
    if not right:
        record(
            db,
            user,
            "account.custodian_access_refused",
            kind=method,
            **whose,
            **sign_in_ip(request),
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG[method])
    attempts.second_step_passed(db, user.id, ip)
    if method == "recovery_code":
        record(
            db,
            user,
            "account.recovery_code_used",
            left=two_step.recovery_codes_left(db, user),
            **whose,
            **sign_in_ip(request),
        )


WRONG = {
    "app": "That code isn't right.",
    "recovery_code": "That recovery code isn't right, or has been used.",
    "passkey": "That passkey didn't confirm it's you. Try again, or use another way.",
}


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
@allowed_first
def switch_off(request: Request, db: DbSession, user: CurrentUser) -> None:
    """Switch custodian access off for this sign-in, at once."""
    session = this_session(request, db, user)
    access_on.end_for_session(db, session.id, "stopped")
    db.commit()
