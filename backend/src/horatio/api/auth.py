import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import handles, notifications, preferences, suspensions
from horatio.audit import client_ip, record, sign_in_ip
from horatio.auth import attempts, passkeys, two_step
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.passwords import MIN_PASSWORD_LENGTH, hash_password, verify_password
from horatio.auth.resets import (
    cancel_reset,
    email_reset,
    limited,
    request_reset,
    use_reset,
    user_for_reset,
)
from horatio.auth.sessions import end_other_sessions, end_session, start_session, user_for_token
from horatio.auth.two_step import allowed_first
from horatio.auth.viewing import allowed_while_viewing, viewing_for
from horatio.auth.viewing import end as end_viewing
from horatio.config import get_settings
from horatio.connectors import email
from horatio.db import get_sessionmaker
from horatio.models import SecondStepSignIn, User
from horatio.preferences import Preferences

router = APIRouter(prefix="/auth", tags=["auth"])


class SignUp(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    display_name: str = Field(min_length=1, max_length=100)
    # How others will find them (horatio.handles); made from their name if not given.
    handle: str | None = None


class SignIn(BaseModel):
    # Their email or their handle.
    login: str = Field(min_length=1)
    password: str


class NewPassword(BaseModel):
    token: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class PasswordChange(BaseModel):
    current: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class Forgot(BaseModel):
    email: EmailStr
    # Where they were going, to go on to after setting a new password: a path on this site.
    next: str | None = None


class ForgotHelp(BaseModel):
    # Whether Horatio can email reset links; without email, the custodian makes them.
    can_email: bool


class ForgotAnswer(BaseModel):
    message: str


class ResetFor(BaseModel):
    display_name: str
    email: str


class Me(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    handle: str
    # When they can next change their handle; None if they can now.
    next_handle_change: datetime | None
    is_custodian: bool
    # Their settings, so the app has them from the start (horatio.preferences).
    preferences: Preferences
    # They must set up two-step sign-in before anything else (horatio.auth.two_step):
    # the app sends them to do it. Never while the custodian views as them.
    two_step_needed: bool = False


class SecondStep(BaseModel):
    """The password was right, and the account has a second step: no session until
    it is given (POST /auth/second-step)."""

    # The ways they can give it: "app", "passkey", "recovery_code".
    second_step: list[str]


class PasskeySigned(BaseModel):
    # The browser's PublicKeyCredential, as JSON (WebAuthn's toJSON()).
    credential: dict[str, Any]


class SecondStepCode(BaseModel):
    # Six digits from their authenticator app, or a recovery code.
    code: str = Field(min_length=1, max_length=64)


def me(user: User, db: Session | None = None) -> Me:
    """Who they are, for the app. With `db`, whether they must set up a second step."""
    return Me(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        handle=user.handle,
        next_handle_change=handles.next_change(user),
        is_custodian=user.is_custodian,
        preferences=preferences.read(user),
        two_step_needed=db is not None and two_step.needed(db, user),
    )


def set_second_step_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        two_step.COOKIE,
        token,
        max_age=int(two_step.SIGN_IN_FOR.total_seconds()),
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/api/auth",
    )


def clear_second_step_cookie(response: Response) -> None:
    response.delete_cookie(two_step.COOKIE, path="/api/auth")


def ask_second_step(
    db: DbSession, user: User, response: Response, login_hash: str | None, request: Request
) -> SecondStep:
    """Their password was right (or newly set): wait on their second step, with no
    session. Refused at once while they are suspended, as a session would be."""
    suspensions.refuse(db, user)
    set_second_step_cookie(response, two_step.begin(db, user, login_hash))
    record(
        db,
        user,
        "account.second_step_asked",
        member=user.display_name,
        user_id=user.id,
        **sign_in_ip(db, request),
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return SecondStep(second_step=two_step.methods(db, user))


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        # Without a path the cookie would only be sent back to /api/auth.
        path="/",
    )


def user_by_email(db: DbSession, email: str) -> User | None:
    """The account using an email. A merged account's email is free for use."""
    return db.scalar(
        select(User).where(func.lower(User.email) == email.lower(), User.merged_into_id.is_(None))
    )


def user_by_login(db: DbSession, login: str) -> User | None:
    """The account an email or a handle (with or without its @) signs in to."""
    login = login.strip()
    if "@" in login.removeprefix("@"):
        return user_by_email(db, login)
    handle = login.removeprefix("@").lower()
    return db.scalar(
        select(User).where(func.lower(User.handle) == handle, User.merged_into_id.is_(None))
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
@allowed_first
def sign_up(body: SignUp, request: Request, db: DbSession, response: Response) -> Me:
    if (held := attempts.sign_up_held_back(db, attempts.source(request))) is not None:
        # The first a limit turns away in its window is info; the rest are debug (#1074).
        record(
            db,
            None,
            "account.sign_up_throttled" if held.first else "account.sign_up_throttled_again",
            limit=held.limit.key,
            **sign_in_ip(db, request),
        )
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, held.wait)
    if user_by_email(db, body.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    user = User(
        email=body.email,
        display_name=body.display_name,
        handle=(
            handles.choose(db, body.handle)
            if body.handle and body.handle.strip()
            else handles.suggest(db, body.display_name)
        ),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    notifications.signed_up(db, user)
    record(
        db,
        user,
        "account.signed_up",
        member=user.display_name,
        user_id=user.id,
        **sign_in_ip(db, request),
    )
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user)


@router.post("/login", responses={202: {"model": SecondStep}})
@allowed_first
def sign_in(body: SignIn, request: Request, db: DbSession, response: Response) -> Me | SecondStep:
    """Sign in with a password. For an account with a second step, that starts a
    sign-in waiting on it (202), and only the second step signs them in."""
    ip = attempts.source(request)
    held = attempts.sign_in_held_back(db, body.login, ip)
    user = user_by_login(db, body.login)
    from_ip = sign_in_ip(db, request)
    if held is not None:
        # Turned away before the password is checked, whether an account uses the
        # login or not. Never what was typed, as for a failed sign-in. The first a
        # limit turns away in its window is info; the rest are debug (#1074).
        whose: dict[str, Any] = (
            {"kind": "unknown"}
            if user is None
            else {"member": user.display_name, "user_id": user.id}
        )
        record(
            db,
            user,
            "account.sign_in_throttled" if held.first else "account.sign_in_throttled_again",
            limit=held.limit.key,
            **whose,
            **from_ip,
        )
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, held.wait)
    ok, new_hash = verify_password(body.password, user.password_hash if user else None)
    if user is None or not ok:
        # Never what was typed: someone may have typed their password as their login.
        if user is None:
            record(db, None, "account.sign_in_failed", kind="unknown", **from_ip)
        else:
            record(
                db,
                user,
                "account.sign_in_failed",
                member=user.display_name,
                user_id=user.id,
                **from_ip,
            )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email, handle or password.")
    if new_hash is not None:
        user.password_hash = new_hash
    if two_step.has_second_step(db, user):
        # Its tries still count as failed until the second step signs them in.
        asked = ask_second_step(db, user, response, attempts.login_key(body.login), request)
        db.commit()
        return asked
    attempts.signed_in(db, body.login, ip)
    record(db, user, "account.signed_in", member=user.display_name, user_id=user.id, **from_ip)
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user, db)


