import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
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
    titles: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # What a sheet may hold (horatio.rules.checks), as written in the rule set file.
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Traits that give other traits (horatio.rules.grants), as written in the files.
    grants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Traits chosen at creation only, as {category, name?, name_prefix?}.
    creation_only: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )


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
    # For a specialisation category: the skill or background it specialises.
    specializes: Mapped[dict[str, str] | None] = mapped_column(JSONB)


class TraitDefinition(Record):
    """Something a sheet can contain: a skill, merit, discipline, clan…"""

    __tablename__ = "trait_definitions"
    __table_args__ = (UniqueConstraint("category_id", "name"),)

    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trait_categories.id"), index=True)
    name: Mapped[str]
    # The trait description (CONTEXT.md).
    description: Mapped[str | None]
    page_reference: Mapped[str | None]
    # Splat-specific data the rules read, such as a clan's in-clan disciplines.
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


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
