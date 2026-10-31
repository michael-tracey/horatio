"""What traits cost under a troupe's rules.

The cost of a trait at a rating is the price of that rating less the price of
its free rating, the part the character did not pay for. A purchase costs the
difference between the trait's cost after and before.

Choosing the cost rule: house rules and generic rules compete together, and
the most specific one wins. A rule naming the trait beats a whole category,
and a rule testing more facts beats one testing fewer; a house rule wins a
tie. So a troupe re-pricing all merits leaves a generic price for one merit
alone, and a troupe replaces a generic rule by giving the same trait and
condition its own price. Two rules left tied is a mistake in the rules, and
is refused rather than guessed at.

A power a merit opens past its Generation (horatio.rules.grants, open_barred) costs
the merit's price instead, whatever the cost rules say: Hard as Steel's Fortitude
elder power, 20 XP, for a Neonate the rules would not sell one to.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from horatio.rules.conditions import clause_count, holds
from horatio.rules.grants import Opening, matching, opening, priced
from horatio.rules.model import CostRuleData, SheetTrait, TroupeRules
from horatio.rules.splats import SPLATS


class PricingError(Exception):
    """A trait could not be priced. Never treated as free."""


class UnknownCategory(PricingError):
    pass


class NoCostRule(PricingError):
    pass


class AmbiguousCostRule(PricingError):
    pass


class NotAllowed(PricingError):
    pass


class RatingOutOfRange(PricingError):
    pass


@dataclass(frozen=True)
class Quote:
    """A price, and the rule that set it, for a purchase to record."""

    cost: int
    rule: CostRuleData
    # The merit that opened the trait and set its price, where one did.
    opening: Opening | None = None


def choose_rule(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> CostRuleData:
    facts = SPLATS[rules.splat].facts(rules, sheet, trait)

    def applies(rule: CostRuleData) -> bool:
        return (
            rule.category == trait.category
            and rule.trait in (None, trait.name)
            and holds(rule.condition, facts)
        )

    matching = [r for r in [*rules.house_rules, *rules.rule_set.cost_rules] if applies(r)]
    if not matching:
        raise NoCostRule(f"no cost rule for {trait.category} {trait.name!r}")

    def specificity(rule: CostRuleData) -> tuple[bool, int, bool]:
        return (rule.trait is not None, clause_count(rule.condition), rule.house)

    best = max(specificity(r) for r in matching)
    chosen = [r for r in matching if specificity(r) == best]
    if len(chosen) > 1:
        raise AmbiguousCostRule(
            f"{len(chosen)} equally specific cost rules for {trait.category} {trait.name!r}"
        )
    return chosen[0]


def price(rule: CostRuleData, rating: int) -> int:
    """The full price of `rating` dots under one rule."""
    if rating == 0 or rule.scheme == "free":
        return 0
    if rule.scheme == "not_allowed":
        raise NotAllowed(f"{rule.category} {rule.trait or ''} cannot be bought".replace("  ", " "))
    if rule.scheme == "table":
        assert rule.table is not None
        if rating > len(rule.table):
            raise RatingOutOfRange(f"the cost table stops at {len(rule.table)}")
        return sum(rule.table[:rating])
    assert rule.rate is not None
    if rule.scheme == "per_dot":
        return rule.rate * rating
    if rule.scheme == "progressive":
        return rule.rate * rating * (rating + 1) // 2
    if rule.scheme == "fixed":
        return rule.rate
    raise ValueError(f"unknown scheme {rule.scheme!r}")


def points(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> int:
    """What the trait is worth at its rating, starting dots included: a merit's
    points as the troupe prices it. Always positive, even for a flaw."""
    if not trait.rating:
        return 0
    return abs(price(choose_rule(rules, sheet, trait), trait.rating))


def fixed_rating(
    rules: TroupeRules, sheet: Sequence[SheetTrait], category: str, name: str
) -> int | None:
    """The rating this character holds a merit or flaw at, or None for a trait
    bought dot by dot. A troupe's fixed price for it is its value, where that price
    is the one that applies to the character; otherwise the catalogue's rating."""
    book = rules.rule_set.trait_properties(category, name).get("rating")
    if book is None:
        return None
    try:
        rule = choose_rule(rules, sheet, SheetTrait(category=category, name=name, rating=book))
    except PricingError:
        return book
    if rule.house and rule.scheme == "fixed" and rule.rate:
        return abs(rule.rate)
    return book


def trait_cost(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> Quote:
    """What the character has paid for this trait at its current rating."""
    category = rules.rule_set.categories.get(trait.category)
    if category is None:
        raise UnknownCategory(f"{trait.category!r} is not a {rules.splat} category")
    if not category.rated or trait.rating is None:
        raise PricingError(f"{trait.category} {trait.name!r} has no rating to price")
    if category.max_rating is not None and trait.rating > category.max_rating:
        raise RatingOutOfRange(f"{trait.category} cannot go above {category.max_rating}")
    if not 0 <= trait.free_rating <= trait.rating:
        raise RatingOutOfRange("the free rating must be between 0 and the rating")

    rule = choose_rule(rules, sheet, trait)
    if trait.rating == trait.free_rating:
        return Quote(cost=0, rule=rule)
    opened = opening(rules, sheet, trait)
    if opened is not None:
        rule = opened.rule(trait)
        cost = price(rule, trait.rating) - price(rule, trait.free_rating)
        return Quote(cost=cost, rule=rule, opening=opened)
    cost = price(rule, trait.rating) - price(rule, trait.free_rating)
    percent = priced(rules.rule_set, sheet).cost_percent
    key = matching(percent, trait)
    if key is not None:
        # Rounded up, as the book does for half costs.
        cost = -((-cost * percent[key]) // 100)
    return Quote(cost=cost, rule=rule)


def purchase_cost(
    rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait, to_rating: int
) -> Quote:
    """What raising (or lowering) `trait` to `to_rating` costs, priced against the
    sheet as it stands before the purchase."""
    before = trait_cost(rules, sheet, trait)
    after = trait_cost(
        rules,
        sheet,
        SheetTrait(
            category=trait.category,
            name=trait.name,
            rating=to_rating,
            free_rating=trait.free_rating,
            detail=trait.detail,
        ),
    )
    return Quote(
        cost=after.cost - before.cost, rule=after.rule, opening=after.opening or before.opening
    )


def describe(rule: CostRuleData, unit: str = "dot") -> str:
    """How a rule prices, in plain words: "3 XP per dot", "1 XP back per point"."""

    def xp(amount: int) -> str:
        return f"{amount} XP" if amount >= 0 else f"{-amount} XP back"

    if rule.scheme == "free":
        return "free"
    if rule.scheme == "not_allowed":
        return "cannot be bought"
    if rule.scheme == "table":
        assert rule.table is not None
        shown = ", ".join(map(str, rule.table[:5])) + (", …" if len(rule.table) > 5 else "")
        return f"{shown} XP for each {unit} in turn"
    assert rule.rate is not None
    if rule.scheme == "per_dot":
        return f"{xp(rule.rate)} per {unit}"
    if rule.scheme == "progressive":
        return f"{xp(rule.rate)} × the new rating"
    return xp(rule.rate)