AGAIN = "Your sign-in has timed out. Sign in again."


@router.get("/second-step")
@allowed_first
def second_step_waiting(request: Request, db: DbSession) -> SecondStep:
    """The second steps a sign-in waiting on one can be given with; 410 if there's
    none waiting here, or it has timed out."""
    waiting = two_step.waiting(db, request.cookies.get(two_step.COOKIE))
    if waiting is None:
        raise HTTPException(status.HTTP_410_GONE, AGAIN)
    return SecondStep(second_step=two_step.methods(db, db.get_one(User, waiting.user_id)))


@router.post("/second-step")
@allowed_first
def second_step(body: SecondStepCode, request: Request, db: DbSession, response: Response) -> Me:
    """Give the second step of a sign-in waiting on one: a code from their
    authenticator app, or a recovery code. Wrong codes count against limits of their
    own (horatio.auth.attempts); five wrong end the sign-in, to start again."""
    if two_step.is_app_code(body.code):
        return give_second_step(
            request,
            db,
            response,
            "app",
            lambda user, _: two_step.check_app(db, user, body.code),
            "That code isn't right.",
        )
    return give_second_step(
        request,
        db,
        response,
        "recovery_code",
        lambda user, _: two_step.use_recovery_code(db, user, body.code),
        "That recovery code isn't right, or has been used.",
    )


