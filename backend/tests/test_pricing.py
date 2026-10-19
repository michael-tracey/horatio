"""How a troupe's rules choose a cost rule and price a trait."""

import pytest

from horatio.rules.files import check_cost_rule
from horatio.rules.model import (
    CategoryData,
    CostRuleData,
    RuleSetData,
    SheetTrait,
    TraitData,
    TroupeRules,
)
from horatio.rules.pricing import (
    AmbiguousCostRule,
    NoCostRule,
    NotAllowed,
    RatingOutOfRange,
    UnknownCategory,
    purchase_cost,
    trait_cost,
)

CATEGORIES = {
    "skills": CategoryData(key="skills", name="Skills", group="Skills", max_rating=10),
    "merits": CategoryData(key="merits", name="Merits", group="Merits", house_rules_per_trait=True),
    "techniques": CategoryData(key="techniques", name="Techniques", group="Disciplines"),
    "backgrounds": CategoryData(key="backgrounds", name="Backgrounds", group="Backgrounds"),
}


def rule_set(*cost_rules: CostRuleData) -> RuleSetData:
    return RuleSetData(
        key="test",
        splat="vampire",
        name="Test",
        version=1,
        starting_xp=0,
        categories=CATEGORIES,
        cost_rules=list(cost_rules),
        traits={("merits", "Iron Will"): TraitData(category="merits", name="Iron Will")},
    )


def cost(rules: TroupeRules, trait: SheetTrait, *others: SheetTrait) -> int:
    return trait_cost(rules, [trait, *others], trait).cost


def skill(rating: int, free: int = 0) -> SheetTrait:
    return SheetTrait(category="skills", name="Brawl", rating=rating, free_rating=free)


def generation(rating: int) -> SheetTrait:
    return SheetTrait(category="backgrounds", name="Generation", rating=rating)


@pytest.mark.parametrize(
    ("rule", "rating", "expected"),
    [
        (CostRuleData("skills", "per_dot", rate=3), 4, 12),
        (CostRuleData("skills", "progressive", rate=2), 3, 12),  # 2 + 4 + 6
        (CostRuleData("skills", "table", table=(1, 4, 6)), 3, 11),
        (CostRuleData("skills", "fixed", rate=5), 3, 5),
        (CostRuleData("skills", "free"), 5, 0),
        (CostRuleData("skills", "progressive", rate=2), 0, 0),
    ],
)
def test_schemes(rule: CostRuleData, rating: int, expected: int) -> None:
    assert cost(TroupeRules(rule_set(rule)), skill(rating)) == expected


def test_free_dots_are_not_paid_for() -> None:
    rules = TroupeRules(rule_set(CostRuleData("skills", "progressive", rate=2)))

    # Dots 3 and 4 only: 6 + 8.
    assert cost(rules, skill(4, free=2)) == 14


def test_a_purchase_costs_the_difference() -> None:
    rules = TroupeRules(rule_set(CostRuleData("skills", "progressive", rate=2)))

    quote = purchase_cost(rules, [skill(2)], skill(2), to_rating=4)

    assert quote.cost == 14  # dots 3 and 4: 6 + 8
    assert quote.rule.describe() == {
        "category": "skills",
        "scheme": "progressive",
        "rate": 2,
        "house_rule": False,
    }


def test_a_rule_naming_the_trait_beats_the_category() -> None:
    rules = TroupeRules(
        rule_set(
            CostRuleData("skills", "per_dot", rate=2),
            CostRuleData("skills", "per_dot", rate=1, trait="Brawl"),
        )
    )

    assert cost(rules, skill(3)) == 3


def test_a_rule_with_more_conditions_beats_one_with_fewer() -> None:
    rules = TroupeRules(
        rule_set(
            CostRuleData("skills", "per_dot", rate=2),
            CostRuleData("skills", "per_dot", rate=1, condition={"generation": 1}),
        )
    )

    assert cost(rules, skill(3), generation(1)) == 3
    assert cost(rules, skill(3), generation(2)) == 6


