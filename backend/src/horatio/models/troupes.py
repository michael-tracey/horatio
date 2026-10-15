import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Imported, Record


class Troupe(Imported, Record):
    """The top-level group. Archived rather than deleted."""

    __tablename__ = "troupes"

    name: Mapped[str]
    description: Mapped[str] = mapped_column(default="", server_default="")
    # Not null: every troupe has exactly one lead storyteller, enforced here
    # rather than by counting rows in troupe_staff.
    lead_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Sects whose PCs may join; empty means any.
    allowed_sects: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")


class TroupeStaff(Record):
    """A storyteller, assistant storyteller or narrator. The lead is not listed here."""

    __tablename__ = "troupe_staff"
    __table_args__ = (
        UniqueConstraint("troupe_id", "user_id"),
        CheckConstraint(
            "role in ('storyteller', 'assistant_storyteller', 'narrator')", name="role"
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str]


class TroupeMembership(Record):
    """A character's membership of a troupe. Kept after the character leaves."""

    __tablename__ = "troupe_memberships"
    __table_args__ = (
        # A character can rejoin a troupe, but is only a current member once.
        Index(
            "uq_troupe_memberships_current",
            "troupe_id",
            "character_id",
            unique=True,
            postgresql_where=text("left_at is null"),
        ),
        CheckConstraint("left_at is null or left_at >= joined_at", name="left_after_joined"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The sheet as this troupe accepted it as the character's home troupe. Null for a
    # troupe the character only visits.
    approved_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sheet_versions.id", use_alter=True)
    )


class TroupeSpecialization(Record):
    """An option a troupe offers for one kind of specialisation (an Influence's
    areas, its city's notable Contacts). Where a troupe has a list for a kind,
    its characters choose from it."""

    __tablename__ = "troupe_specializations"
    __table_args__ = (UniqueConstraint("troupe_id", "category_key", "name"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    category_key: Mapped[str]
    name: Mapped[str]


class TroupeTitle(Record):
    """A title a troupe added to the rule set's list."""

    __tablename__ = "troupe_titles"
    __table_args__ = (UniqueConstraint("troupe_id", "name"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]


class CharacterTitle(Record):
    """A title a character holds in one troupe (CONTEXT.md: Title)."""

    __tablename__ = "character_titles"
    __table_args__ = (UniqueConstraint("troupe_id", "character_id", "name"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    name: Mapped[str]
