import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class DowntimeCycle(Record):
    """One round of downtimes for a troupe (CONTEXT.md: Downtime Cycle)."""

    __tablename__ = "downtime_cycles"
    __table_args__ = (
        CheckConstraint("status in ('draft', 'open', 'closed', 'complete')", name="status"),
        CheckConstraint("grace_ends_at >= closes_at", name="grace_after_close"),
        # One open cycle per troupe at a time.
        Index(
            "uq_downtime_cycles_one_open",
            "troupe_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    status: Mapped[str] = mapped_column(default="draft", server_default="draft")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Submissions after this are late; after the grace period they need a storyteller.
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grace_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Question(Record):
    """One prompt on a cycle's downtime form. Each cycle owns its own questions."""

    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("kind in ('action', 'custom')", name="kind"),
        CheckConstraint("(kind = 'action') = (action_kind is not null)", name="action_has_kind"),
        CheckConstraint(
            "answer_type in ('long_text', 'short_text', 'choice', 'number', 'yes_no')",
            name="answer_type",
        ),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("downtime_cycles.id"), index=True)
    position: Mapped[int]
    kind: Mapped[str]
    action_kind: Mapped[str | None]
    prompt: Mapped[str]
    help_text: Mapped[str] = mapped_column(default="", server_default="")
    answer_type: Mapped[str] = mapped_column(default="long_text", server_default="long_text")
    options: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    required: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Action questions: at most this many answers, each spending an action.
    # Null means as many as the allowance permits.
    max_answers: Mapped[int | None]
    # Who sees the question, for example {"splats": ["vampire"]}; null = everyone.
    visible_to: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class CycleParticipant(Record):
    """A character taking part in a downtime cycle, and its action allowance,
    fixed when it joined the cycle."""

    __tablename__ = "cycle_participants"
    __table_args__ = (UniqueConstraint("cycle_id", "character_id"),)

    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("downtime_cycles.id"), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    allowance: Mapped[dict[str, int]] = mapped_column(JSONB)
    allowance_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Null when added as the cycle opened.
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # A storyteller let this participant submit after the grace period.
    late_accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AllowanceAdjustment(Record):
    __tablename__ = "allowance_adjustments"

    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cycle_participants.id"), index=True
    )
    action_kind: Mapped[str]
    delta: Mapped[int]
    reason: Mapped[str]
    adjusted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Submission(Record):
    __tablename__ = "submissions"
    __table_args__ = (CheckConstraint("status in ('draft', 'submitted')", name="status"),)

    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cycle_participants.id"), unique=True
    )
    status: Mapped[str] = mapped_column(default="draft", server_default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    late: Mapped[bool] = mapped_column(default=False, server_default="false")


class Answer(Record):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("submission_id", "question_id", "slot"),)

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), index=True)
    # Which answer to this question: an action question may be answered several times.
    slot: Mapped[int] = mapped_column(default=1, server_default="1")
    body: Mapped[str]
    # The action kind's extra fields, such as an influence level.
    structured: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Response(Record):
    """A staff member's answer to one answer in a submission (CONTEXT.md: Response)."""

    __tablename__ = "responses"
    __table_args__ = (
        CheckConstraint("status in ('unassigned', 'assigned', 'written')", name="status"),
        CheckConstraint(
            "not (assigned_to_any_narrator and assigned_to_user_id is not null)",
            name="one_assignee",
        ),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("answers.id"), unique=True)
    body: Mapped[str] = mapped_column(default="", server_default="")
    status: Mapped[str] = mapped_column(default="unassigned", server_default="unassigned")
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    assigned_to_any_narrator: Mapped[bool] = mapped_column(default=False, server_default="false")
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    written_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    written_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Delivery(Record):
    """Sending a submission's responses to its player (CONTEXT.md: Delivery)."""

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint("channel in ('horatio', 'discord', 'email')", name="channel"),
        CheckConstraint("status in ('pending', 'sent', 'failed')", name="status"),
        # Never send the same submission twice on one channel.
        Index(
            "uq_deliveries_sent_once",
            "submission_id",
            "channel",
            unique=True,
            postgresql_where=text("status = 'sent' and not test_mode"),
        ),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    channel: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending", server_default="pending")
    test_mode: Mapped[bool] = mapped_column(default=False, server_default="false")
    message: Mapped[str]
    sent_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    last_error: Mapped[str | None]
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class RandomTable(Record):
    """A fill table, such as feeding or patrol results. Entries may name other
    tables in square brackets, "[Location]", to be filled in from them."""

    __tablename__ = "random_tables"
    __table_args__ = (UniqueConstraint("troupe_id", "name"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    entries: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
