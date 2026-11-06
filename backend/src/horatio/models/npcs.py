import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
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


class NpcClaim(Record):
    """A claim link for a sheeted NPC (horatio.npc_gifts): whoever opens it, and
    claims, is given the NPC as their own character. The link holds the token, the
    table its hash. At most one per NPC; used, cancelled or replaced, the row is
    deleted, and the audit log keeps what happened."""

    __tablename__ = "npc_claims"
    __table_args__ = (CheckConstraint("carried_xp >= 0", name="carried_xp"),)

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True
    )
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Unspent XP the player had banked elsewhere, given as its own entry on claiming.
    carried_xp: Mapped[int] = mapped_column(default=0, server_default="0")
    carried_reason: Mapped[str] = mapped_column(default="", server_default="")
