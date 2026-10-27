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
        CheckConstraint(
            "(kind = 'npc') = (npc_kind is not null and npc_form is not null)", name="npc_has_kind"
        ),
        CheckConstraint("npc_form in ('sheeted', 'stock')", name="npc_form"),
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
    # Its last downtime's answer was half Blood: its next Play View game starts
    # at half (horatio.feeding, horatio.play). Cleared when that game starts.
    half_blood_next_game: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Beast traits a diablerie adds to its next Play View game (horatio.diablerie),
    # which start there and are cleared when that game starts.
    beast_next_game: Mapped[int] = mapped_column(default=0, server_default="0")
    # A ghoul's domitor (horatio.domitors): the vampire PC or NPC it is bound to, or,
    # for one not in Horatio, its name as the player typed it. The domitor's clan and
    # bloodline are the ghoul's clan trait. Both empty for a vampire.
    domitor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"))
    domitor_name: Mapped[str] = mapped_column(default="", server_default="")
    # What an NPC is, by its kind's key (horatio.rules.npc_kinds): "vampire",
    # "werewolf", "custom" and so on; and its form: "sheeted", with a full sheet, or
    # "stock", with only a rating and specializations (horatio.stock_npcs). Both
    # null for a PC.
    npc_kind: Mapped[str | None]
    npc_form: Mapped[str | None]
    # A custom kind as staff set it up for this NPC: {"name", "nature", "resource":
    # {"name", "size", "per_turn", "regains"}}. Null for every other kind.
    npc_custom_kind: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Staff list this NPC on its troupe's Who's Who though it holds no title there
    # (horatio.whos_who). Titled NPCs are listed anyway.
    on_whos_who: Mapped[bool] = mapped_column(default=False, server_default="false")


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
    # For a merit that gives free traits the player chooses (Ventrue Royalty): the
    # choices, as {"grant", "name", "detail", "amount"} each (horatio.rules.grants).
    choices: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # What the player chose when buying a power of this discipline, by the power:
    # {"Shape of the Beast": {"fight": "bear", "template": "Huge"}} (horatio.api.power_choices).
    power_choices: Mapped[dict[str, dict[str, str]]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )


class AppliedHouseTrait(Record):
    """A house merit or flaw staff applied to a character (horatio.house_traits):
    free or charged, whether a free one counts toward the merit limit, and why.
    Only staff remove it; it goes when the trait does."""

    __tablename__ = "applied_house_traits"

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    character_trait_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("character_traits.id", ondelete="CASCADE"), unique=True
    )
    house_trait_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("house_traits.id"), index=True)
    free: Mapped[bool]
    # A free merit counts toward the category's points limit unless staff say not.
    counts_toward_limit: Mapped[bool] = mapped_column(default=True, server_default="true")
    # XP it cost when applied: 0 when free, negative for a charged flaw's XP back.
    cost: Mapped[int] = mapped_column(default=0, server_default="0")
    reason: Mapped[str]
    applied_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


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


class Diablerie(Record):
    """A diablerie on a character's sheet (MET: VTM p. 306): recorded by the home
    troupe's staff, or asked by the player and kept here, unrecorded, while it waits
    on an approval. `outcome` says what recording it did."""

    __tablename__ = "diableries"

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"))
    # The approval a player's request waits on; none for one staff recorded.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approvals.id"), unique=True)
    # The night it happened, as p. 306 asks the sheet to mark.
    committed_on: Mapped[date] = mapped_column(Date)
    # Who was diablerized, as staff write it: for staff only.
    victim: Mapped[str] = mapped_column(default="", server_default="")
    note: Mapped[str] = mapped_column(default="", server_default="")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Who recorded it (or approved it) and when; none while it waits.
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What recording it did: the Generations, Humanity lowered, Beast traits added,
    # techniques lost with their refunds, and what was done about a Lesser
    # Generation or Thin Blooded flaw.
    outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Embrace(Record):
    """A ghoul's Embrace (MET: VTM pp. 297–299), as its home troupe's staff ran it:
    the ghoul became a vampire of its sire's clan, or died in it and was retired.
    `outcome` says what each step did, and the XP it came to."""

    __tablename__ = "embraces"
    __table_args__ = (CheckConstraint("result in ('vampire', 'died')", name="result"),)

    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"), index=True)
    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"))
    # "vampire", or "died" for a character retired in the attempt.
    result: Mapped[str]
    embraced_on: Mapped[date] = mapped_column(Date)
    # The sire: a vampire PC or NPC in Horatio, or one known by name, clan and
    # Generation only. Kept by name if the linked one is deleted.
    sire_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("characters.id"))
    sire_name: Mapped[str] = mapped_column(default="", server_default="")
    sire_clan: Mapped[str] = mapped_column(default="", server_default="")
    # As a number: 10 for the 10th generation.
    sire_generation: Mapped[int | None]
    note: Mapped[str] = mapped_column(default="", server_default="")
    # The Storyteller let the discipline dots the Embrace took be bought back into
    # XP debt (p. 298): in the procedure, or from the cart, up to 2 dots in all.
    buy_back_into_debt: Mapped[bool] = mapped_column(default=False, server_default="false")
    outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


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
        # A reprice is the difference in what a purchase costs when Generation
        # changes before acceptance (horatio.repricing), or at a ghoul's Embrace
        # (horatio.embrace). A debt line is XP debt staff add (negative) or forgive
        # (positive), with their reason (horatio.xp_debt).
        CheckConstraint(
            "kind in ('award', 'purchase', 'settlement', 'fee', 'correction',"
            " 'self_entered', 'cap', 'reprice', 'debt')",
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
        CheckConstraint(
            "kind <> 'reprice' or corrects_id is not null", name="reprice_names_its_purchase"
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
    # (the difference). For a reprice: the purchase it reprices.
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("xp_entries.id"), index=True)
