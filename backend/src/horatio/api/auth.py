import uuid

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.passwords import MIN_PASSWORD_LENGTH, hash_password, verify_password
from horatio.auth.resets import use_reset, user_for_reset
from horatio.auth.sessions import end_session, start_session
from horatio.config import get_settings
from horatio.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class SignUp(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    display_name: str = Field(min_length=1, max_length=100)


class SignIn(BaseModel):
    email: EmailStr
    password: str


class NewPassword(BaseModel):
    token: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class ResetFor(BaseModel):
    display_name: str
    email: str


class Me(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_custodian: bool


def me(user: User) -> Me:
    return Me(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_custodian=user.is_custodian,
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


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def sign_up(body: SignUp, db: DbSession, response: Response) -> Me:
    if user_by_email(db, body.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    user = User(
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user)


@router.post("/login")
def sign_in(body: SignIn, db: DbSession, response: Response) -> Me:
    user = user_by_email(db, body.email)
    ok, new_hash = verify_password(body.password, user.password_hash if user else None)
    if user is None or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password.")
    if new_hash is not None:
        user.password_hash = new_hash
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(request: Request, db: DbSession, response: Response) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
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
            "This reset link has expired or been used. Ask the custodian for a new one.",
        )
    return user


@router.get("/reset/{token}")
def reset_for(token: str, db: DbSession) -> ResetFor:
    """Whose password a reset link sets, so the page can say."""
    user = reset_user(db, token)
    return ResetFor(display_name=user.display_name, email=user.email)


@router.post("/reset")
def reset_password(body: NewPassword, db: DbSession, response: Response) -> Me:
    """Set a new password from the custodian's link. Ends every other session the
    person had, and signs them in here."""
    user = reset_user(db, body.token)
    user.password_hash = hash_password(body.password)
    use_reset(db, user)
    record(db, user, "account.password_reset")
    set_session_cookie(response, start_session(db, user))
    db.commit()
    return me(user)
