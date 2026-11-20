"""Setting up two-step sign-in from Account › Sign-in: an authenticator app, passkeys
and recovery codes; the custodian resetting it for someone who has lost theirs; and a
troupe's lead storyteller asking it of the troupe's staff (#1057). How signing in with
it works is in horatio.auth.two_step, horatio.auth.passkeys and horatio.api.auth."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio.api.players import player
from horatio.api.troupes import get_troupe
from horatio.audit import record
from horatio.auth import passkeys, two_step
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.passwords import verify_password
from horatio.auth.sessions import hash_token
from horatio.auth.two_step import allowed_first
from horatio.config import get_settings
from horatio.models import Passkey, Troupe, TroupeStaff, User
from horatio.models import Session as SignInSession
from horatio.notifications import notify
from horatio.permissions import TroupeAction, require_custodian, require_troupe_action

router = APIRouter(prefix="/two-step", tags=["auth"])


class PasskeyOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None


class TwoStepOut(BaseModel):
    # An authenticator app is set up, and signs them in.
    app: bool
    # This server can set one up: it has HORATIO_TOTP_KEY.
    apps_available: bool
    passkeys: list[PasskeyOut]
    # This server's address lets browsers make passkeys for it (https, or localhost).
    passkeys_available: bool
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


class NewPasskey(BaseModel):
    # The browser's PublicKeyCredential from navigator.credentials.create, as JSON.
    credential: dict[str, Any]
    name: str = Field(default="Passkey", max_length=60)


class StaffTwoStepIn(BaseModel):
    required: bool


class StaffMemberTwoStep(BaseModel):
    user_id: uuid.UUID
    two_step: bool


class StaffTwoStepOut(BaseModel):
    # The troupe asks a second step of its staff.
    required: bool
    # The signed-in person can change that: the lead storyteller, or the custodian.
    can_change: bool
    # Whether each of its staff, the lead storyteller included, has a second step.
    staff: list[StaffMemberTwoStep]


class ResetIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


def state(db: DbSession, user: User) -> TwoStepOut:
    return TwoStepOut(
        app=two_step.has_app(db, user),
        apps_available=two_step.apps_available(),
        passkeys=[
            PasskeyOut(id=p.id, name=p.name, created_at=p.created_at, last_used_at=p.last_used_at)
            for p in passkeys.mine(db, user)
        ],
        passkeys_available=passkeys.available(),
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
    codes = first_codes(db, user)
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


def first_codes(db: DbSession, user: User) -> list[str]:
    """Ten recovery codes with someone's first second step, if they have none left."""
    if two_step.recovery_codes_left(db, user):
        return []
    codes = two_step.new_recovery_codes(db, user)
    record(db, user, "account.recovery_codes_made", member=user.display_name)
    return codes


def this_session(request: Request, db: DbSession, user: User) -> SignInSession:
    """The sign-in session this request comes with: a passkey being added keeps its
    challenge there."""
    token = request.cookies.get(get_settings().session_cookie_name, "")
    session = db.scalar(
        select(SignInSession).where(
            SignInSession.token_hash == hash_token(token), SignInSession.user_id == user.id
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first.")
    return session


@router.post("/passkeys/options")
@allowed_first
def passkey_options(request: Request, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    """What the browser needs to make a passkey for Horatio: WebAuthn's
    PublicKeyCredentialCreationOptions, as JSON. Its challenge works once."""
    if not passkeys.available():
        raise HTTPException(status.HTTP_409_CONFLICT, "Passkeys need this site on https.")
    options = passkeys.adding_options(db, this_session(request, db, user), user)
    db.commit()
    return options


@router.post("/passkeys")
@allowed_first
def add_passkey(
    body: NewPasskey, request: Request, db: DbSession, user: CurrentUser
) -> RecoveryCodes:
    """Keep the passkey the browser made. With someone's first second step come ten
    recovery codes."""
    passkey = passkeys.add(db, this_session(request, db, user), user, body.credential, body.name)
    record(
        db,
        user,
        "account.two_step_added",
        kind="passkey",
        member=user.display_name,
        name=passkey.name,
    )
    codes = first_codes(db, user)
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/passkeys/{passkey_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_passkey(passkey_id: uuid.UUID, body: Password, db: DbSession, user: CurrentUser) -> None:
    """Remove one of their passkeys, giving their password."""
    check_password(user, body.password)
    passkey = db.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such passkey.")
    keep_one(db, user)
    name = passkey.name
    db.delete(passkey)
    db.flush()
    forget_if_none_left(db, user)
    record(
        db, user, "account.two_step_removed", kind="passkey", member=user.display_name, name=name
    )
    db.commit()


def keep_one(db: DbSession, user: User) -> None:
    """Refuse to turn off the last second step of someone who must have one."""
    why = two_step.required_by(db, user)
    if why and two_step.second_steps(db, user) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You need two-step sign-in as {why[0]}. Set up another second step before"
            " removing this one.",
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


troupe_router = APIRouter(prefix="/troupes", tags=["troupes"])


def staff_two_step(db: DbSession, user: User, troupe: Troupe) -> StaffTwoStepOut:
    staff = [
        troupe.lead_user_id,
        *db.scalars(select(TroupeStaff.user_id).where(TroupeStaff.troupe_id == troupe.id)),
    ]
    having = two_step.with_second_step(db, staff)
    return StaffTwoStepOut(
        required=troupe.staff_two_step,
        can_change=can_change(user, troupe),
        staff=[StaffMemberTwoStep(user_id=u, two_step=u in having) for u in staff],
    )


def can_change(user: User, troupe: Troupe) -> bool:
    return user.is_custodian or troupe.lead_user_id == user.id


@troupe_router.get("/{troupe_id}/staff-two-step")
def get_staff_two_step(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> StaffTwoStepOut:
    """Whether the troupe asks a second step of its staff, and who of them has one."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.VIEW_STAFF)
    return staff_two_step(db, user, troupe)


@troupe_router.put("/{troupe_id}/staff-two-step")
def set_staff_two_step(
    troupe_id: uuid.UUID, body: StaffTwoStepIn, db: DbSession, user: CurrentUser
) -> StaffTwoStepOut:
    """For the lead storyteller (or the custodian): ask a second step of the troupe's
    staff, or stop. Those without one are sent to set it up at their next request. The
    lead storyteller needs one of their own first."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.VIEW_STAFF)
    if not can_change(user, troupe):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the lead storyteller asks this of the staff."
        )
    if body.required and troupe.lead_user_id == user.id and not two_step.has_second_step(db, user):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set up two-step sign-in yourself first, in Account › Sign-in and email: this asks"
            " it of you too.",
        )
    if troupe.staff_two_step != body.required:
        troupe.staff_two_step = body.required
        record(
            db,
            user,
            "troupe.staff_two_step",
            troupe_id=troupe.id,
            setting="on" if body.required else "off",
        )
    db.commit()
    return staff_two_step(db, user, troupe)
