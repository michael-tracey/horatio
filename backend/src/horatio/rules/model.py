"""The rules as plain values, independent of how they are stored.

A `RuleSetData` is the generic rules for one splat. `TroupeRules` is a rule set
with one troupe's house rules applied (CONTEXT.md: Troupe Rules); a character
with no home troupe plays by a `TroupeRules` with no house rules.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

Scheme = Literal["per_dot", "progressive", "table", "fixed", "free", "not_allowed"]
SCHEMES: tuple[str, ...] = get_args(Scheme)

DEFAULT_MAX_RATING = 20


@dataclass(frozen=True)
class CategoryData:
    key: str
    name: str
    group: str
    rated: bool = True
    max_rating: int | None = DEFAULT_MAX_RATING
    # Merits and flaws: a troupe re-prices them one trait at a time, never the
    # whole category (docs/design/schema.md, decision 5).
    house_rules_per_trait: bool = False


@dataclass(frozen=True)
class CostRuleData:
    category: str
    scheme: Scheme
    trait: str | None = None
    condition: Mapping[str, Any] | None = None
    rate: int | None = None
    table: tuple[int, ...] | None = None
    text: str | None = None
    # True for a troupe's house rule, False for the generic rule set.
    house: bool = False

    def describe(self) -> dict[str, Any]:
        """What a purchase records as its cost basis."""
        basis: dict[str, Any] = {"category": self.category, "scheme": self.scheme}
        for name in ("trait", "condition", "rate", "text"):
            value = getattr(self, name)
            if value is not None:
                basis[name] = value
        if self.table is not None:
            basis["table"] = list(self.table)
        basis["house_rule"] = self.house
        return basis


@dataclass(frozen=True)
class TraitData:
    category: str
    name: str
    description: str | None = None
    page_reference: str | None = None
    # For example a clan's in-clan disciplines, or a merit's fixed rating.
    properties: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionKindData:
    """A category of downtime action (CONTEXT.md: Action Kind)."""

    key: str
    name: str
    # Extra inputs an action of this kind asks for, such as an influence level.
    fields: tuple[Mapping[str, Any], ...] = ()
    # True for an action kind a troupe added itself.
    house: bool = False


AllowanceScheme = Literal["fixed", "per_dot"]


@dataclass(frozen=True)
class AllowanceRuleData:
    """How a trait adds to (or takes from) a character's action allowance. With
    no trait, the base allowance everyone gets (CONTEXT.md: Allowance Rule)."""

    action_kind: str
    scheme: AllowanceScheme
    amount: int
    category: str | None = None
    trait: str | None = None
    min_rating: int = 1
    house: bool = False

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        """A house rule with the same key replaces the generic rule."""
        return (self.action_kind, self.category, self.trait)


@dataclass(frozen=True)
class RuleSetData:
    key: str
    splat: str
    name: str
    version: int
    starting_xp: int
    categories: Mapping[str, CategoryData]
    cost_rules: Sequence[CostRuleData]
    traits: Mapping[tuple[str, str], TraitData]
    action_kinds: Mapping[str, ActionKindData] = field(default_factory=dict)
    allowance_rules: Sequence[AllowanceRuleData] = ()

    def trait_properties(self, category: str, name: str) -> Mapping[str, Any]:
        trait = self.traits.get((category, name))
        return trait.properties if trait else {}


@dataclass(frozen=True)
class TroupeRules:
    rule_set: RuleSetData
    house_rules: Sequence[CostRuleData] = ()
    house_action_kinds: Sequence[ActionKindData] = ()
    house_allowance_rules: Sequence[AllowanceRuleData] = ()

    @property
    def splat(self) -> str:
        return self.rule_set.splat

    def action_kinds(self) -> dict[str, ActionKindData]:
        kinds = dict(self.rule_set.action_kinds)
        kinds.update({k.key: k for k in self.house_action_kinds})
        return kinds

    def allowance_rules(self) -> list[AllowanceRuleData]:
        """The generic allowance rules, each replaced by a house rule with the same
        key where the troupe has one, plus the troupe's own additions."""
        house = {r.key: r for r in self.house_allowance_rules}
        rules = [house.pop(r.key, r) for r in self.rule_set.allowance_rules]
        return rules + list(house.values())


@dataclass(frozen=True)
class SheetTrait:
    """One trait on a character's sheet, as the rules see it."""

    category: str
    name: str
    rating: int | None = None
    free_rating: int = 0
    detail: str = ""

    @property
    def full_name(self) -> str:
        """The name with its detail, as Yorick wrote it: "Thaumaturgy: Path of Blood"."""
        return f"{self.name}: {self.detail}" if self.detail else self.name
