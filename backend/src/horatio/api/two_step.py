"""Setting up two-step sign-in from Account › Sign-in: an authenticator app, passkeys
and recovery codes; the custodian resetting it for someone who has lost theirs; and a
troupe's lead storyteller asking it of the troupe's staff (#1057). How signing in with
it works is in horatio.auth.two_step, horatio.auth.passkeys and horatio.api.auth."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import closing
from horatio.api.players import player
from horatio.api.troupes import get_troupe
from horatio.audit import record, sign_in_ip
from horatio.auth import attempts, passkeys, two_step
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.passwords import verify_password
from horatio.auth.sessions import hash_token
from horatio.auth.two_step import allowed_first
from horatio.config import get_settings
from horatio.connectors import discord
from horatio.models import Passkey, Troupe, TroupeStaff, User
from horatio.models import Session as SignInSession
from horatio.notifications import notify
from horatio.permissions import (
    TroupeAction,
    acting_as_custodian,
    require_custodian,
    require_troupe_action,
)

router = APIRouter(prefix="/two-step", tags=["auth"])


class PasskeyOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
    # It can sign in alone, with no password (#1098): True if so; False if the device
    # said it can't; None if that isn't known, as for those made before it could.
    discoverable: bool | None


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
    # They have a password, which the changes above ask for again. An account made
    # with Discord (#1128) has none until they set one with a reset link.
    has_password: bool = True
    # With no password, they can confirm it's them with Discord instead (#1140): it is
    # linked, and set up on this server.
    can_confirm_with_discord: bool = False
    # Until when this sign-in is confirmed with Discord, standing in for the password
    # once; None if it isn't.
    confirmed_until: datetime | None = None


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


class Replacement(BaseModel):
    # The browser's PublicKeyCredential from navigator.credentials.create, as JSON.
    credential: dict[str, Any]


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


def passkey_out(p: Passkey) -> PasskeyOut:
    return PasskeyOut(
        id=p.id,
        name=p.name,
        created_at=p.created_at,
        last_used_at=p.last_used_at,
        discoverable=p.discoverable,
    )


def state(request: Request, db: DbSession, user: User) -> TwoStepOut:
    session = own_session(request, db, user)
    confirmed = session is not None and live(session.confirmed_until)
    return TwoStepOut(
        app=two_step.has_app(db, user),
        apps_available=two_step.apps_available(),
        passkeys=[passkey_out(p) for p in passkeys.mine(db, user)],
        passkeys_available=passkeys.available(),
        recovery_codes_left=two_step.recovery_codes_left(db, user),
        required_by=two_step.required_by(db, user),
        needed=two_step.needed(db, user),
        has_password=user.password_hash is not None,
        can_confirm_with_discord=can_confirm_with_discord(user),
        confirmed_until=session.confirmed_until if session is not None and confirmed else None,
    )


def can_confirm_with_discord(user: User) -> bool:
    """Whether they confirm it's them with Discord, having no password (#1140)."""
    return user.password_hash is None and user.discord_user_id is not None and discord.configured()


def live(until: datetime | None) -> bool:
    return until is not None and until > datetime.now(UTC)


# Told to someone held back from giving their password here: the limit is the one on
# changing it, at the account (#1095), so a sign-in left open can't guess it either way.
PASSWORD_WAIT = "Too many tries at your password. Try again later."


NO_PASSWORD = (
    "This asks for your password, and you have none yet. Set one with Forgot your password?"
    " on the sign-in page, then try again."
)
CONFIRM_FIRST = (
    "This asks you to confirm it's you, and you have no password: confirm with Discord,"
    " then try again."
)


def check_password(request: Request, db: DbSession, user: User, password: str) -> None:
    """Adding, replacing or removing a passkey, setting up or turning off the app, or
    making new recovery codes asks for the password again, so a sign-in left open
    somewhere can't (#1110, #1148). Each try, right or wrong, counts towards the limit
    on password tries at the account, as changing the password does, checked before
    the password is.

    An account with no password (one made with Discord, #1128) confirms it's them with
    Discord instead (#1140, horatio.api.discord_confirm): this sign-in's confirmation
    from the last few minutes stands in for the password, and is used up once whatever
    asked is done (`used_up`). That try was counted when they confirmed. Without
    Discord linked, they are told how to set a password."""
    if user.password_hash is None:
        if not live(this_session(request, db, user).confirmed_until):
            detail = CONFIRM_FIRST if can_confirm_with_discord(user) else NO_PASSWORD
            raise HTTPException(status.HTTP_409_CONFLICT, detail)
        return
    if (held := attempts.password_change_held_back(db, user.id)) is not None:
        record(
            db,
            user,
            "account.password_change_throttled"
            if held.first
            else "account.password_change_throttled_again",
            kind="two_step",
            limit=held.limit.key,
            member=user.display_name,
            user_id=user.id,
            **sign_in_ip(request),
        )
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, PASSWORD_WAIT)
    ok, _ = verify_password(password, user.password_hash)
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That's not your password.")


