"""The signed-in person's own settings (horatio.preferences)."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import notification_emails, preferences, web_push
from horatio.api.throw_images import may_choose
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
    # Only the whole set of a troupe the person plays in (#671).
    chosen = kept.throw_images if "throw_images" in changes else None
    if chosen is not None and not may_choose(db, user, chosen):
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "You can choose only the throw pictures of a troupe you play in.",
        )
    # What waits for a digest or for the end of quiet hours goes as they now say (#1196).
    if notification_emails.DIGEST_SETTINGS & changes.keys():
        notification_emails.retime(db, user)
    if web_push.QUIET_SETTINGS & changes.keys():
        web_push.retime(db, user)
    db.commit()
    return kept


@router.get("/email")
def email_help(user: CurrentUser) -> EmailHelp:
    """Whether notifications can come by email here (horatio.notification_emails)."""
    return EmailHelp(available=email.configured())
