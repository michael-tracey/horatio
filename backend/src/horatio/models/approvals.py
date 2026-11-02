import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Approval(Record):
    """Something waiting on (or decided by) a troupe's storytellers or assistant
    storytellers: a home troupe change, a discipline dot bought in the home
    troupe, a change held for review, a trait asked for by exception, a
    diablerie a player says they committed, or a merit or flaw added or removed
    once the character is accepted (horatio.merit_requests). One queue for every
    kind. `sheet_change` is kept only for history."""

    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "kind in ('sheet_change', 'home_troupe_change', 'discipline', 'review',"
            " 'exception', 'diablerie', 'merit_flaw')",
            name="kind",
        ),
        CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'withdrawn')", name="status"
        ),
        # A character has at most one home troupe request waiting in each troupe;
        # dots held for approval, and merit and flaw changes, each wait on their own.
        Index(
            "uq_approvals_one_pending",
            "character_id",
            "troupe_id",
            "kind",
            unique=True,
            postgresql_where=text(
                "status = 'pending'"
                " and kind not in ('discipline', 'review', 'exception', 'merit_flaw')"
            ),
        ),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    # The troupe whose staff decide.
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending", server_default="pending")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    player_note: Mapped[str] = mapped_column(default="", server_default="")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staff_note: Mapped[str] = mapped_column(default="", server_default="")
    # The quest staff answered it with (horatio.merit_requests): completing it
    # approves the request, failing or closing it declines it.
    quest_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quests.id", ondelete="SET NULL"), index=True
    )


class DisciplinePurchase(Record):
    """The dots of a discipline bought in the home troupe, held until its staff decide;
    also the dots of a change held for review or asked for by exception, and a merit
    or flaw asked to be added or removed (which is not on the sheet until approved).
    The XP is spent when bought and refunded if they decline."""

    __tablename__ = "discipline_purchases"

    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approvals.id"), unique=True)
    trait_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_definitions.id"))
    detail: Mapped[str] = mapped_column(default="", server_default="")
    from_rating: Mapped[int]
    to_rating: Mapped[int]
    cost: Mapped[int]
    # Who teaches it, as the player says: out-of-clan powers need a teacher (p. 112).
    teacher: Mapped[str] = mapped_column(default="", server_default="")
    # For a merit asked for: the free traits its player chose with it, given when
    # it is approved ([{grant, name, detail, amount}]).
    choices: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # A free change (horatio.free_changes): a trait lowered or removed while the
    # character's free changes were open, refunding its full XP.
    free_change: Mapped[bool] = mapped_column(default=False, server_default="false")


class HomeTroupeChange(Record):
    """The details of a home troupe change request."""

    __tablename__ = "home_troupe_changes"

    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approvals.id"), unique=True)
    # Null for a character's first home troupe.
    from_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    to_troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"))
    # The player's choice: below the new troupe's XP floor, top the character up to it.
    top_up: Mapped[bool] = mapped_column(default=True, server_default="true")
    # Once decided, the character's XP against the troupe's floor and ceiling and
    # what staff did about it (horatio.xp_range.Review), for the record.
    xp_review: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


SETTLEMENTS = (
    "keep_price",
    "pay_difference",
    "refund_difference",
    "remove_and_refund",
    # Starting-dot differences:
    "pay_for_dots",
    "remove_dots",
    "add_free_dots",
)


class ReconciliationItem(Record):
    """One difference between what a character paid for a trait and what the new
    home troupe's rules charge for it, and how it is settled."""

    __tablename__ = "reconciliation_items"
    __table_args__ = (
        CheckConstraint(
            "difference in ('cost_differs', 'not_allowed', 'creation_differs')", name="difference"
        ),
        CheckConstraint(f"proposed_settlement in {SETTLEMENTS}", name="proposed_settlement"),
        CheckConstraint(f"settlement is null or settlement in {SETTLEMENTS}", name="settlement"),
    )

    home_troupe_change_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("home_troupe_changes.id"), index=True
    )
    # Null for a difference about a whole creation pool, such as extra picks.
    trait_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trait_definitions.id")
    )
    detail: Mapped[str] = mapped_column(default="", server_default="")
    difference: Mapped[str]
    # For creation differences: the category and pick rating (0 for a points budget).
    pool_category: Mapped[str | None]
    pool_rating: Mapped[int | None]
    rating: Mapped[int]
    # XP the character paid for the trait, and what the new rules charge (null if not allowed).
    old_cost: Mapped[int]
    new_cost: Mapped[int | None]
    proposed_settlement: Mapped[str]
    # Set when the request is decided: the staff's final choice.
    settlement: Mapped[str | None]
    xp_delta: Mapped[int | None]
