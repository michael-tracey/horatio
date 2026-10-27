"""The rules as plain values, independent of how they are stored.

A `RuleSetData` is the generic rules for one splat. `TroupeRules` is a rule set
with one troupe's house rules applied (CONTEXT.md: Troupe Rules); a character
with no home troupe plays by a `TroupeRules` with no house rules.
"""

import uuid
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, Literal, TypeVar, get_args

from horatio.rules.equipment import NO_EQUIPMENT, EquipmentRules
from horatio.rules.status import (
    NO_STATUS_RULES,
    StatusData,
    StatusRulesData,
    TitleData,
    statuses_of,
)

if TYPE_CHECKING:
    from horatio.rules.checks import CheckData
    from horatio.rules.grants import GrantData

Scheme = Literal["per_dot", "progressive", "table", "fixed", "free", "not_allowed"]
SCHEMES: tuple[str, ...] = get_args(Scheme)

DEFAULT_MAX_RATING = 20

T = TypeVar("T")
# Answers a rule set remembers before it forgets them all and starts again.
MEMO_SIZE = 512


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
    # Only shown and allowed when the character has this choice, for example
    # {"category": "sect", "name": "Sabbat"} for faction.
    requires: Mapping[str, str] | None = None
    # XP to swap the choice in this category for another after creation, such
    # as a focus (10 XP); None when it cannot be swapped that way.
    change_cost: int | None = None
    # The most points a character can hold in this category (merits), or for a
    # category that pays XP back (flaws), the most it pays out.
    points_limit: int | None = None
    # The highest rating usually allowed when buying (skills 5); grants can raise
    # it. `max_rating` stays the hard ceiling.
    usual_max: int | None = None
    # How many traits a character holds in this category, besides any granted
    # (one focus per attribute).
    max_held: int | None = None
    # Worked out from the rest of the sheet (health, Willpower); not bought.
    derived: bool = False
    # Removing an accepted trait costs this many times its points (flaws: 2).
    buy_off_factor: int | None = None
    # Downtime actions each dot gained after acceptance costs (learning a
    # discipline, buying a merit), unless the sheet holds a trait that waives it.
    downtime_actions: int | None = None
    downtime_waived_by: Sequence[Mapping[str, str]] = ()
    # For a specialisation category: the skill or background it specialises,
    # as {category, name}.
    specializes: Mapping[str, str] | None = None


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
    # Extra inputs an action of this kind asks for, such as an influence's
    # specialisation.
    fields: tuple[Mapping[str, Any], ...] = ()
    # The named actions an action of this kind can be, such as "5: Lockdown" for
    # Underworld influence (horatio.influence): {key, name, level?, conflict?}.
    actions: tuple[Mapping[str, Any], ...] = ()
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
class FeedingModifierData:
    """How a trait changes what a character must do to feed between games
    (horatio.feeding): `amount` more feeding actions needed, how much each dot
    of Herd counts for (0 for none, 2 for double), or always half Blood."""

    category: str
    trait: str
    amount: int = 0
    herd_factor: int = 1
    always_half: bool = False
    page: str | None = None


@dataclass(frozen=True)
class CreationRuleData:
    """What a new character gets free in a category (CONTEXT.md: Creation Rule):
    `picks` picks at `rating`, or a budget of `points` (merits and flaws)."""

    category: str
    rating: int | None = None
    picks: int | None = None
    points: int | None = None
    # A splat fact a trait must have to take one of these picks, such as "in_clan".
    restriction: str | None = None
    house: bool = False
    # Only while the sheet meets this condition (horatio.rules.checks): Thin
    # Blooded vampires get no 2-dot discipline pick.
    when: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class StartingTraitData:
    """A trait every new character starts with, free (CONTEXT.md: Starting Trait)."""

    category: str
    name: str
    rating: int | None
    house: bool = False


