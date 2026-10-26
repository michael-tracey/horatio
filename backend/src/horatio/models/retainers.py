import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Retainer(Record):
    """One of a character's Retainers (core book p. 104): named, with its own dots,
    and perhaps linked to an NPC built for it."""

    __tablename__ = "retainers"
    __table_args__ = (
        CheckConstraint("dots >= 1", name="dots"),
        CheckConstraint("lost is null or lost in ('released', 'killed')", name="lost"),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(default=0, server_default="0")
    name: Mapped[str]
    dots: Mapped[int]
    description: Mapped[str] = mapped_column(default="", server_default="")
    # The merit that gave it, such as "Ghostly Retainer"; empty for the background's.
    from_merit: Mapped[str] = mapped_column(default="", server_default="")
    # released | killed, and the day it happened; null while it serves.
    lost: Mapped[str | None]
    lost_on: Mapped[date | None] = mapped_column(Date)
    # The NPC staff linked to it.
    npc_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    # A ghoul has 5 potent Blood and may take a discipline specialty (p. 105).
    ghoul: Mapped[bool] = mapped_column(default=False, server_default="false")
    # One specialty a dot (p. 105): skills, each +5 to the pool, and for a ghoul
    # perhaps one discipline in-clan for its domitor, to its dots.
    specialties: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    discipline: Mapped[str] = mapped_column(default="", server_default="")


class AlternateIdentity(Record):
    """What is kept for one of a character's Alternate Identities (core pp. 98-99),
    by the name it is bought under on the sheet: the sect or group that has
    Accepted it, if any (p. 310)."""

    __tablename__ = "alternate_identities"
    __table_args__ = (UniqueConstraint("character_id", "name"),)

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str]
    accepted_by: Mapped[str] = mapped_column(default="", server_default="")
