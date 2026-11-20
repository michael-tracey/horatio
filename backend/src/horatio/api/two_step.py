"""Setting up two-step sign-in from Account › Sign-in, and the custodian resetting it
for someone who has lost theirs (#1057). How signing in with it works is in
horatio.auth.two_step and horatio.api.auth."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio.api.players import player
from horatio.audit import record
from horatio.auth import two_step
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.passwords import verify_password
from horatio.auth.two_step import allowed_first
from horatio.models import User
from horatio.notifications import notify
from horatio.permissions import require_custodian

router = APIRouter(prefix="/two-step", tags=["auth"])


class TwoStepOut(BaseModel):
    # An authenticator app is set up, and signs them in.
    app: bool
    # This server can set one up: it has HORATIO_TOTP_KEY.
    apps_available: bool
    recovery_codes_left: int
    # Why they must have a second step: ["the custodian"]; empty if they needn't.
    required_by: list[str]
    # They must set one up before anything else.
    needed: bool


class AppSetup(BaseModel):
    # The secret, base32, for typing into an app that can't scan.
    secret: str
    # What the app scans, as a QR code: otpauth://totp/...
    uri: str


class Code(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class Password(BaseModel):
    password: str


class RecoveryCodes(BaseModel):
    # Shown once: only their hashes are kept. Empty if they had codes left already.
    recovery_codes: list[str]


class ResetIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


def state(db: DbSession, user: User) -> TwoStepOut:
    return TwoStepOut(
        app=two_step.has_app(db, user),
        apps_available=two_step.apps_available(),
        recovery_codes_left=two_step.recovery_codes_left(db, user),
        required_by=two_step.required_by(db, user),
        needed=two_step.needed(db, user),
    )


def check_password(user: User, password: str) -> None:
    """Turning off a second step, or making new recovery codes, asks for the password
    again, so a sign-in left open somewhere can't."""
    ok, _ = verify_password(password, user.password_hash)
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That's not your password.")


@router.get("")
@allowed_first
def two_step_state(db: DbSession, user: CurrentUser) -> TwoStepOut:
    """The signed-in person's second steps, and whether they must have one."""
    return state(db, user)


@router.post("/app")
@allowed_first
def start_app(db: DbSession, user: CurrentUser) -> AppSetup:
    """Start setting up an authenticator app: the secret to scan or type into it. It
    signs no one in until a code from it is given (POST /two-step/app/confirm)."""
    secret = two_step.start_app(db, user)
    db.commit()
    return AppSetup(secret=secret, uri=two_step.otpauth_uri(user, secret))


@router.post("/app/confirm")
@allowed_first
def confirm_app(body: Code, db: DbSession, user: CurrentUser) -> RecoveryCodes:
    """Turn on the authenticator app being set up with a code from it. With it come
    ten recovery codes, if they have none left."""
    if not two_step.check_app(db, user, body.code, setting_up=True):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That code isn't right. Check that your phone's clock is right, and give the"
            " newest code.",
        )
    record(db, user, "account.two_step_added", kind="app", member=user.display_name)
    codes: list[str] = []
    if not two_step.recovery_codes_left(db, user):
        codes = two_step.new_recovery_codes(db, user)
        record(db, user, "account.recovery_codes_made", member=user.display_name)
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


def keep_one(db: DbSession, user: User) -> None:
    """Refuse to turn off the last second step of someone who must have one."""
    why = two_step.required_by(db, user)
    if why and two_step.second_steps(db, user) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You need two-step sign-in as {why[0]}. Set up another second step before"
            " turning this one off.",
        )


def forget_if_none_left(db: DbSession, user: User) -> None:
    """With no second step left, recovery codes have nothing to stand in for."""
    if not two_step.has_second_step(db, user):
        two_step.forget_all(db, user)


@router.post("/app/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_app(body: Password, db: DbSession, user: CurrentUser) -> None:
    """Turn off their authenticator app, giving their password."""
    check_password(user, body.password)
    if not two_step.has_app(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have no authenticator app set up.")
    keep_one(db, user)
    two_step.remove_app(db, user)
    forget_if_none_left(db, user)
    record(db, user, "account.two_step_removed", kind="app", member=user.display_name)
    db.commit()


@router.post("/recovery-codes")
def new_recovery_codes(body: Password, db: DbSession, user: CurrentUser) -> RecoveryCodes:
    """Ten new recovery codes in place of the ones they had, giving their password."""
    check_password(user, body.password)
    if not two_step.has_second_step(db, user):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Set up a second step first: recovery codes stand in for it."
        )
    codes = two_step.new_recovery_codes(db, user)
    record(db, user, "account.recovery_codes_made", member=user.display_name)
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/reset/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset(user_id: uuid.UUID, body: ResetIn, db: DbSession, user: CurrentUser) -> None:
    """For the custodian: take away every second step someone has, and their recovery
    codes, when they have lost them, so their password alone signs them in again until
    they set up another. Recorded as a notice, and they are told."""
    require_custodian(user)
    person = player(db, user_id)
    if not two_step.has_second_step(db, person):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{person.display_name} has no second step.")
    two_step.forget_all(db, person)
    record(
        db,
        user,
        "account.two_step_reset",
        member=person.display_name,
        user_id=person.id,
        reason=body.reason,
    )
    notify(
        db,
        [person.id],
        "account.two_step_reset",
        f"{user.display_name}, the custodian, reset your two-step sign-in: {body.reason}. Your"
        " password alone signs you in until you set it up again.",
        "/account/sign-in",
    )
    db.commit()
