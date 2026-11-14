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
    # Beast traits the game starts with: a diablerie added them (horatio.diablerie).
    beast_start: Mapped[int] = mapped_column(default=0, server_default="0")
    # Willpower the game starts with, when its player said at check-in that the
    # character had no full day's rest (horatio.checkin): where the game before left
    # it. None for full, as after a day's rest (MET: VtM core, p. 288).
    willpower_start: Mapped[int | None]
    # The character's sect status at this game (horatio.play_status): its source of
    # abiding status, a title's status chosen for it, the titles whose holders are
    # away, and the titles it held as the game began.
    status: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Retainer upkeep as the night began (horatio.retainer_upkeep): what was taken,
    # and the Retainers left neglected. None until the night begins.
    upkeep: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


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
    # A fleeting status this tap spent for good: its record, so Undo gives it back
    # (horatio.play_status).
    held_status: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # A Leadership use spent learning about another character's status: whose, and
    # which (horatio.play_others).
    learned: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # An item this tap gave or discarded (horatio.equipment.by_tap): its name, who it
    # went to, and its history's event, so Undo takes it back; or why it was refused.
    # On an undo, why the item stayed where it was, if it did.
    equipment: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Retainer upkeep the server took as the night began (horatio.retainer_upkeep):
    # the period and the Retainers paid for, or, on a note, those left neglected.
    upkeep: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


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


class PlayDerangement(Record):
    """A temporary derangement a player or staff added on the Play View, such as one
    from Voice of Madness. Its id is the one the device gave it, so the taps that
    add and remove it ("derangement:<id>") can be made offline. Whether the
    character has it is worked out from those taps (horatio.play)."""

    __tablename__ = "play_derangements"

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    name: Mapped[str]
    # Where it came from: "Voice of Madness", a quest's consequence.
    source: Mapped[str] = mapped_column(default="", server_default="")
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class PoolModifier(Record):
    """A bonus or penalty a player noted on their character's test pools, such as
    "+2 Social, against mortals: Fame". Kept per character, across games and
    Resets, and switched on and off at the table. Removed ones are deleted."""

    __tablename__ = "pool_modifiers"
    __table_args__ = (CheckConstraint("amount <> 0", name="amount_not_zero"),)

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    label: Mapped[str]
    amount: Mapped[int]
    # Which pools it changes: "all", "attack", "defense", an attribute ("Social"),
    # or one pool's key ("pool:dodge"). The Pools tab works out the rest.
    pools: Mapped[str]
    # A note shown beside it, not worked out: "against mortals".
    when: Mapped[str] = mapped_column(default="", server_default="")
    on: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class PlayEffect(Record):
    """A power's effect that lasts until undone, not until the game ends (issue
    #822): Heart of Darkness's removed heart, a Malleable Visage, Bonecraft. It
    belongs to the character it is on, not to a game, so it is kept through Reset
    (horatio.play_effects).

    `character_id` is who it is on and `source_character_id` who used the power:
    the same character for one on itself. One used on another character in the same
    troupe (issue #823) is made `active` at once, as the target can't refuse a
    power that worked; they acknowledge it, or dispute it to staff. `offered` and
    `declined` are kept for flows that ask first."""

    __tablename__ = "play_effects"
    __table_args__ = (
        CheckConstraint("state in ('offered', 'active', 'declined', 'ended')", name="state"),
        # A character carries one application of a power at a time (core p. 168):
        # using it again replaces the last.
        Index(
            "uq_play_effects_active",
            "character_id",
            "key",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    # None once the character who used it is deleted: the effect stays on its
    # target, with that character's name (horatio.deletion).
    source_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id"), index=True
    )
    source_name: Mapped[str] = mapped_column(default="", server_default="")
    # The switch it holds on (horatio.reference.Switch.key): "Heart removed".
    key: Mapped[str]
    # What was chosen when the power was used (issue #821), such as Bonecraft's
    # modifications, and amounts picked (issue #824), such as Tough's 1-3.
    options: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    amounts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict, server_default="{}")
    state: Mapped[str] = mapped_column(default="active", server_default="active")
    # The device's id for it: the tap that made it, so a tap sent twice makes it once.
    client_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    # The Play View tap that made it, and the one that ended it, if taps did.
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("play_events.id"))
    ended_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("play_events.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # For one on another character: when its target acknowledged it, or disputed it
    # to staff with a note (issue #823).
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispute_note: Mapped[str] = mapped_column(default="", server_default="")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Why it ended: "off" (turned off), "replaced" (used again), "undone", "staff".
    ended_how: Mapped[str] = mapped_column(default="", server_default="")
    # The effect this one replaced, which undoing this one brings back.
    replaced_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("play_effects.id"))
