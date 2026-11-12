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
        CheckConstraint("(status = 'fading') <= (fades_on is not null)", name="fading"),
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
    # A fading bond (#662): the day it ends, and why it fades ("regnant_died": its
    # regnant met Final Death, so it fades over a month, p. 296). The thrall still
    # feels it until then, and their player is told only that it faded, never why.
    fades_on: Mapped[date | None] = mapped_column(Date)
    fade_reason: Mapped[str] = mapped_column(default="", server_default="")
    # When the thrall's player was told a faded bond had faded: until then their
    # character's sheet shows it as it was. Set at once for a thrall with no player.
    thrall_told_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Its thrall met Final Death and the regnant's player knew of the bond: they go on
    # seeing it as it was, for the regnant has no sense of the thrall's death, until
    # staff clear it.
    kept_for_regnant: Mapped[bool] = mapped_column(default=False, server_default="false")
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


class BondReport(Record):
    """A drink a player reported for their own character (#661), waiting until it is
    decided: on the troupe's running staff, through its approvals queue (the troupe's
    setting "players report and staff approves", or a regnant's drink whose thrall has
    no player to confirm it); or on the thrall's player, who confirms or declines a
    drink the regnant's player recorded ("players manage"). Its drink goes in the
    bond's log only once it is approved or confirmed (horatio.bonds)."""

    __tablename__ = "bond_reports"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'withdrawn')", name="status"
        ),
        CheckConstraint("waiting_on in ('staff', 'thrall')", name="waiting_on"),
        CheckConstraint("reported_as in ('thrall', 'regnant')", name="reported_as"),
        CheckConstraint("source in ('game', 'downtime')", name="source"),
        CheckConstraint("(thrall_id is null) <> (thrall_name = '')", name="thrall"),
        CheckConstraint("(regnant_id is null) <> (regnant_name = '')", name="regnant"),
        CheckConstraint("(waiting_on = 'staff') = (approval_id is not null)", name="approval"),
    )

    # The troupe whose bonds it goes to.
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    thrall_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    thrall_name: Mapped[str] = mapped_column(default="", server_default="")
    regnant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    regnant_name: Mapped[str] = mapped_column(default="", server_default="")
    # Which side the reporting player's character is on.
    reported_as: Mapped[str]
    night: Mapped[date] = mapped_column(Date)
    # At a game, or in a downtime.
    source: Mapped[str]
    note: Mapped[str] = mapped_column(default="", server_default="")
    status: Mapped[str] = mapped_column(default="pending", server_default="pending")
    # Who decides it: running staff, or the thrall's player.
    waiting_on: Mapped[str]
    # Its request in the troupe's approvals queue, while staff decide it.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id", ondelete="CASCADE"), unique=True
    )
    reported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why it was declined, for the player who reported it.
    reason: Mapped[str] = mapped_column(default="", server_default="")
    # The bond its drink went to, once approved or confirmed.
    bond_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("blood_bonds.id", ondelete="SET NULL")
    )
