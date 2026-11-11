import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class BloodBond(Record):
    """A blood bond (CONTEXT.md: Blood Bond): a thrall's to a regnant, kept by one
    troupe's running staff (horatio.bonds). Either side is a character (a PC or an
    NPC) or, for someone not in Horatio, a name only. Its level is never stored: it
    comes from its log (BondEntry), so drinks on one night count once."""

    __tablename__ = "blood_bonds"
    __table_args__ = (
        CheckConstraint("status in ('active', 'fading', 'ended', 'broken')", name="status"),
        CheckConstraint("(thrall_id is null) <> (thrall_name = '')", name="thrall"),
        CheckConstraint("(regnant_id is null) <> (regnant_name = '')", name="regnant"),
        CheckConstraint("thrall_id <> regnant_id", name="not_own_regnant"),
        CheckConstraint("(status in ('ended', 'broken')) = (ended_at is not null)", name="ended"),
    )

    # The troupe whose running staff keep it, and whose Blood bonds setting says
    # whether it shows at all.
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    # The one bound: a character, or a name only.
    thrall_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    thrall_name: Mapped[str] = mapped_column(default="", server_default="")
    # The one whose blood binds them: a vampire character, or a name only.
    regnant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    regnant_name: Mapped[str] = mapped_column(default="", server_default="")
    # active; fading, still felt by the thrall but ending (its regnant is dead, say);
    # ended, by fading or wiped away by a full bond to another (p. 295); or broken,
    # by staff with a reason (p. 296). Ended and broken bonds are kept as history.
    status: Mapped[str] = mapped_column(default="active", server_default="active")
    # Staff have told the regnant's player of it: only then do they see it.
    known_to_regnant: Mapped[bool] = mapped_column(default=False, server_default="false")
    # When it ended or was broken, by whom (for one a full bond wiped away, whoever
    # recorded the drink that made it full), and why.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ended_reason: Mapped[str] = mapped_column(default="", server_default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class BondEntry(Record):
    """A line of a blood bond's log, from which its level is worked out
    (horatio.bonds.level_of): a drink, on a night, which counts once a night; or the
    bond entered by staff at the level it already stood at, such as one from before
    Horatio, with the reason."""

    __tablename__ = "bond_entries"
    __table_args__ = (
        CheckConstraint("kind in ('drink', 'entered')", name="kind"),
        CheckConstraint("source in ('game', 'downtime', 'staff')", name="source"),
        CheckConstraint("(kind = 'entered') = (level is not null)", name="entered_level"),
        CheckConstraint("level between 1 and 3", name="level"),
    )

    bond_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blood_bonds.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str]
    # The night it happened: for a bond entered, the night it stood at `level` from.
    night: Mapped[date] = mapped_column(Date)
    # Where it was told: at a game, in a downtime, or to staff some other way.
    source: Mapped[str] = mapped_column(default="staff", server_default="staff")
    # For a bond entered, the level it stood at: 1 to 3 drinks.
    level: Mapped[int | None]
    # A note, or for a bond entered, the reason.
    note: Mapped[str] = mapped_column(default="", server_default="")
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
