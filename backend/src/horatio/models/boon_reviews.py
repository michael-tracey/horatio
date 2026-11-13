import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class BoonFlag(Record):
    """A flag raised on a boon for review (horatio.boon_reviews, #687): by Horatio, for
    a side named by a name that matches no character in the troupe ("unmatched"), or
    for a likely duplicate of another boon; or by hand, for a ruling. It stays raised
    until cleared, with a note, or until what it is about is put right."""

    __tablename__ = "boon_flags"
    __table_args__ = (
        CheckConstraint("kind in ('unmatched', 'duplicate', 'hand')", name="kind"),
        CheckConstraint("side is null or side in ('debtor', 'creditor')", name="side"),
        CheckConstraint("(kind = 'unmatched') = (side is not null)", name="sided"),
    )

    boon_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("boons.id", ondelete="CASCADE"), index=True
    )
    # unmatched | duplicate | hand
    kind: Mapped[str]
    # For an unmatched name: the side it names, debtor or creditor.
    side: Mapped[str | None]
    # What Horatio found: "Matches Bram: link it?", or "Like Agnes's minor boon of ...".
    detail: Mapped[str] = mapped_column(default="", server_default="")
    # The review note: why it was flagged by hand.
    note: Mapped[str] = mapped_column(default="", server_default="")
    # For a likely duplicate: the boon it looks like.
    other_boon_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("boons.id", ondelete="SET NULL")
    )
    # Who raised it by hand; none for Horatio's own.
    raised_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleared_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cleared_note: Mapped[str] = mapped_column(default="", server_default="")