@dataclass(frozen=True)
class HouseTraitData:
    """A merit or flaw a troupe made itself (horatio.house_traits). Its troupe's
    rules hold it in `RuleSetData.traits` like a merit from the book, with this
    beside it saying whose it is and who can take it."""

    id: uuid.UUID
    troupe_id: uuid.UUID
    troupe_name: str
    category: str
    name: str
    points: int
    kind: str
    # "staff": only staff apply it; "building": a character built for the troupe
    # can take it.
    availability: Literal["staff", "building"]
    creation_only: bool = False
    archived: bool = False
    description: str = ""
    requirement: str = ""
    # Its effect blocks, as stored (horatio.rules.house_effects); none for one that
    # does only what its description says.
    effects: tuple[Mapping[str, Any], ...] = ()
    # What the blocks do, in words, and the disciplines one lets the character add
    # in-clan: worked out when the troupe's rules are read.
    summary: str = ""
    in_clan: tuple[str, ...] = ()

    @property
    def offered(self) -> bool:
        """Whether a player can take it, rather than only staff apply it."""
        return self.availability == "building" and not self.archived

    @property
    def label(self) -> str:
        """How it is marked wherever it shows: "House merit of Night Court"."""
        return house_label(self.category, self.troupe_name)


def house_label(category: str, troupe_name: str) -> str:
    noun = "House flaw" if category == "flaws" else "House merit"
    return f"{noun} of {troupe_name}"


def house_page(troupe_name: str) -> str:
    """A house trait's page reference, where a book trait's page would be."""
    return f"House rule — {troupe_name}"


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
    # Traits that change how much a character must feed between games.
    feeding_modifiers: Sequence[FeedingModifierData] = ()
    creation_rules: Sequence[CreationRuleData] = ()
    starting_traits: Sequence[StartingTraitData] = ()
    # Titles a troupe can give (CONTEXT.md: Title), each with its sect and the status
    # it gives (horatio.rules.status); troupes can add their own.
    titles: Sequence[TitleData] = ()
    # Each sect's Accepted and status bans, the status of social age, and the status
    # caps (horatio.rules.status). The statuses themselves are traits.
    status_rules: StatusRulesData = NO_STATUS_RULES
    # What a sheet may hold (horatio.rules.checks).
    checks: Sequence["CheckData"] = ()
    # Traits that give other traits (horatio.rules.grants).
    grants: Sequence["GrantData"] = ()
    # Traits chosen at creation only: {category, name?, name_prefix?, until?} each.
    # They lock when creation is finished, or with until = "accepted" when a first
    # home troupe accepts the character.
    creation_only: Sequence[Mapping[str, str]] = ()
    # Unspent creation XP kept when a first home troupe accepts the character;
    # None keeps it all.
    banked_xp: int | None = None
    # Equipment's kinds, grades, qualities and sample items (horatio.rules.equipment).
    equipment: EquipmentRules = NO_EQUIPMENT

    @cached_property
    def memo(self) -> dict[Hashable, Any]:
        """Answers worked out from these rules and a sheet (see `remembered`)."""
        return {}

    def remembered(self, key: Hashable, work_out: Callable[[], T]) -> T:
        """The answer for `key`, worked out once and kept as long as these rules
        are (a database session): what a sheet's grants price, say, which judging
        a category asks again for every trait in it. Only for answers that are
        plain values, as every caller gets the same one."""
        if key not in self.memo:
            if len(self.memo) >= MEMO_SIZE:
                self.memo.clear()
            self.memo[key] = work_out()
        return self.memo[key]

    @cached_property
    def kinds(self) -> Mapping[tuple[str, str], str]:
        """Each trait's catalogue type ("Clan", "General"…), for checks that ask."""
        return {k: t.properties["type"] for k, t in self.traits.items() if "type" in t.properties}

    @cached_property
    def tags(self) -> Mapping[tuple[str, str], frozenset[str]]:
        """Each trait's catalogue tags ("vampire_only"), for checks that ask."""
        return {
            k: frozenset(t.properties["tags"])
            for k, t in self.traits.items()
            if "tags" in t.properties
        }

    @cached_property
    def statuses(self) -> Mapping[str, StatusData]:
        """Each status trait, by name, with what it does (horatio.rules.status)."""
        return statuses_of(self.traits)

    @cached_property
    def titles_by_name(self) -> Mapping[str, TitleData]:
        return {t.name: t for t in self.titles}

    def trait_properties(self, category: str, name: str) -> Mapping[str, Any]:
        trait = self.traits.get((category, name))
        return trait.properties if trait else {}


