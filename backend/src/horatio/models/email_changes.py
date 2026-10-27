import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class EmailChange(Record):
    """A change of someone's email waiting to be confirmed at the new address
    (horatio.email_changes). The link holds the token, the table its hash. At most
    one per person; confirmed, cancelled or replaced, the row is deleted, and the
    audit log keeps what happened."""

    __tablename__ = "email_changes"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    new_email: Mapped[str]
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The person themself, or the custodian who started it.
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Why the custodian changed it; none when the person changes their own.
    reason: Mapped[str | None] = mapped_column(Text)
