import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class RuleSet(Record):
    """The generic rules for one splat, loaded from horatio/rules/data/."""

    __tablename__ = "rule_sets"

    key: Mapped[str] = mapped_column(unique=True)
    splat: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    version: Mapped[int]
    starting_xp: Mapped[int] = mapped_column(default=0, server_default="0")
    # Unspent creation XP kept on a first home troupe's acceptance; None keeps all.
    banked_xp: Mapped[int | None]
    # The names of the titles a troupe can give; what those that are more than a
    # name are (sect, status) is in `status_rules`.
    titles: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Sect status beyond the status traits (horatio.rules.status): {caps, sects,
    # social_ages, titles}, as written in the rule set's files.
    status_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # What a sheet may hold (horatio.rules.checks), as written in the rule set file.
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Traits that give other traits (horatio.rules.grants), as written in the files.
    grants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Traits that change feeding between games (horatio.feeding), as in the file.
    feeding_modifiers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # Traits chosen at creation only, as {category, name?, name_prefix?, until?}.
    creation_only: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # Equipment's kinds and grades (horatio.rules.equipment): {kinds, grades}, as
    # written in the rule set's equipment file. Its qualities and sample items are
    # in `equipment_qualities` and `equipment_templates`.
    equipment: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class TraitCategory(Record):
    __tablename__ = "trait_categories"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "key"),
        CheckConstraint("rated or max_rating is null", name="unrated_has_no_max"),
    )

    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"), index=True)
    key: Mapped[str]
    name: Mapped[str]
    group_name: Mapped[str]
    position: Mapped[int]
    rated: Mapped[bool]
    max_rating: Mapped[int | None]
    house_rules_per_trait: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Only allowed when the character has this choice, e.g. {"category": "sect", "name": "Sabbat"}.
    requires: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    # XP to swap this category's choice for another after creation, e.g. a focus.
    change_cost: Mapped[int | None]
    # Most points held in this category (merits), or paid out by it (flaws).
    points_limit: Mapped[int | None]
    # Highest rating usually allowed when buying; grants can raise it.
    usual_max: Mapped[int | None]
    # Traits held in this category besides granted ones (one focus per attribute).
    max_held: Mapped[int | None]
    # Worked out from the rest of the sheet; never bought.
    derived: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Removing an accepted trait costs this many times its points (flaws).
    buy_off_factor: Mapped[int | None]
    # Downtime actions each dot gained after acceptance costs, and what waives it.
    downtime_actions: Mapped[int | None]
    downtime_waived_by: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # What makes each dot cost more actions (horatio.rules.model.CategoryData).
    downtime_added_by: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # For a specialisation category: the skill or background it specialises.
    specializes: Mapped[dict[str, str] | None] = mapped_column(JSONB)