def test_a_house_rule_beats_an_equally_specific_generic_rule() -> None:
    generic = rule_set(
        CostRuleData("skills", "per_dot", rate=2),
        CostRuleData("skills", "per_dot", rate=1, condition={"generation": 1}),
    )
    rules = TroupeRules(
        generic,
        house_rules=[
            CostRuleData("skills", "per_dot", rate=5, house=True),
            CostRuleData("skills", "per_dot", rate=3, condition={"generation": 1}, house=True),
        ],
    )

    assert cost(rules, skill(2), generation(2)) == 10
    assert cost(rules, skill(2), generation(1)) == 6


def test_a_more_specific_generic_rule_beats_a_house_rule() -> None:
    """A troupe re-pricing a whole category leaves the rule set's prices for
    single traits, and for narrower conditions, alone."""
    generic = rule_set(
        CostRuleData("merits", "per_dot", rate=1),
        CostRuleData("merits", "fixed", rate=2, trait="Lucky", condition={"generation": 1}),
        CostRuleData("skills", "per_dot", rate=2),
        CostRuleData("skills", "per_dot", rate=1, condition={"generation": 1}),
    )
    rules = TroupeRules(
        generic,
        house_rules=[
            CostRuleData("merits", "per_dot", rate=2, house=True),
            CostRuleData("skills", "per_dot", rate=5, house=True),
        ],
    )
    lucky = SheetTrait(category="merits", name="Lucky", rating=3)

    assert cost(rules, lucky, generation(1)) == 2
    assert cost(rules, lucky, generation(2)) == 6
    assert cost(rules, skill(2), generation(1)) == 2


def test_a_house_rule_for_one_merit_leaves_other_merits_alone() -> None:
    generic = rule_set(CostRuleData("merits", "per_dot", rate=1))
    rules = TroupeRules(
        generic,
        house_rules=[
            CostRuleData(
                "merits", "fixed", rate=4, trait="Iron Will", text="Pricier here", house=True
            )
        ],
    )
    iron_will = SheetTrait(category="merits", name="Iron Will", rating=2)
    other = SheetTrait(category="merits", name="Lucky", rating=2)

    assert cost(rules, iron_will) == 4
    assert cost(rules, other) == 2


def test_tied_rules_are_refused_rather_than_guessed() -> None:
    rules = TroupeRules(
        rule_set(
            CostRuleData("skills", "per_dot", rate=1, condition={"generation": {"lt": 5}}),
            CostRuleData("skills", "per_dot", rate=2, condition={"generation": {"gte": 2}}),
        )
    )

    with pytest.raises(AmbiguousCostRule):
        cost(rules, skill(1), generation(3))


def test_a_trait_that_is_not_allowed_cannot_be_bought() -> None:
    rules = TroupeRules(rule_set(CostRuleData("techniques", "not_allowed")))
    technique = SheetTrait(category="techniques", name="Ward", rating=0)

    assert cost(rules, technique) == 0
    with pytest.raises(NotAllowed):
        purchase_cost(rules, [technique], technique, to_rating=1)


def test_unpriceable_traits_are_refused_not_free() -> None:
    rules = TroupeRules(rule_set(CostRuleData("skills", "per_dot", rate=1)))

    with pytest.raises(NoCostRule):
        cost(rules, SheetTrait(category="backgrounds", name="Resources", rating=1))
    with pytest.raises(UnknownCategory):
        cost(rules, SheetTrait(category="gifts", name="Spirit Speech", rating=1))
    with pytest.raises(RatingOutOfRange):
        cost(rules, skill(11))
    with pytest.raises(RatingOutOfRange):
        cost(TroupeRules(rule_set(CostRuleData("skills", "table", table=(1, 2)))), skill(3))


def test_merit_house_rules_must_name_one_merit() -> None:
    with pytest.raises(ValueError, match="must name one trait"):
        check_cost_rule(CostRuleData("merits", "per_dot", rate=2, house=True), rule_set())


def test_conditions_may_only_test_the_splats_facts() -> None:
    with pytest.raises(ValueError, match="unknown fact"):
        check_cost_rule(CostRuleData("skills", "free", condition={"rank": 2}), rule_set())
    with pytest.raises(ValueError, match="unknown operator"):
        check_cost_rule(
            CostRuleData("skills", "free", condition={"generation": {"about": 2}}), rule_set()
        )
