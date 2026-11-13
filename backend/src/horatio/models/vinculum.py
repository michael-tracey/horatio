import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Vaulderie(Record):
    """A Vaulderie a Sabbat troupe's running staff recorded, or a player reported for
    their own character (#666; MET: VTM pp. 433-434), kept by the troupe that keeps its
    blood bonds (horatio.vinculum). Its participants' Vinculum ratings come from the
    Vaulderies recorded, never typed in."""

    __tablename__ = "vaulderies"
    __table_args__ = (
        CheckConstraint(
            "status in ('recorded', 'pending', 'declined', 'withdrawn', 'removed')",
            name="status",
        ),
        CheckConstraint("source in ('game', 'downtime', 'staff')", name="source"),
        CheckConstraint("officiant_id is null or officiant_name = ''", name="officiant"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    night: Mapped[date] = mapped_column(Date)
    # Who officiated: a character, a name only, or nobody named.
    officiant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"))
    officiant_name: Mapped[str] = mapped_column(default="", server_default="")
    # Where it was told: at a game, in a downtime, or to staff some other way.
    source: Mapped[str] = mapped_column(default="staff", server_default="staff")
    note: Mapped[str] = mapped_column(default="", server_default="")
    # recorded, which counts; pending, a player's report waiting on staff; declined or
    # withdrawn, which never counted; removed by staff with a reason, which no longer
    # counts.
    status: Mapped[str] = mapped_column(default="recorded", server_default="recorded")
    # Who recorded it, or reported it.
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # A player's report: who decided it, when, and why it was declined or removed.
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(default="", server_default="")


class VaulderieParticipant(Record):
    """One who took part in a Vaulderie: a character (a PC or an NPC) or a name only. A
    false Sabbat drank but gave no blood: they gain Vinculum ratings to the others, but
    the others gain none to them from it (the Errata's p. 434)."""

    __tablename__ = "vaulderie_participants"
    __table_args__ = (CheckConstraint("(character_id is null) <> (name = '')", name="who"),)

    vaulderie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vaulderies.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    name: Mapped[str] = mapped_column(default="", server_default="")
    false_sabbat: Mapped[bool] = mapped_column(default=False, server_default="false")


class VinculumTie(Record):
    """A background tie (p. 435's example): two who shared Vaulderies before Horatio,
    entered by staff at the rating it stood at on a night, with the reason. It counts as
    the history that would give that rating then, and thins with time like any other."""

    __tablename__ = "vinculum_ties"
    __table_args__ = (
        CheckConstraint("(one_id is null) <> (one_name = '')", name="one"),
        CheckConstraint("(other_id is null) <> (other_name = '')", name="other"),
        CheckConstraint("rating between 1 and 5", name="rating"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    one_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    one_name: Mapped[str] = mapped_column(default="", server_default="")
    other_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    other_name: Mapped[str] = mapped_column(default="", server_default="")
    rating: Mapped[int]
    night: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(default="", server_default="")
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
