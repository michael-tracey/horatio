import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class QuestRequest(Record):
    """A player asking their troupe's staff for a quest (CONTEXT.md: Quest Request),
    waiting in the troupe's queue until staff answer it (horatio.quests). Kept after
    it is answered or withdrawn."""

    __tablename__ = "quest_requests"
    __table_args__ = (
        # A custom quest; or one about a location (horatio.location_quests): to
        # acquire it, add a quality, undermine it or repair it; or learning whose
        # locations are whose with Contacts.
        CheckConstraint(
            "kind in ('custom', 'acquire', 'quality', 'undermine', 'repair', 'whose')",
            name="kind",
        ),
        CheckConstraint("status in ('new', 'working', 'answered', 'withdrawn')", name="status"),
        CheckConstraint(
            "outcome is null or outcome in ('quest', 'not_needed', 'refused', 'done')",
            name="outcome",
        ),
        CheckConstraint(
            "not (assigned_to_any_narrator and assigned_to_user_id is not null)",
            name="one_assignee",
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(default="custom", server_default="custom")
    # What the player wants to achieve, in their own words; why; and who they would
    # bring.
    objective: Mapped[str]
    reason: Mapped[str] = mapped_column(default="", server_default="")
    companions: Mapped[str] = mapped_column(default="", server_default="")
    # What a location request names: the place by name, address and map link, the
    # quality or negative wanted, a victory condition, or another character.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # The location record it is about: the character's own, or the one staff matched
    # it to or made from it.
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    # The downtime cycle whose request limit it counts against: the open one when it
    # was made, or the next; null when the troupe had neither.
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("downtime_cycles.id", ondelete="SET NULL"), index=True
    )
    # new: no one has started on it; working: assigned, or a quest is being built;
    # answered; or withdrawn by the player.
    status: Mapped[str] = mapped_column(default="new", server_default="new", index=True)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    assigned_to_any_narrator: Mapped[bool] = mapped_column(default=False, server_default="false")
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # How staff answered: with a quest, as not needed (which gives the slot back),
    # refused, or done without a quest (a repair, a Contacts lookup); with a note for
    # the player.
    outcome: Mapped[str | None]
    note: Mapped[str] = mapped_column(default="", server_default="")
    answered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The quest built from it.
    quest_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("quests.id", ondelete="SET NULL"))
    # Staff who have marked it read, by user id, with when.
    read_by: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")


