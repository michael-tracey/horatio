import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Backstory(Record):
    """A character's backstory, in Markdown (horatio.backstories): one per character,
    kept apart from the sheet so that loading the sheet never loads it."""

    __tablename__ = "backstories"
    __table_args__ = (
        CheckConstraint("review in ('none', 'returned', 'resubmitted', 'approved')", name="review"),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), unique=True)
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Goes up with every save: a save names the one it was made from, and is refused
    # if the backstory has changed since.
    version: Mapped[int] = mapped_column(default=0, server_default="0")
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The sections each question set last built, by the set's id: building again
    # replaces them, and a difference shows the player edited them since.
    built: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Where staff's reading of it stands: "none" yet, "returned" to the player with
    # feedback, "resubmitted" by the player, or "approved"; and the troupe whose
    # staff last acted on it.
    review: Mapped[str] = mapped_column(default="none", server_default="none")
    review_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    # The text as it was approved, to show staff what has changed since.
    approved_text: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Its writer's draft, saved as they type and not yet submitted as a version
    # (issue #426); the version it was started from, and when it was last saved.
    # Staff never read it.
    draft_text: Mapped[str | None] = mapped_column(Text)
    draft_version: Mapped[int | None]
    draft_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackstoryFeedback(Record):
    """One line in the thread between a backstory's player and the staff reading it:
    feedback sending it back (overall, or on one section), the player's reply as they
    resubmit, or staff approving it."""

    __tablename__ = "backstory_feedback"
    __table_args__ = (CheckConstraint("kind in ('feedback', 'reply', 'approved')", name="kind"),)

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str]
    # The section's heading the feedback is on; empty for the backstory as a whole.
    section: Mapped[str] = mapped_column(default="", server_default="")
    body: Mapped[str] = mapped_column(Text, default="", server_default="")


QUESTION_KINDS = ("long", "short", "year", "choice", "scale", "heading")


class BackstoryQuestionSet(Record):
    """A troupe's set of backstory questions, such as a Short Form, in order."""

    __tablename__ = "backstory_question_sets"

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    position: Mapped[int]
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackstoryQuestion(Record):
    """One of a troupe's backstory questions (horatio.backstories). Archived rather
    than deleted, so the answers given to it are kept."""

    __tablename__ = "backstory_questions"
    __table_args__ = (CheckConstraint(f"kind in {QUESTION_KINDS}", name="kind"),)

    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backstory_question_sets.id"), index=True)
    position: Mapped[int]
    kind: Mapped[str]
    text: Mapped[str] = mapped_column(Text)
    # The troupe's short title for it, for its section's heading; empty uses the text.
    title: Mapped[str] = mapped_column(default="", server_default="")
    hint: Mapped[str] = mapped_column(Text, default="", server_default="")
    optional: Mapped[bool] = mapped_column(default=False, server_default="false")
    # A choice's options; a scale's two poles.
    options: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # When it is shown (horatio.backstories.shown): null for always.
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackstoryAnswer(Record):
    """A character's answer to one backstory question, saved as the player goes."""

    __tablename__ = "backstory_answers"
    __table_args__ = (UniqueConstraint("character_id", "question_id"),)

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backstory_questions.id"))
    answer: Mapped[str] = mapped_column(Text, default="", server_default="")
