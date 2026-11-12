import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class BoonTalon(Record):
    """A Lesser Harpy, or talon (horatio.boon_talons, #689; MET: VTM p. 379): a
    character the troupe's Harpy gave access to the boon ledger, with what they may
    do beyond seeing it. The access belongs to the office, not to the Harpy who gave
    it: a new Harpy finds the list and keeps or removes each one."""

    __tablename__ = "boon_talons"
    __table_args__ = (UniqueConstraint("troupe_id", "character_id"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    # Register boons.
    can_add: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Edit, trade, pass on, settle, void and reopen boons, and review reports.
    can_edit: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Audit a character's boons (#690).
    can_audit: Mapped[bool] = mapped_column(default=False, server_default="false")
    # The Harpy who gave it, as their character; none when staff did, or once deleted.
    given_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
