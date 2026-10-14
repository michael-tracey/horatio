import uuid

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.passwords import MIN_PASSWORD_LENGTH, hash_password, verify_password
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
