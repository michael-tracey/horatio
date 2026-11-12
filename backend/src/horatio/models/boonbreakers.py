import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Boonbreaker(Record):
    """A character declared a Boonbreaker in one troupe's boon ledger (CONTEXT.md:
    Boonbreaker; horatio.boonbreakers; MET: VTM p. 397): every boon owed to or by them
    there made void, and Disgraced while the mark stands. Lifted on mercy, from the
    Harpy or a court of Harpies (p. 398), it stays, as a record."""

    __tablename__ = "boonbreakers"
    __table_args__ = (
        # One standing mark per character per troupe; lifted ones are kept.
        Index(
            "uq_boonbreakers_standing",
            "troupe_id",
            "character_id",
            unique=True,
            postgresql_where=text("lifted_at is null"),
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    # The boon they refused to pay, if it is in the ledger.
    refused_boon_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("boons.id", ondelete="SET NULL")
    )
    note: Mapped[str] = mapped_column(default="", server_default="")
    declared_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The Harpy who declared it, as their character (#688); none for staff.
    declared_as_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    # The boons the declaration made void, to restore one by one on mercy.
    voided: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # The Disgraced it gave them (horatio.sect_status), held while the mark stands;
    # none when they hold no status, or once it is gone.
    held_status_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("held_statuses.id", ondelete="SET NULL")
    )
    # Each appeal for mercy: {"to": "harpy" | "court", "outcome": "granted" |
    # "refused", "against": votes against at a court, "note", "on" (a date), "by"}.
    appeals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Mercy: when the mark was lifted, by whom, why, and the boons restored then.
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lifted_note: Mapped[str] = mapped_column(default="", server_default="")
    restored: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
