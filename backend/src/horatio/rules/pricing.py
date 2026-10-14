"""What traits cost under a troupe's rules.

The cost of a trait at a rating is the price of that rating less the price of
its free rating, the part the character did not pay for. A purchase costs the
difference between the trait's cost after and before.

Choosing the cost rule: house rules beat generic rules outright. Within
whichever of those has a match, a rule naming the trait beats a whole
category, and a rule testing more facts beats one testing fewer. Two rules
left tied is a mistake in the rules, and is refused rather than guessed at.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from horatio.rules.conditions import clause_count, holds
from horatio.rules.grants import effects, matching
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


def choose_rule(rules: TroupeRules, sheet: Sequence[SheetTrait], trait: SheetTrait) -> CostRuleData:
    facts = SPLATS[rules.splat].facts(rules, sheet, trait)

    def applies(rule: CostRuleData) -> bool:
        return (
            rule.category == trait.category
            and rule.trait in (None, trait.name)
            and holds(rule.condition, facts)
        )

    matching = [r for r in rules.house_rules if applies(r)] or [
        r for r in rules.rule_set.cost_rules if applies(r)
    ]
    if not matching:
        raise NoCostRule(f"no cost rule for {trait.category} {trait.name!r}")

    def specificity(rule: CostRuleData) -> tuple[bool, int]:
        return (rule.trait is not None, clause_count(rule.condition))

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
    cost = price(rule, trait.rating) - price(rule, trait.free_rating)
    found = effects(rules.rule_set.grants, sheet, rules.rule_set)
    key = matching(found.cost_percent, trait)
    if key is not None:
        # Rounded up, as the book does for half costs.
        cost = -((-cost * found.cost_percent[key]) // 100)
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
    return Quote(cost=after.cost - before.cost, rule=after.rule)