def used_up(request: Request, db: DbSession, user: User) -> None:
    """What a confirmation with Discord stood in for is done: it is used (#1140). Not
    before, so a change refused, or a passkey's prompt cancelled, leaves it to try again."""
    session = own_session(request, db, user)
    if session is not None:
        session.confirmed_until = None


@router.get("")
@allowed_first
def two_step_state(request: Request, db: DbSession, user: CurrentUser) -> TwoStepOut:
    """The signed-in person's second steps, and whether they must have one."""
    return state(request, db, user)


@router.post("/app")
@allowed_first
def start_app(body: Password, request: Request, db: DbSession, user: CurrentUser) -> AppSetup:
    """Start setting up an authenticator app, giving their password first (#1148): the
    secret to scan or type into it, so a wrong password never shows one. It signs no
    one in until a code from it is given (POST /two-step/app/confirm)."""
    two_step.can_start_app(db, user)
    check_password(request, db, user, body.password)
    secret = two_step.start_app(db, user)
    db.commit()
    return AppSetup(secret=secret, uri=two_step.otpauth_uri(user, secret))


@router.post("/app/confirm")
@allowed_first
def confirm_app(body: Code, request: Request, db: DbSession, user: CurrentUser) -> RecoveryCodes:
    """Turn on the authenticator app being set up with a code from it. With it come
    ten recovery codes, if they have none left. The password was given for its
    secret, at POST /two-step/app."""
    if not two_step.check_app(db, user, body.code, setting_up=True):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That code isn't right. Check that your phone's clock is right, and give the"
            " newest code.",
        )
    used_up(request, db, user)
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


def own_session(request: Request, db: DbSession, user: User) -> SignInSession | None:
    """The sign-in session this request comes with, if it is `user`'s own."""
    token = request.cookies.get(get_settings().session_cookie_name, "")
    return db.scalar(
        select(SignInSession).where(
            SignInSession.token_hash == hash_token(token), SignInSession.user_id == user.id
        )
    )


def this_session(request: Request, db: DbSession, user: User) -> SignInSession:
    """The sign-in session this request comes with: a passkey being added keeps its
    challenge there, and a confirmation with Discord its time (#1140)."""
    session = own_session(request, db, user)
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first.")
    return session


@router.post("/passkeys/options")
@allowed_first
def passkey_options(
    body: Password, request: Request, db: DbSession, user: CurrentUser
) -> dict[str, Any]:
    """What the browser needs to make a passkey for Horatio: WebAuthn's
    PublicKeyCredentialCreationOptions, as JSON, giving their password first. Its
    challenge works once, so the passkey it makes is kept only after the password."""
    if not passkeys.available():
        raise HTTPException(status.HTTP_409_CONFLICT, "Passkeys need this site on https.")
    check_password(request, db, user, body.password)
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
    session = this_session(request, db, user)
    passkey = passkeys.add(db, session, user, body.credential, body.name)
    used_up(request, db, user)
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
def remove_passkey(
    passkey_id: uuid.UUID, body: Password, request: Request, db: DbSession, user: CurrentUser
) -> None:
    """Remove one of their passkeys, giving their password."""
    check_password(request, db, user, body.password)
    passkey = db.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such passkey.")
    keep_one(db, user)
    name = passkey.name
    db.delete(passkey)
    db.flush()
    forget_if_none_left(db, user)
    used_up(request, db, user)
    record(
        db, user, "account.two_step_removed", kind="passkey", member=user.display_name, name=name
    )
    db.commit()


def replaceable(db: DbSession, user: User, passkey_id: uuid.UUID) -> Passkey:
    """One of their passkeys that may not sign in alone, to replace with one that does."""
    passkey = db.scalar(select(Passkey).where(Passkey.id == passkey_id).with_for_update())
    if passkey is None or passkey.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such passkey.")
    if passkey.discoverable:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{passkey.name} signs you in alone already.")
    return passkey


