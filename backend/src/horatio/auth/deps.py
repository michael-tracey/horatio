"""FastAPI dependencies for the signed-in user."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from horatio.auth.sessions import user_for_token
from horatio.config import get_settings
from horatio.db import get_session
from horatio.models import User

DbSession = Annotated[Session, Depends(get_session)]


def optional_user(request: Request, db: DbSession) -> User | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    return user_for_token(db, token) if token else None


def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
# Whoever is signed in, or None: for the few pages anyone may see.
MaybeUser = Annotated[User | None, Depends(optional_user)]
