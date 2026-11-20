import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class AuditEvent(Record):
    """Something that happened, who did it, and to what. Written in the same
    transaction as the change it records, and never changed after.

    Each has a level (horatio.audit): debug, info or notice. Debug and info events
    are deleted once older than the custodian's retention for their level
    (horatio.audit_retention). Notice events are never deleted, and every action a
    feature reads back from the log as history (title history, the chronicle, a
    location's log...) must be notice: `tests/test_audit_levels.py` checks the
    readers. A log shown to staff or players (a troupe's, a character's) shows what
    is still kept, and never debug events."""

    __tablename__ = "audit_events"
    __table_args__ = (
        # Newest first, a page at a time, across every troupe (the custodian's search).
        Index("ix_audit_events_created_at_id", "created_at", "id"),
        # The purge, and the search by level.
        Index("ix_audit_events_level_created_at", "level", "created_at"),
        CheckConstraint("level in ('debug', 'info', 'notice')", name="level"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    # Set to null if the character is deleted; `data` keeps its name.
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str]
    # debug, info or notice: the action's level when it was recorded.
    level: Mapped[str] = mapped_column(server_default="info")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
