import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Imported, Record


class Character(Imported, Record):
    """A persona a player plays. Belongs to its player, never deleted, only retired."""

    __tablename__ = "characters"
    __table_args__ = (CheckConstraint("status in ('draft', 'active', 'retired')", name="status"),)

    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # The splat's rule set is the one with this splat (rule_sets.splat).
    splat: Mapped[str]
    name: Mapped[str]
    status: Mapped[str] = mapped_column(default="draft", server_default="draft")
    home_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    # The approved sheet. Null until the first approval; a draft has none.
    approved_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sheet_versions.id", use_alter=True)
    )


class CharacterTrait(Record):
    """One trait on the character's sheet as it stands, including unapproved edits."""

    __tablename__ = "character_traits"
    __table_args__ = (
        UniqueConstraint("character_id", "trait_definition_id", "detail"),
        CheckConstraint("free_rating >= 0", name="free_rating_not_negative"),
        CheckConstraint(
            "rating is null and free_rating = 0 or rating >= free_rating",
            name="free_rating_within_rating",
        ),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    trait_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_definitions.id"))
    # Null for traits without a rating, such as a clan.
    rating: Mapped[int | None]
    # Dots the character has without paying XP: from creation, or granted by another trait.
    free_rating: Mapped[int] = mapped_column(default=0, server_default="0")
    # Which one, for traits a character can hold more than once: "Path of Blood".
    detail: Mapped[str] = mapped_column(default="", server_default="")
    note: Mapped[str] = mapped_column(default="", server_default="")


class SheetVersion(Record):
    """One approved sheet, frozen. The approved sheet is the latest."""

    __tablename__ = "sheet_versions"
    __table_args__ = (UniqueConstraint("character_id", "number"),)

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    number: Mapped[int]
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class XpEntry(Record):
    """One line of a character's XP history. Never updated once written."""

    __tablename__ = "xp_entries"
    __table_args__ = (
        CheckConstraint("kind in ('award', 'purchase', 'settlement')", name="kind"),
        CheckConstraint(
            "kind <> 'purchase' or (trait_definition_id is not null"
            " and from_rating is not null and to_rating is not null"
            " and cost_basis is not null)",
            name="purchase_is_complete",
        ),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    kind: Mapped[str]
    # Positive for XP gained, negative for XP spent.
    amount: Mapped[int]
    reason: Mapped[str] = mapped_column(default="", server_default="")
    entered_on: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    entered_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    trait_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trait_definitions.id")
    )
    detail: Mapped[str | None]
    from_rating: Mapped[int | None]
    to_rating: Mapped[int | None]
    # The cost rule that priced a purchase, as it stood at the time.
    cost_basis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
