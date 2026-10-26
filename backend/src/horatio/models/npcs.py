import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class StockNpc(Record):
    """What a Stock NPC has in place of a sheet (MET: VTM pp. 489–490; see
    horatio.rules.stock): its NPC rating and specializations, and staff's notes.
    Its name, kind and picture are on its character."""

    __tablename__ = "stock_npcs"
    __table_args__ = (CheckConstraint("rating >= 1", name="rating"),)

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True
    )
    rating: Mapped[int]
    # Each {"type": "skill" or "power", "name"}: a skill, or a discipline, path or
    # numina its kind allows, as "Thaumaturgy: Lure of Flames" or "True Faith".
    specializations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    notes: Mapped[str] = mapped_column(default="", server_default="")