class Quest(Record):
    """A quest (CONTEXT.md: Quest; MET: VTM Vol. II Issue 1, pp. 99-110): an
    objective with a category and difficulty, requirements to meet and scenarios to
    pass, a leader and a party. Horatio tracks it; the tests happen at the table or
    in downtime (horatio.quests)."""

    __tablename__ = "quests"
    __table_args__ = (
        CheckConstraint("category in ('simple', 'complex', 'epic')", name="category"),
        # A location's qualities can raise it past 5 (Vol. II Issue 1, p. 126).
        CheckConstraint("difficulty between 1 and 10", name="difficulty"),
        CheckConstraint(
            "status in ('draft', 'active', 'completed', 'failed', 'closed')", name="status"
        ),
        CheckConstraint("offer in ('character', 'chosen', 'unlocked', 'troupe')", name="offer"),
        CheckConstraint(
            "(offer = 'unlocked') = (unlock_quest_id is not null and unlock_scenario is not null)",
            name="unlock_names_a_scenario",
        ),
        CheckConstraint(
            "not (assigned_to_any_narrator and assigned_to_user_id is not null)",
            name="one_assignee",
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    objective: Mapped[str] = mapped_column(default="", server_default="")
    category: Mapped[str] = mapped_column(default="simple", server_default="simple")
    difficulty: Mapped[int] = mapped_column(default=1, server_default="1")
    # Must be completed in downtime: its results are recorded only through a downtime
    # Quest action (horatio.quest_actions).
    downtime_only: Mapped[bool] = mapped_column(default=False, server_default="false")
    # For staff only.
    staff_notes: Mapped[str] = mapped_column(default="", server_default="")
    # The location it changes when it is completed, and how
    # (horatio.location_quests.Change): control passes to its leader, a quality is
    # added or swapped, its type upgraded, a negative added, or an infiltration's
    # victory condition recorded.
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    location_change: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # draft while staff build it; active once its requirements are sent; then
    # completed or failed after its last scenario, or closed by staff at any point.
    status: Mapped[str] = mapped_column(default="draft", server_default="draft", index=True)
    # The character it is for. A quest offered more widely may have none until
    # someone joins.
    leader_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), index=True
    )
    # Who may see and join it besides its leader and those it is shared with: the
    # leader only (character), characters staff chose (chosen), anyone who passed a
    # scenario of another quest (unlocked), or the whole troupe (troupe).
    offer: Mapped[str] = mapped_column(default="character", server_default="character")
    unlock_quest_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quests.id", ondelete="SET NULL"), index=True
    )
    unlock_scenario: Mapped[int | None]
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    assigned_to_any_narrator: Mapped[bool] = mapped_column(default=False, server_default="false")
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    read_by: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Its requirements sent to the leader and party.
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Completed or failed: when, and the party then ([{id, name}]).
    ended_on: Mapped[date | None] = mapped_column(Date)
    ended_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    finished_by: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # Closed by staff, and why ("No longer relevant").
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    close_note: Mapped[str] = mapped_column(default="", server_default="")
    # Telling the Tale (p. 102): the players' account, which staff edit and approve
    # as the official one.
    tale: Mapped[str] = mapped_column(default="", server_default="")
    tale_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    tale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tale_approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    tale_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestMember(Record):
    """A character a quest is shared with or offered to, who may join its party
    (CONTEXT.md: Party). The leader is the quest's own, not a row here."""

    __tablename__ = "quest_members"
    __table_args__ = (
        UniqueConstraint("quest_id", "character_id"),
        CheckConstraint("status in ('invited', 'joined', 'left')", name="status"),
    )

    quest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quests.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    # invited: it may see the quest and join; joined: in the party; left: dropped out.
    status: Mapped[str] = mapped_column(default="invited", server_default="invited")
    # Who shared it: the leader's player, or staff.
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestRequirement(Record):
    """One of a quest's requirements (CONTEXT.md: Quest Requirement): one or more
    alternatives, each a trait, an aspect, something to expend or words
    (horatio.quest_requirements), and who met it."""

    __tablename__ = "quest_requirements"

    quest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quests.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    # The alternatives, any one of which meets it: [{"kind": "trait", ...}, ...].
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Met: by which character (a party member, or a patron the story allows), with
    # which alternative, and when; what meeting it spent, to undo it.
    met_by_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL")
    )
    met_by_name: Mapped[str] = mapped_column(default="", server_default="")
    met_option: Mapped[int | None]
    met_patron: Mapped[bool] = mapped_column(default=False, server_default="false")
    met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    met_marked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    spent: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class QuestScenario(Record):
    """One of a quest's scenarios (CONTEXT.md: Scenario), numbered from 1: what its
    success and failure say, and its result once staff send it."""

    __tablename__ = "quest_scenarios"
    __table_args__ = (
        UniqueConstraint("quest_id", "number"),
        CheckConstraint("result is null or result in ('passed', 'failed')", name="result"),
    )

    quest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quests.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int]
    success_text: Mapped[str] = mapped_column(default="", server_default="")
    fail_text: Mapped[str] = mapped_column(default="", server_default="")
    result: Mapped[str | None]
    # What was sent: the success or fail text as it stood.
    result_text: Mapped[str] = mapped_column(default="", server_default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Recorded through a downtime cycle's Quest actions (horatio.quest_actions): it
    # goes out with that cycle's delivery, and sent_at stays empty until then.
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("downtime_cycles.id", ondelete="SET NULL"), index=True
    )
    # The party when it passed ([character id]): who it unlocks other quests for.
    party: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Resources spent on it on a location quest, each {character_id, name, dots,
    # successes} (Vol. II Issue 1, p. 120).
    resources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )


class QuestLogEntry(Record):
    """One line in a quest's log, for staff: what happened to it, or a note."""

    __tablename__ = "quest_log_entries"

    quest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("quests.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str]
