import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class InfluenceBlock(Record):
    """One discovery block on an influence entry, added when staff accepted a
    player's discovery block answer (horatio.influence_lookups). Each adds one to
    the entry's `blocks`; taking it away takes that one back off."""

    __tablename__ = "influence_blocks"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("influence_entries.id", ondelete="CASCADE"), index=True
    )
    # The answer whose response added it: one block for each answer.
    response_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("responses.id", ondelete="SET NULL"), unique=True
    )
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
