import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Viewing(Record):
    """The custodian viewing Horatio as someone, read-only, for support
    (horatio.auth.viewing). Kept once it ends, so the person can see when it
    happened and why."""

    __tablename__ = "viewings"

    custodian_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Whom the custodian sees Horatio as.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # The custodian's sign-in it belongs to: it ends with it. Null if that is deleted.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str] = mapped_column(Text)
    # When it ends by itself, 30 minutes after it starts.
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When it did end: stopped, signed out, or found timed out. Null while it may be live.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
