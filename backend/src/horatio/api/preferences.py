"""The signed-in person's own settings (horatio.preferences)."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from horatio import preferences
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import email
from horatio.preferences import Preferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


class EmailHelp(BaseModel):
    # Whether this server can send email, so notifications can come by email too.
    available: bool


@router.get("")
def read_preferences(user: CurrentUser) -> Preferences:
    return preferences.read(user)


@router.patch("")
def change_preferences(changes: dict[str, Any], db: DbSession, user: CurrentUser) -> Preferences:
    """Change some settings; the rest stay as they are."""
    kept = preferences.change(user, changes)
    db.commit()
    return kept


@router.get("/email")
def email_help(user: CurrentUser) -> EmailHelp:
    """Whether notifications can come by email here (horatio.notification_emails)."""
    return EmailHelp(available=email.configured())