class TraitDefinition(Record):
    """Something a sheet can contain: a skill, merit, discipline, clan…"""

    __tablename__ = "trait_definitions"
    __table_args__ = (
        # A troupe's house merits and flaws are unique among its own; the rule set's
        # (no troupe) among theirs.
        UniqueConstraint("category_id", "name", "troupe_id", postgresql_nulls_not_distinct=True),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_categories.id"), index=True)
    name: Mapped[str]
    # Set for a troupe's house merit or flaw (HouseTrait): only that troupe's
    # characters can hold it. Null for the rule set's own traits.
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    # The trait description (CONTEXT.md).
    description: Mapped[str | None]
    page_reference: Mapped[str | None]
    # Splat-specific data the rules read, such as a clan's in-clan disciplines.
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # No longer in the rule set's files: not offered, but kept for sheets that hold it.
    retired: Mapped[bool] = mapped_column(default=False, server_default="false")


SCHEME_CHECK = "scheme in ('per_dot', 'progressive', 'table', 'fixed', 'free', 'not_allowed')"


class CheckOverride(Record):
    """A troupe's house rule for one check (horatio.rules.checks): a different
    strength, or `off`."""

    __tablename__ = "check_overrides"
    __table_args__ = (
        UniqueConstraint("troupe_id", "check_key"),
        CheckConstraint(
            "strength in ('refuse', 'complete', 'review', 'note', 'off')", name="strength"
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    check_key: Mapped[str]
    strength: Mapped[str]


class CostRule(Record):
    """A cost rule. `troupe_id` null: part of the generic rule set; set: a house rule."""

    __tablename__ = "cost_rules"
    __table_args__ = (
        CheckConstraint(SCHEME_CHECK, name="scheme"),
        CheckConstraint(
            "scheme not in ('per_dot', 'progressive', 'fixed') or rate is not null",
            name="rate_given",
        ),
        CheckConstraint("scheme <> 'table' or cost_table is not null", name="table_given"),
    )

    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_categories.id"))
    trait_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trait_definitions.id")
    )
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    scheme: Mapped[str]
    rate: Mapped[int | None]
    cost_table: Mapped[list[int] | None] = mapped_column(JSONB)
    # A house rule's own wording, shown with the trait description.
    text: Mapped[str | None]


class ActionKind(Record):
    """A category of downtime action. `troupe_id` set: one a troupe added itself."""

    __tablename__ = "action_kinds"
    __table_args__ = (
        # Postgres 15+: a troupe's keys are unique, and so are the generic ones (null troupe).
        UniqueConstraint("rule_set_id", "troupe_id", "key", postgresql_nulls_not_distinct=True),
    )

    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    key: Mapped[str]
    name: Mapped[str]
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # The named actions an action of this kind can be (horatio.influence).
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")


class AllowanceRule(Record):
    """`troupe_id` null: part of the generic rule set; set: a house rule."""

    __tablename__ = "allowance_rules"
    __table_args__ = (CheckConstraint("scheme in ('fixed', 'per_dot')", name="scheme"),)

    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    action_kind: Mapped[str]
    trait_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trait_definitions.id")
    )
    min_rating: Mapped[int] = mapped_column(default=1, server_default="1")
    scheme: Mapped[str]
    amount: Mapped[int]
    # What it means, shown on the character's downtime (Hunted's actions).
    note: Mapped[str] = mapped_column(default="", server_default="")


class CreationRule(Record):
    """`troupe_id` null: part of the generic rule set; set: a house rule. A
    troupe's creation rules for a category replace all the generic ones for it."""

    __tablename__ = "creation_rules"
    __table_args__ = (
        CheckConstraint(
            "(points is null and rating > 0 and picks > 0)"
            " or (points > 0 and rating is null and picks is null)",
            name="picks_or_points",
        ),
    )

    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_categories.id"))
    rating: Mapped[int | None]
    picks: Mapped[int | None]
    points: Mapped[int | None]
    # A splat fact the trait must have to take a pick, such as "in_clan".
    restriction: Mapped[str | None]
    # Only while the sheet meets this condition (horatio.rules.checks).
    when: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class StartingTrait(Record):
    """A trait every new character starts with, free."""

    __tablename__ = "starting_traits"

    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    trait_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_definitions.id"))
    rating: Mapped[int | None]


class ClanLogo(Record):
    """A clan's or bloodline's logo, which the custodian uploads (horatio.pictures):
    the official symbols are the publisher's and cannot ship with Horatio."""

    __tablename__ = "clan_logos"
    __table_args__ = (UniqueConstraint("splat", "clan"),)

    splat: Mapped[str]
    # The clan trait's name, such as "Toreador" or "Brujah: True Brujah".
    clan: Mapped[str]
    # The id its files are kept under, new with each upload.
    image_id: Mapped[uuid.UUID]
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class HouseTrait(Record):
    """A merit or flaw a troupe made itself (horatio.house_traits). Sheets and
    purchases hold it through its own trait definition, which it keeps in step."""

    __tablename__ = "house_traits"
    __table_args__ = (
        UniqueConstraint("troupe_id", "splat", "category", "name"),
        CheckConstraint("category in ('merits', 'flaws')", name="category"),
        CheckConstraint("points between 1 and 7", name="points"),
        CheckConstraint("kind in ('General', 'Clan', 'Sabbat')", name="kind"),
        CheckConstraint("availability in ('staff', 'building')", name="availability"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    splat: Mapped[str] = mapped_column(default="vampire", server_default="vampire")
    category: Mapped[str]
    name: Mapped[str]
    points: Mapped[int]
    # Its catalogue type, for the merit limit and the filters.
    kind: Mapped[str] = mapped_column(default="General", server_default="General")
    # "staff": only staff apply it; "building": characters built for the troupe can
    # take it, as they would a merit from the book.
    availability: Mapped[str]
    creation_only: Mapped[bool] = mapped_column(default=False, server_default="false")
    description: Mapped[str] = mapped_column(default="", server_default="")
    requirement: Mapped[str] = mapped_column(default="", server_default="")
    # What it does on the sheet and in play, as blocks each naming the engine kind
    # it maps to ({"kind": "free_up_to", ...}), checked as the rules files are.
    # Empty: description only, for the storytellers to rule on at the table.
    effects: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Archived: no new picks; those who hold it keep it.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trait_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trait_definitions.id"), unique=True
    )


EQUIPMENT_KIND_CHECK = "kind in ('melee', 'ranged', 'protective', 'miscellaneous')"


class EquipmentQuality(Record):
    """A quality an item of one kind can have (horatio.rules.equipment), loaded from
    the rule set's equipment file. Never deleted, like a trait definition: one the
    file no longer has is retired."""

    __tablename__ = "equipment_qualities"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "kind", "name"),
        CheckConstraint(EQUIPMENT_KIND_CHECK, name="kind"),
    )

    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"), index=True)
    kind: Mapped[str]
    name: Mapped[str]
    # What it does, in a line of our own words.
    effect: Mapped[str]
    # What it does at the table, in a few words, for the Play View.
    play: Mapped[str] = mapped_column(default="", server_default="")
    page: Mapped[str | None]
    # What it does to an item (two_handed, excludes, shots...), as in the file.
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Its place in the file, to list them in the book's order.
    position: Mapped[int]
    retired: Mapped[bool] = mapped_column(default=False, server_default="false")


class EquipmentTemplate(Record):
    """An item to start one from: the book's sample items (troupe null), and a
    troupe's own (horatio.equipment), saved under the rule set it was checked by."""

    __tablename__ = "equipment_templates"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "troupe_id", "name", postgresql_nulls_not_distinct=True),
        CheckConstraint(EQUIPMENT_KIND_CHECK, name="kind"),
        CheckConstraint("grade in ('cheap', 'standard', 'special')", name="grade"),
    )

    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rule_sets.id"), index=True)
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    kind: Mapped[str]
    grade: Mapped[str]
    # Each {name, detail?}.
    qualities: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    page: Mapped[str | None]
    position: Mapped[int] = mapped_column(default=0, server_default="0")
    # A troupe's own template keeps the rest of the item it was saved from.
    crafted: Mapped[bool] = mapped_column(default=False, server_default="false")
    # An archaic ranged weapon (a bow, a crossbow) may shoot with Athletics instead
    # of Firearms (MET: VTM p. 279).
    archaic: Mapped[bool] = mapped_column(default=False, server_default="false")
    # A special item's own effects: each {name, effect}.
    effects: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list, server_default="[]")
    description: Mapped[str] = mapped_column(default="", server_default="")
