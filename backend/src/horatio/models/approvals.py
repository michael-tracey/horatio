import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Approval(Record):
    """A change a player has asked for, waiting on (or decided by) a troupe's
    storytellers or assistant storytellers. One queue for every kind."""

    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("kind in ('sheet_change', 'home_troupe_change')", name="kind"),
        CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'withdrawn')", name="status"
        ),
        # A character has at most one request of each kind waiting at a time.
        Index(
            "uq_approvals_one_pending",
            "character_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'pending'"),
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


class HomeTroupeChange(Record):
    """The details of a home troupe change request."""

    __tablename__ = "home_troupe_changes"

    approval_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("approvals.id"), unique=True)
    # Null for a character's first home troupe.
    from_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    to_troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"))


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
