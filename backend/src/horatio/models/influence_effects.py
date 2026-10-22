import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class InfluenceEffect(Record):
    """A change a targeted influence action made, while it lasts (horatio.influence_effects):
    an Attack's lost levels, a Boost's raise, or a Block on an activity. It ends by
    itself, by its dates and the target's games; nothing needs to end it."""

    __tablename__ = "influence_effects"
    __table_args__ = (
        CheckConstraint("kind in ('attack', 'boost', 'block')", name="kind"),
        CheckConstraint("type in ('elite', 'underworld')", name="type"),
        CheckConstraint("levels >= 0 and defended >= 0 and games >= 0", name="counts"),
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    kind: Mapped[str]
    # The influence it changes: the target's for an Attack or Boost, the blocked one
    # for a Block.
    type: Mapped[str]
    # The target of an Attack or Boost, with its name as it was; none for a Block.
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(default="", server_default="")
    # The log entry it came from; none for a Block staff recorded on its own. One
    # effect an entry.
    entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("influence_entries.id", ondelete="SET NULL"), unique=True
    )
    # Levels lost (Attack, after Defends), levels raised (Boost), or a Block's strength.
    levels: Mapped[int]
    # Levels the target's Defends took off an Attack.
    defended: Mapped[int] = mapped_column(default=0, server_default="0")
    # A Block's activity, such as "acquiring firearms".
    activity: Mapped[str] = mapped_column(default="", server_default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # It lasts at least to here; an Attack also lasts until the target has played
    # `games` more games.
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    games: Mapped[int] = mapped_column(default=0, server_default="0")
    # The actions an Attack took from (or a Boost added to) the target's next
    # downtime allowance.
    owed_action_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("owed_actions.id", ondelete="SET NULL")
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
