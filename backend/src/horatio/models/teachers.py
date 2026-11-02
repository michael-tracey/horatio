import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class TeacherRule(Record):
    """A troupe's rule that a kind of trait needs a teacher (horatio.teaching): which
    traits, for whom, when, what the teacher must hold, and what learning costs
    besides the XP (downtime actions, the teacher's Willpower)."""

    __tablename__ = "teacher_rules"
    __table_args__ = (
        CheckConstraint("holds in ('same', 'rating')", name="holds"),
        CheckConstraint("holds = 'same' or rating is not null", name="rating"),
        CheckConstraint("willpower = 0 or games > 0", name="games"),
        CheckConstraint("jsonb_array_length(names) = 0 or name_prefix is null", name="subject"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    splat: Mapped[str] = mapped_column(default="vampire", server_default="vampire")
    # Which traits: a category, and in it these traits or the names starting with a
    # prefix; neither for every trait of the category.
    category: Mapped[str]
    names: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    name_prefix: Mapped[str | None]
    # For whom: a condition in the house checks' vocabulary (horatio.rules.house_checks);
    # null for everyone.
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # When: false (the default) only once creation is finished; true always.
    always: Mapped[bool] = mapped_column(default=False, server_default="false")
    # What the teacher must hold: the same trait at the rating being bought ("same"),
    # or at `rating` ("rating").
    holds: Mapped[str] = mapped_column(default="same", server_default="same")
    rating: Mapped[int | None]
    # Downtime actions learning takes, beside any the rules already ask.
    actions: Mapped[int] = mapped_column(default=0, server_default="0")
    # Willpower the teacher spends, and the games they attend before it returns.
    willpower: Mapped[int] = mapped_column(default=0, server_default="0")
    games: Mapped[int] = mapped_column(default=0, server_default="0")


class Teaching(Record):
    """One purchase a teacher rule asked a teacher for: who teaches it, and the
    teacher's Willpower, from asked to spent (or refused, or given back)."""

    __tablename__ = "teachings"
    __table_args__ = (
        CheckConstraint(
            "status in ('not_needed', 'asked', 'spent', 'refused', 'given_back')", name="status"
        ),
    )

    # The student, and the troupe whose rule it was.
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"))
    # The purchase waiting on the home troupe; null when there was none to wait on.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approvals.id"), unique=True)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teacher_rules.id", ondelete="SET NULL")
    )
    trait_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_definitions.id"))
    detail: Mapped[str] = mapped_column(default="", server_default="")
    rating: Mapped[int]
    # A character in the troupe, or (null) an NPC known only by the name the player gave.
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"), index=True)
    teacher_name: Mapped[str]
    # What the rule asked when it was bought: downtime actions, and the teacher's
    # Willpower and the games before it returns.
    actions: Mapped[int] = mapped_column(default=0, server_default="0")
    willpower: Mapped[int] = mapped_column(default=0, server_default="0")
    games: Mapped[int] = mapped_column(default=0, server_default="0")
    # not_needed (no Willpower, or an NPC known only by name), asked (waiting on the
    # teacher's player), spent, refused, or given_back (the purchase was not made).
    status: Mapped[str] = mapped_column(default="not_needed", server_default="not_needed")
    answered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # When the Willpower was spent, and the Play View game and tap it was spent in.
    spent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    spent_game_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("play_games.id"))
    tap_id: Mapped[uuid.UUID | None]
