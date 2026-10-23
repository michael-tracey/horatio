import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class PlayGame(Record):
    """One game as a character's Play View tracked it: what was spent, tap by tap.
    Resetting for the next game ends it, kept with its log, and starts the next."""

    __tablename__ = "play_games"
    __table_args__ = (
        UniqueConstraint("character_id", "number"),
        # One game at a time.
        Index(
            "uq_play_games_open",
            "character_id",
            unique=True,
            postgresql_where=text("ended_at is null"),
        ),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    # 1 for the character's first game, counting up.
    number: Mapped[int]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The trackers after the latest tap, worked out from the log (horatio.play).
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Blood starts at half, rounded up: the character fed short last downtime.
    half_blood: Mapped[bool] = mapped_column(default=False, server_default="false")


class PlayEvent(Record):
    """One tap in a game: a tracker changed, a note, or the undoing of an earlier
    tap. Kept in the order the taps happened on the device, which can differ from
    the order they arrived in when a phone was offline."""

    __tablename__ = "play_events"
    __table_args__ = (
        CheckConstraint("kind in ('change', 'note', 'undo')", name="kind"),
        CheckConstraint("damage is null or damage in ('normal', 'aggravated')", name="damage"),
        CheckConstraint("kind <> 'undo' or undoes_id is not null", name="undo_names_a_tap"),
    )

    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("play_games.id"), index=True)
    # The id the device gave the tap, so a tap sent twice is recorded once.
    client_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # When it happened on the device.
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str]
    # What changed: blood, willpower, health, morality, beast, a trait's uses
    # ("trait:backgrounds/Herd/") or a custom counter's ("counter:<id>").
    tracker: Mapped[str] = mapped_column(default="", server_default="")
    # Up or down by this much; for health, damage taken (or healed, negative).
    amount: Mapped[int] = mapped_column(default=0, server_default="0")
    # For health: normal or aggravated.
    damage: Mapped[str | None]
    note: Mapped[str] = mapped_column(default="", server_default="")
    undoes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("play_events.id"))
    # The tracker before and after, as the log replays (for health, boxes marked).
    before: Mapped[int | None]
    after: Mapped[int | None]


class PlayCounter(Record):
    """A counter a player added to their Play View, such as "Fetish charges: 3".
    Each game starts it back at `uses`. Removed ones are kept for the old logs."""

    __tablename__ = "play_counters"
    __table_args__ = (CheckConstraint("uses > 0", name="uses_positive"),)

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    name: Mapped[str]
    uses: Mapped[int]
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
