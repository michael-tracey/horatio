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
