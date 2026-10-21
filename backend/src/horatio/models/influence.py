import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class InfluenceEntry(Record):
    """One influence action taken, in a troupe's influence log (CONTEXT.md: Influence
    Entry). Kept by horatio.influence_log, which records each change in the audit log."""

    __tablename__ = "influence_entries"
    __table_args__ = (
        CheckConstraint("type in ('elite', 'underworld')", name="type"),
        CheckConstraint("source in ('downtime', 'game', 'hand', 'import')", name="source"),
        CheckConstraint("times >= 1", name="times"),
        CheckConstraint("blocks >= 0", name="blocks"),
        CheckConstraint("number >= 1", name="number"),
        CheckConstraint("action_key is not null or needs_details", name="action_or_details"),
        # The short id, E12 or UW7, is the type's letters and this number.
        UniqueConstraint("troupe_id", "type", "number", name="uq_influence_entries_number"),
        # An imported row's id in the sheet it came from, so an import can run again.
        UniqueConstraint("troupe_id", "reference", name="uq_influence_entries_reference"),
        # Lookups count back from when each action happened.
        Index("ix_influence_entries_troupe_happened", "troupe_id", "happened_at"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"))
    type: Mapped[str]
    number: Mapped[int]
    # When it was taken, to the minute: a downtime's submission, a game's tap, the
    # time staff give, or an imported date at midnight.
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Null for someone not in Horatio, or a character since deleted; `name` keeps
    # the name either way.
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str]
    specialization: Mapped[str] = mapped_column(default="", server_default="")
    # The action's key in the troupe's rules (horatio.influence); null only while
    # the entry needs details.
    action_key: Mapped[str | None]
    purpose: Mapped[str] = mapped_column(default="", server_default="")
    # The same action taken several times for one purpose.
    times: Mapped[int] = mapped_column(default=1, server_default="1")
    # Discovery blocks on it: a lookup needs more strength than this to find it.
    blocks: Mapped[int] = mapped_column(default=0, server_default="0")
    # Where it came from: a downtime answer, a game's tap, staff by hand, an import.
    source: Mapped[str]
    # The cycle a downtime answer was in, or that staff say it applies to.
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("downtime_cycles.id"), index=True)
    # The Play View tap that spent it.
    play_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("play_events.id", ondelete="SET NULL"), index=True
    )
    reference: Mapped[str | None]
    # Logged without its specialisation, action or purpose, for staff to finish.
    needs_details: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Who logged it; null for an import run from the command line.
    logged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