@router.post("/second-step/passkey/options")
@allowed_first
def passkey_options(request: Request, db: DbSession) -> dict[str, Any]:
    """What the browser needs to sign the waiting sign-in with a passkey: WebAuthn's
    PublicKeyCredentialRequestOptions, as JSON. Its challenge works once."""
    waiting = two_step.waiting(db, request.cookies.get(two_step.COOKIE))
    if waiting is None:
        raise HTTPException(status.HTTP_410_GONE, AGAIN)
    user = db.get_one(User, waiting.user_id)
    if not two_step.passkey_count(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "You have no passkey set up.")
    options = passkeys.sign_in_options(db, waiting, user)
    db.commit()
    return options


@router.post("/second-step/passkey")
@allowed_first
def second_step_passkey(
    body: PasskeySigned, request: Request, db: DbSession, response: Response
) -> Me:
    """Give the second step of a sign-in waiting on one with a passkey: the browser's
    answer to the challenge from /second-step/passkey/options. Counted against the
    same limits as codes."""
    return give_second_step(
        request,
        db,
        response,
        "passkey",
        lambda user, waiting: passkeys.check(db, waiting, user, body.credential),
        "That passkey didn't sign you in. Try again, or use another way.",
    )


def give_second_step(
    request: Request,
    db: DbSession,
    response: Response,
    method: str,
    right: Callable[[User, SecondStepSignIn], bool],
    wrong_message: str,
) -> Me:
    """Check a second step for the sign-in waiting here, with `right`: limited, logged,
    and counted against the sign-in, which ends after five wrong."""
    waiting = two_step.waiting(db, request.cookies.get(two_step.COOKIE))
    if waiting is None:
        clear_second_step_cookie(response)
        raise HTTPException(status.HTTP_410_GONE, AGAIN)
    user = db.get_one(User, waiting.user_id)
    ip = attempts.source(request)
    from_ip = sign_in_ip(db, request)
    whose = {"member": user.display_name, "user_id": user.id}
    if (held := attempts.second_step_held_back(db, user.id, ip)) is not None:
        record(
            db,
            user,
            "account.second_step_throttled"
            if held.first
            else "account.second_step_throttled_again",
            limit=held.limit.key,
            **whose,
            **from_ip,
        )
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, held.wait)
    # Counted and committed, which let go of the row's lock: take it again.
    waiting = two_step.waiting(db, request.cookies.get(two_step.COOKIE))
    if waiting is None:
        raise HTTPException(status.HTTP_410_GONE, AGAIN)
    if not right(user, waiting):
        ended = two_step.wrong(db, waiting)
        record(db, user, "account.second_step_failed", kind=method, **whose, **from_ip)
        db.commit()
        if ended:
            raise HTTPException(status.HTTP_410_GONE, "Too many wrong tries. Sign in again.")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, wrong_message)
    return signed_in_by_second_step(db, user, waiting, method, request, response)


