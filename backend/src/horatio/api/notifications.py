"""The bell in the menu bar: tasks and messages for the signed-in person."""

import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel

from horatio import notifications
from horatio.auth.deps import CurrentUser, DbSession

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    kind: str
    # Work waiting on you: it goes when done, and cannot be marked read.
    task: bool
    troupe_id: uuid.UUID | None
    troupe_name: str | None
    summary: str
    link: str
    at: datetime
    read: bool


class NotificationsOut(BaseModel):
    items: list[NotificationOut]
    # Tasks plus unread messages: the number on the bell.
    count: int


class ReadIds(BaseModel):
    # Message ids; leave out to mark every message read.
    ids: list[uuid.UUID] | None = None


@router.get("")
def list_notifications(db: DbSession, user: CurrentUser) -> NotificationsOut:
    items = notifications.for_user(db, user)
    return NotificationsOut(
        items=[NotificationOut(**vars(i)) for i in items],
        count=sum(1 for i in items if i.task or not i.read),
    )


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(body: ReadIds, db: DbSession, user: CurrentUser) -> None:
    notifications.mark_read(db, user, body.ids)
    db.commit()
