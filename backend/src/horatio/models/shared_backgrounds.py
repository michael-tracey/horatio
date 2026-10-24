import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class SharedBackground(Record):
    """A background a troupe's characters pool together (CONTEXT.md: Shared
    Background). Kept by horatio.shared_backgrounds, which records each change in
    the audit log."""

    __tablename__ = "shared_backgrounds"
    __table_args__ = (UniqueConstraint("troupe_id", "name", name="uq_shared_backgrounds_name"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    # What the sharers call it, such as "The coterie's Haven".
    name: Mapped[str]
    # The background's name in the troupe's rules, such as "Haven".
    background: Mapped[str]
    # What the sharers chose it gives them, such as a haven's advantages.
    notes: Mapped[str] = mapped_column(default="", server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class SharedBackgroundEntry(Record):
    """One line in a shared background's log: dots a character put in or took out,
    or a use of it (CONTEXT.md: Shared Background Entry)."""

    __tablename__ = "shared_background_entries"
    __table_args__ = (
        CheckConstraint("kind in ('contribution', 'withdrawal', 'use')", name="kind"),
        # Dots go in and come out; a use has none.
        CheckConstraint("(kind = 'use') = (dots is null)", name="dots_by_kind"),
        CheckConstraint("dots is null or dots >= 1", name="dots"),
    )

    background_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shared_backgrounds.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str]
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Null for a character since deleted; `name` keeps its name as it was logged.
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str]
    dots: Mapped[int | None]
    # A use's "what for".
    purpose: Mapped[str] = mapped_column(default="", server_default="")
    note: Mapped[str] = mapped_column(default="", server_default="")
    logged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