def signed_in_by_second_step(
    db: DbSession,
    user: User,
    waiting: SecondStepSignIn,
    method: str,
    request: Request,
    response: Response,
) -> Me:
    """The second step was right: sign them in, here only."""
    ip = attempts.source(request)
    from_ip = sign_in_ip(db, request)
    attempts.second_step_passed(db, user.id, ip)
    if waiting.login_hash is not None:
        attempts.signed_in_at(db, waiting.login_hash, ip)
    db.delete(waiting)
    if method == "recovery_code":
        record(
            db,
            user,
            "account.recovery_code_used",
            member=user.display_name,
            user_id=user.id,
            left=two_step.recovery_codes_left(db, user),
            **from_ip,
        )
    record(
        db,
        user,
        "account.signed_in",
        kind=method,
        member=user.display_name,
        user_id=user.id,
        **from_ip,
    )
    set_session_cookie(response, start_session(db, user))
    clear_second_step_cookie(response)
    db.commit()
    return me(user, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@allowed_while_viewing
@allowed_first
def sign_out(request: Request, db: DbSession, response: Response) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        viewing = viewing_for(request, db)
        if viewing is not None:
            end_viewing(db, viewing, "signed_out")
        if (user := user_for_token(db, token)) is not None:
            record(
                db,
                user,
                "account.signed_out",
                member=user.display_name,
                user_id=user.id,
                **sign_in_ip(db, request),
            )
        end_session(db, token)
        db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me")
@allowed_first
def who_am_i(request: Request, db: DbSession, user: CurrentUser) -> Me:
    # While the custodian views as someone, never sent to set up anything.
    return me(user, None if viewing_for(request, db) is not None else db)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
@allowed_first
def change_password(
    body: PasswordChange, request: Request, db: DbSession, user: CurrentUser
) -> None:
    """Change your own password, giving the one you have now. Signs you out
    everywhere else, and cancels any reset link you had, but not here. Limited at the
    account, every try counted, right or not (#1095)."""
    whose = {"member": user.display_name, "user_id": user.id}
    if (held := attempts.password_change_held_back(db, user.id)) is not None:
        # Turned away before the password is checked. The first a limit turns away in
        # its window is info; the rest are debug.
        record(
            db,
            user,
            "account.password_change_throttled"
            if held.first
            else "account.password_change_throttled_again",
            limit=held.limit.key,
            **whose,
            **sign_in_ip(db, request),
        )
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, held.wait)
    ok, _ = verify_password(body.current, user.password_hash)
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That's not your current password.")
    if body.password == body.current:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That's your password now. Choose a new one."
        )
    user.password_hash = hash_password(body.password)
    end_other_sessions(db, user, request.cookies.get(get_settings().session_cookie_name))
    cancel_reset(db, user)
    record(db, user, "account.password_changed", **whose)
    db.commit()


def reset_user(db: DbSession, token: str) -> User:
    user = user_for_reset(db, token)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This reset link has expired or been used. Ask for a new one.",
        )
    suspensions.refuse(db, user)
    return user


@router.get("/reset/{token}")
@allowed_first
def reset_for(token: str, db: DbSession) -> ResetFor:
    """Whose password a reset link sets, so the page can say."""
    user = reset_user(db, token)
    return ResetFor(display_name=user.display_name, email=user.email)


@router.post("/reset", responses={202: {"model": SecondStep}})
@allowed_first
def reset_password(
    body: NewPassword, request: Request, db: DbSession, response: Response
) -> Me | SecondStep:
    """Set a new password from a reset link. Ends every other session the person had,
    and signs them in here; or, if they have a second step, asks for it (202) as
    signing in does. A reset link never stands in for a second step."""
    user = reset_user(db, body.token)
    user.password_hash = hash_password(body.password)
    use_reset(db, user)
    record(db, user, "account.password_reset", member=user.display_name, user_id=user.id)
    if two_step.has_second_step(db, user):
        asked = ask_second_step(db, user, response, None, request)
        db.commit()
        return asked
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user, db)


NO_EMAIL = "Horatio can't send email here, so ask the custodian to make you a reset link."
ON_ITS_WAY = (
    "If an account uses that address, a reset link is on its way. "
    "It works once, for the next 24 hours."
)


def background_session() -> Session:
    """A session of its own, for work done after the response (tests swap it)."""
    return get_sessionmaker()()


def send_requested_reset(user_id: uuid.UUID, url: str) -> None:
    """Email a link someone asked for. Done after answering them, so how long the
    mail server takes never shows whether an account uses the address."""
    with background_session() as db:
        email_reset(db, db.get_one(User, user_id), url, by=None)
        db.commit()


@router.get("/forgot")
@allowed_first
def forgot_help() -> ForgotHelp:
    """Whether someone who forgot their password can ask Horatio for a link."""
    return ForgotHelp(can_email=email.configured())


@router.post("/forgot", status_code=status.HTTP_202_ACCEPTED)
@allowed_first
def forgot_password(
    body: Forgot, request: Request, db: DbSession, background: BackgroundTasks
) -> ForgotAnswer:
    """Email a reset link to an account's own address, if an account uses it. The
    answer is the same either way, so it never says who has an account; so is
    being turned away for asking too often."""
    if not email.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_EMAIL)
    ip = client_ip(request)
    wait = limited(db, body.email, ip)
    if wait is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, wait)
    asked = request_reset(db, body.email, ip, body.next)
    db.commit()
    if asked is not None:
        user, url = asked
        background.add_task(send_requested_reset, user.id, url)
    return ForgotAnswer(message=ON_ITS_WAY)
