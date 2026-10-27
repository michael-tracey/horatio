import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class AuditEvent(Record):
    """Something that happened, who did it, and to what. Never updated or deleted.
    Written in the same transaction as the change it records."""

    __tablename__ = "audit_events"
    # Newest first, a page at a time, across every troupe (the custodian's search).
    __table_args__ = (Index("ix_audit_events_created_at_id", "created_at", "id"),)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    # Set to null if the character is deleted; `data` keeps its name.
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str]
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
