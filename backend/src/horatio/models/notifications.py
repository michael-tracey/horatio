import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
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
