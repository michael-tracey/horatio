import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Approval(Record):
    """A change a player has asked for, waiting on (or decided by) a troupe's
    storytellers or assistant storytellers. One queue for every kind."""

    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("kind in ('sheet_change', 'home_troupe_change')", name="kind"),
        CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'withdrawn')", name="status"
        ),
        # A character has at most one request of each kind waiting at a time.
        Index(
            "uq_approvals_one_pending",
            "character_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    # The troupe whose staff decide.
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending", server_default="pending")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    player_note: Mapped[str] = mapped_column(default="", server_default="")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staff_note: Mapped[str] = mapped_column(default="", server_default="")
