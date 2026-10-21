import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Notification(Record):
    """A message for one person about something that happened, such as their
    downtime results arriving. Kept until read and afterwards. Work waiting on
    someone (an approval to decide) is not stored here: it is worked out from
    what is waiting, so it can never go stale (see horatio/notifications.py)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # What kind of event, e.g. downtime.delivered; lets the app group or filter them.
    kind: Mapped[str]
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    # One line, written when the event happens, so it reads the same later.
    summary: Mapped[str]
    # Where in the app to go about it.
    link: Mapped[str]
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailNotice(Record):
    """A notification waiting to go out by email as well, to someone who asked for
    that kind by email (horatio.notification_emails). Gone once sent, or once
    they no longer want it."""

    __tablename__ = "email_notices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Which of the person's email settings it comes under, e.g. "downtime".
    topic: Mapped[str]
    # The troupe's name, the line and the link, as the bell shows them.
    troupe: Mapped[str | None]
    summary: Mapped[str]
    link: Mapped[str]
    # When it may go: at once, at the person's daily digest, or after a failure,
    # once the wait is over.
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    last_error: Mapped[str | None]