@dataclass(frozen=True)
class TroupeRules:
    rule_set: RuleSetData
    house_rules: Sequence[CostRuleData] = ()
    house_action_kinds: Sequence[ActionKindData] = ()
    house_allowance_rules: Sequence[AllowanceRuleData] = ()
    house_creation_rules: Sequence[CreationRuleData] = ()
    house_starting_traits: Sequence[StartingTraitData] = ()
    # Check key to its house strength ("off" drops the check).
    check_overrides: Mapping[str, str] = field(default_factory=dict)
    # The troupe's own merits and flaws, also in `rule_set.traits` (and, for those
    # chosen at creation only, in `rule_set.creation_only`), their effects' grants
    # and checks in `rule_set.grants` and `rule_set.checks`.
    house_traits: Sequence[HouseTraitData] = ()
    # The rule set as it is without the house traits' effects, for trying a change
    # to one (horatio.house_traits.preview). None where there are none.
    unmerged: RuleSetData | None = None

    @property
    def splat(self) -> str:
        return self.rule_set.splat

    def house_trait(self, category: str, name: str) -> HouseTraitData | None:
        """The troupe's own merit or flaw of that name, if it is one."""
        return self.house_by_key.get((category, name))

    @cached_property
    def house_by_key(self) -> Mapping[tuple[str, str], HouseTraitData]:
        return {(t.category, t.name): t for t in self.house_traits}

    def checks(self) -> list["CheckData"]:
        """The rule set's checks with the troupe's house strengths applied."""
        from dataclasses import replace

        found: list[CheckData] = []
        for check in self.rule_set.checks:
            strength = self.check_overrides.get(check.key)
            if strength == "off":
                continue
            found.append(replace(check, strength=strength) if strength else check)  # type: ignore[arg-type]
        return found

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

    def creation_rules(self) -> list[CreationRuleData]:
        """The generic creation rules, except that a troupe with house rules for a
        category replaces all the generic rules for that category."""
        house_categories = {r.category for r in self.house_creation_rules}
        generic = [r for r in self.rule_set.creation_rules if r.category not in house_categories]
        return generic + list(self.house_creation_rules)

    def fixed_rating(self, category: str, name: str) -> int | None:
        """The rating a merit or flaw is always held at, or None for a trait bought
        dot by dot: the troupe's fixed price for it with no condition, else the
        catalogue's rating. For one character, `pricing.fixed_rating` says which
        price applies to them."""
        fixed = self.rule_set.trait_properties(category, name).get("rating")
        if fixed is None:
            return None
        for rule in self.house_rules:
            if (
                rule.category == category
                and rule.trait == name
                and not rule.condition
                and rule.scheme == "fixed"
                and rule.rate
            ):
                return abs(rule.rate)
        return fixed

    def starting_traits(self) -> list[StartingTraitData]:
        house = {(t.category, t.name): t for t in self.house_starting_traits}
        traits = [house.pop((t.category, t.name), t) for t in self.rule_set.starting_traits]
        return traits + list(house.values())


@dataclass(frozen=True)
class FreeChoice:
    """One of the free traits a player chose for a merit that gives them
    (horatio.rules.grants, kind free_choices): which grant it answers, the trait's
    name and detail, and for dots the amount placed on it. A merit that opens a
    power past a check (kind open_barred) keeps the power the same way, with its
    category and the price it was opened at as the amount."""

    grant: str
    name: str
    detail: str = ""
    amount: int = 0
    category: str = ""


@dataclass(frozen=True)
class SheetTrait:
    """One trait on a character's sheet, as the rules see it."""

    category: str
    name: str
    rating: int | None = None
    free_rating: int = 0
    detail: str = ""
    # Dots another trait's grant gives it (horatio.rules.grants).
    granted_rating: int = 0
    # The free traits the player chose for it, if it gives some.
    choices: tuple[FreeChoice, ...] = ()

    @property
    def granted(self) -> bool:
        """Held only because another trait gives it, as Extrasensory Perceptions
        gives Acute Sense: not bought, so not counted as a copy or a clan merit."""
        return self.granted_rating > 0 and self.granted_rating >= (self.rating or 0)

    @property
    def full_name(self) -> str:
        """The name with its detail, as Yorick wrote it: "Thaumaturgy: Path of Blood"."""
        return f"{self.name}: {self.detail}" if self.detail else self.name
