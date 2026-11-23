import uuid
from datetime import datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, Interval, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
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


class CustodianAccess(Record):
    """The custodian switching custodian access on, for one sign-in
    (horatio.auth.custodian_access): until then they have only their troupe roles'
    permissions. Kept once it ends, with the reason they gave."""

    __tablename__ = "custodian_accesses"

    custodian_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # The sign-in it was switched on from: it ends with it.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str] = mapped_column(Text)
    # When the custodian last used its powers: it ends `lasts` after that.
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # An hour, but for the test suites' shorter ones (horatio.custodian --switch-on).
    lasts: Mapped[timedelta] = mapped_column(Interval)
    # The troupes whose lead storyteller has been told it was used there, once each.
    told_troupe_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), default=list, server_default="{}"
    )
    # When it did end: switched off, signed out, or found timed out. Null while on.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
