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
    __table_args__ = (
        CheckConstraint("status in ('active', 'retired')", name="status"),
        CheckConstraint("kind in ('pc', 'npc')", name="kind"),
        CheckConstraint("(kind = 'npc') = (owner_troupe_id is not null)", name="npc_has_troupe"),
    )

    # For a PC, its player. For an NPC, the staff member who made it; the NPC
    # itself belongs to its troupe.
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(default="pc", server_default="pc")
    # The troupe an NPC belongs to (CONTEXT.md: NPC). Null for a PC.
    owner_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    # The splat's rule set is the one with this splat (rule_sets.splat).
    splat: Mapped[str]
    name: Mapped[str]
    # active | retired. Accepted once a troupe accepts it as home (home_troupe_id).
    status: Mapped[str] = mapped_column(default="active", server_default="active")
    home_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    # Until a home troupe accepts it, the troupe it is built for: its rules (house
    # rules, specialisation lists) apply. None builds by the plain rule set.
    building_troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"))
    # Null while the player is still placing creation picks (CONTEXT.md: Character Creation).
    creation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When its player last renamed it while it was in a troupe: their three months
    # until the next rename run from here (horatio/renames.py). Custodian renames,
    # and renames before any troupe had the character, leave it alone.
    renamed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The primary path the player named, by discipline, where the clan has no
    # in-clan path: {"Thaumaturgy": "Thaumaturgy: Path of Corruption"}.
    primary_paths: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")
    # The character's picture (horatio.pictures): the id its files are kept under,
    # new with each upload or crop so no cache shows an old one; null for none.
    picture_id: Mapped[uuid.UUID | None]
    # Where the square portrait sits in the picture, as fractions:
    # {"x": left, "y": top, "size": side, of the picture's width and height}.
    picture_crop: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    # Who uploaded the picture and when: they are told if someone else removes it.
    picture_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    picture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What others can see or sense about the character that the rules data does not
    # cover, written by staff, for the character's game badge.
    visible_note: Mapped[str] = mapped_column(default="", server_default="")


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
        CheckConstraint(
            "creation_pick is null or creation_pick <= free_rating", name="pick_is_free"
        ),
    )

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    trait_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_definitions.id"))
    # Null for traits without a rating, such as a clan.
    rating: Mapped[int | None]
    # Dots the character has without paying XP: from creation, or granted by another trait.
    free_rating: Mapped[int] = mapped_column(default=0, server_default="0")
    # The part of the rating (and of free_rating) that grants from other traits
    # give, such as Rugged's extra health level; negative for a flaw that takes
    # dots away. Undone exactly when the granting trait goes.
    granted_rating: Mapped[int] = mapped_column(default=0, server_default="0")
    # The creation pick placed on this trait: the pick's rating, or for a points
    # budget (merits, flaws) the points it used. Null for no pick.
    creation_pick: Mapped[int | None]
    # Which one, for traits a character can hold more than once: "Path of Blood".
    detail: Mapped[str] = mapped_column(default="", server_default="")
    note: Mapped[str] = mapped_column(default="", server_default="")


class TraitException(Record):
    """A trait held by exception (horatio.trait_exceptions): asked of the home
    troupe's staff from the cart, or given by them. It sets aside the checks it
    names for that one trait, up to the rating it was given at, and goes when the
    trait does."""

    __tablename__ = "trait_exceptions"

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    character_trait_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("character_traits.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int]
    # The checks it sets aside, as {"key", "message"}: each as it read when the
    # exception was asked for or given.
    checks: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Given at no XP cost: the dots are free dots.
    free: Mapped[bool] = mapped_column(default=False, server_default="false")
    # What the dots cost at the normal price when asked for, if they have one.
    normal_cost: Mapped[int | None]
    reason: Mapped[str]
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # The approval an asked-for exception waits on; none for one staff gave.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approvals.id"), unique=True)
    # Who gave it or approved it, and when; none while it waits.
    given_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SheetVersion(Record):
    """One sheet as one troupe approved it, frozen. That troupe's approved sheet is its latest."""

    __tablename__ = "sheet_versions"
    __table_args__ = (UniqueConstraint("character_id", "troupe_id", "number"),)

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    number: Mapped[int]
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class XpEntry(Record):
    """One line of a character's XP history. Never updated once written: a mistaken
    award is put right by a correction, a later entry naming it."""

    __tablename__ = "xp_entries"
    __table_args__ = (
        # A fee is XP spent on something other than dots, such as changing a focus.
        # A self-entered entry is XP a player added to a character with no home
        # troupe; a cap is XP above a troupe's ceiling taken away as it became home.
        CheckConstraint(
            "kind in ('award', 'purchase', 'settlement', 'fee', 'correction',"
            " 'self_entered', 'cap')",
            name="kind",
        ),
        CheckConstraint(
            "kind <> 'purchase' or (trait_definition_id is not null"
            " and from_rating is not null and to_rating is not null"
            " and cost_basis is not null)",
            name="purchase_is_complete",
        ),
        CheckConstraint(
            "kind <> 'settlement' or reconciliation_item_id is not null",
            name="settlement_names_its_difference",
        ),
        CheckConstraint(
            "kind <> 'correction' or corrects_id is not null", name="correction_names_its_award"
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
    # For a settlement: the reconciliation difference it settles.
    reconciliation_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reconciliation_items.id")
    )
    # For a correction: the award (or self-entered entry) it corrects, by `amount`
    # (the difference).
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("xp_entries.id"), index=True)
