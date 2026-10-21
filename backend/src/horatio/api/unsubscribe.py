"""Turning off a kind of notification email from the link in one, without
signing in (horatio.notification_emails)."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import notification_emails
from horatio.auth.deps import DbSession
from horatio.models import User

router = APIRouter(prefix="/unsubscribe", tags=["unsubscribe"])

NOT_A_LINK = (
    "This unsubscribe link doesn't work. Sign in and choose which notifications "
    "come by email in Account → Settings."
)


class Unsubscribe(BaseModel):
    display_name: str
    email: str
    # What the emails the link stops are about: "downtime results", or "any
    # notification" for a digest's link, which stops them all.
    about: str
    # Whether any of them still come by email.
    subscribed: bool


def unsubscribing(db: DbSession, token: str) -> tuple[User, str]:
    found = notification_emails.unsubscribing(db, token)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_A_LINK)
    return found


def out(user: User, topic: str) -> Unsubscribe:
    return Unsubscribe(
        display_name=user.display_name,
        email=user.email,
        about=notification_emails.about(topic),
        subscribed=notification_emails.subscribed(user, topic),
    )


@router.get("/{token}")
def unsubscribe_for(token: str, db: DbSession) -> Unsubscribe:
    """What an unsubscribe link stops, so the page can ask first."""
    return out(*unsubscribing(db, token))


@router.post("/{token}")
def unsubscribe(token: str, db: DbSession) -> Unsubscribe:
    """Stop the emails the link is about. The bell still shows them."""
    user, topic = unsubscribing(db, token)
    notification_emails.unsubscribe(user, topic)
    db.commit()
    return out(user, topic)