@router.post("/passkeys/{passkey_id}/replace/options")
def replace_options(
    passkey_id: uuid.UUID, body: Password, request: Request, db: DbSession, user: CurrentUser
) -> dict[str, Any]:
    """What the browser needs to make a passkey in place of one that may not sign in
    alone (#1110), giving their password first: as for adding one, but the device must
    make it so it can."""
    if not passkeys.available():
        raise HTTPException(status.HTTP_409_CONFLICT, "Passkeys need this site on https.")
    replaceable(db, user, passkey_id)
    check_password(request, db, user, body.password)
    options = passkeys.adding_options(db, this_session(request, db, user), user, alone=True)
    db.commit()
    return options


@router.post("/passkeys/{passkey_id}/replace")
def replace_passkey(
    passkey_id: uuid.UUID, body: Replacement, request: Request, db: DbSession, user: CurrentUser
) -> PasskeyOut:
    """Replace one of their passkeys that may not sign in alone with the one the browser
    made, which does (#1110), under the same name. The new one is kept and the old one
    removed together, only once the new one checks out, so a cancelled or failed try
    leaves the old one as it was, and someone who must have two-step sign-in is never
    left without a second step. The password was given for its challenge, at
    POST .../replace/options."""
    old = replaceable(db, user, passkey_id)
    session = this_session(request, db, user)
    new = passkeys.add(db, session, user, body.credential, old.name, alone=True)
    used_up(request, db, user)
    db.delete(old)
    db.flush()
    record(
        db,
        user,
        "account.two_step_replaced",
        kind="passkey",
        member=user.display_name,
        name=new.name,
    )
    db.commit()
    return passkey_out(new)


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
def remove_app(body: Password, request: Request, db: DbSession, user: CurrentUser) -> None:
    """Turn off their authenticator app, giving their password."""
    check_password(request, db, user, body.password)
    if not two_step.has_app(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have no authenticator app set up.")
    keep_one(db, user)
    two_step.remove_app(db, user)
    forget_if_none_left(db, user)
    used_up(request, db, user)
    record(db, user, "account.two_step_removed", kind="app", member=user.display_name)
    db.commit()


@router.post("/recovery-codes")
def new_recovery_codes(
    body: Password, request: Request, db: DbSession, user: CurrentUser
) -> RecoveryCodes:
    """Ten new recovery codes in place of the ones they had, giving their password."""
    check_password(request, db, user, body.password)
    if not two_step.has_second_step(db, user):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Set up a second step first: recovery codes stand in for it."
        )
    codes = two_step.new_recovery_codes(db, user)
    used_up(request, db, user)
    record(db, user, "account.recovery_codes_made", member=user.display_name)
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/reset/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset(user_id: uuid.UUID, body: ResetIn, db: DbSession, user: CurrentUser) -> None:
    """For the custodian: take away every second step someone has, and their recovery
    codes, when they have lost them, so their password alone signs them in again until
    they set up another. Recorded as a notice, and they are told in the bell and by
    email; the email goes before the answer, as the custodian's other emails do."""
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
        two_step.ACCOUNT_PAGE,
    )
    two_step.email_reset(db, person, datetime.now(UTC), user, body.reason)
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
    return troupe.lead_user_id == user.id or acting_as_custodian(user, troupe)


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
        if body.required and troupe.archived_at is None:
            tell_staff(db, user, troupe)
    db.commit()
    return staff_two_step(db, user, troupe)


def tell_staff(db: DbSession, user: User, troupe: Troupe) -> None:
    """Tell the troupe's staff in the bell, as it's turned on, that it asks a second
    step of them now: those without one, that they must set it up before going on.
    Not whoever turned it on."""
    staff = [s for s in closing.staff_ids(db, troupe) if s != user.id]
    having = two_step.with_second_step(db, staff)
    asked = f"{user.display_name} asked the troupe's staff to sign in with two steps."
    notify(
        db,
        [s for s in staff if s not in having],
        "troupe.staff_two_step",
        f"{asked} Set it up in Account › Sign-in and email: Horatio sends you there first.",
        two_step.ACCOUNT_PAGE,
        troupe_id=troupe.id,
    )
    notify(
        db,
        [s for s in staff if s in having],
        "troupe.staff_two_step",
        f"{asked} You have it set up already, so nothing changes for you.",
        two_step.ACCOUNT_PAGE,
        troupe_id=troupe.id,
    )
