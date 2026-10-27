import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import handles, preferences
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.passwords import MIN_PASSWORD_LENGTH, hash_password, verify_password
from horatio.auth.resets import email_reset, limited, request_reset, use_reset, user_for_reset
from horatio.auth.sessions import end_session, start_session
from horatio.auth.viewing import allowed_while_viewing, viewing_for
from horatio.auth.viewing import end as end_viewing
from horatio.config import get_settings
from horatio.connectors import email
from horatio.db import get_sessionmaker
from horatio.models import User
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


class Forgot(BaseModel):
    email: EmailStr


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


def me(user: User) -> Me:
    return Me(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        handle=user.handle,
        next_handle_change=handles.next_change(user),
        is_custodian=user.is_custodian,
        preferences=preferences.read(user),
    )


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
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def user_by_login(db: DbSession, login: str) -> User | None:
    """The account an email or a handle (with or without its @) signs in to."""
    login = login.strip()
    if "@" in login.removeprefix("@"):
        return user_by_email(db, login)
    handle = login.removeprefix("@").lower()
    return db.scalar(select(User).where(func.lower(User.handle) == handle))


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def sign_up(body: SignUp, db: DbSession, response: Response) -> Me:
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
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user)


@router.post("/login")
def sign_in(body: SignIn, db: DbSession, response: Response) -> Me:
    user = user_by_login(db, body.login)
    ok, new_hash = verify_password(body.password, user.password_hash if user else None)
    if user is None or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email, handle or password.")
    if new_hash is not None:
        user.password_hash = new_hash
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@allowed_while_viewing
def sign_out(request: Request, db: DbSession, response: Response) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        viewing = viewing_for(request, db)
        if viewing is not None:
            end_viewing(db, viewing, "signed_out")
        end_session(db, token)
        db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me")
def who_am_i(user: CurrentUser) -> Me:
    return me(user)


def reset_user(db: DbSession, token: str) -> User:
    user = user_for_reset(db, token)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This reset link has expired or been used. Ask for a new one.",
        )
    return user


@router.get("/reset/{token}")
def reset_for(token: str, db: DbSession) -> ResetFor:
    """Whose password a reset link sets, so the page can say."""
    user = reset_user(db, token)
    return ResetFor(display_name=user.display_name, email=user.email)


@router.post("/reset")
def reset_password(body: NewPassword, db: DbSession, response: Response) -> Me:
    """Set a new password from a reset link. Ends every other session the person had,
    and signs them in here."""
    user = reset_user(db, body.token)
    user.password_hash = hash_password(body.password)
    use_reset(db, user)
    record(db, user, "account.password_reset", member=user.display_name, user_id=user.id)
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user)


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
def forgot_help() -> ForgotHelp:
    """Whether someone who forgot their password can ask Horatio for a link."""
    return ForgotHelp(can_email=email.configured())


@router.post("/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    body: Forgot, request: Request, db: DbSession, background: BackgroundTasks
) -> ForgotAnswer:
    """Email a reset link to an account's own address, if an account uses it. The
    answer is the same either way, so it never says who has an account; so is
    being turned away for asking too often."""
    if not email.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_EMAIL)
    ip = request.client.host if request.client else None
    wait = limited(db, body.email, ip)
    if wait is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, wait)
    asked = request_reset(db, body.email, ip)
    db.commit()
    if asked is not None:
        user, url = asked
        background.add_task(send_requested_reset, user.id, url)
    return ForgotAnswer(message=ON_ITS_WAY)
