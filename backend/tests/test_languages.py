"""How many languages Linguistics gives, as a troupe plays it: the book's, the
accelerated chart and a troupe's own, each with Natural Linguist doubling it or not."""

import pytest

from horatio.rules.checks import violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.languages import (
    ACCELERATED,
    CATEGORY,
    LanguageRule,
    applied,
    chart_text,
    counts_languages,
)
from horatio.rules.model import SheetTrait

PAGE = "House rule — Lords of the Night"


@pytest.fixture(scope="module", params=["bns_met_vampire.toml", "bns_met_ghoul.toml"])
def checks(request: pytest.FixtureRequest) -> list:  # type: ignore[type-arg]
    """The language checks of each rule set: the ghoul's takes the vampire's."""
    rule_set = load_rule_set(DATA_DIR / request.param)
    return list(rule_set.checks)


def sheet(rating: int, languages: int, natural: bool = False) -> list[SheetTrait]:
    found = [SheetTrait("skills", "Linguistics", rating)]
    found += [SheetTrait(CATEGORY, "Custom", 1, detail=f"Tongue {n}") for n in range(languages)]
    if natural:
        found.append(SheetTrait("merits", "Natural Linguist", 1))
    return found


def most(checks: list, rule: LanguageRule, rating: int, natural: bool = False) -> int:  # type: ignore[type-arg]
    """The most languages a sheet may hold under the rule, by trying."""
    played = applied(checks, rule, PAGE)
    held = 0
    while not violations(played, sheet(rating, held + 1, natural)):
        held += 1
        assert held < 200
    return held


@pytest.mark.parametrize(
    ("rule", "rating", "plain", "natural"),
    [
        (LanguageRule(), 3, 3, 6),
        (LanguageRule(natural_doubles=False), 3, 3, 3),
        (LanguageRule("accelerated"), 3, 4, 8),
        (LanguageRule("accelerated"), 5, 16, 32),
        (LanguageRule("accelerated"), 9, 32, 64),
        (LanguageRule("accelerated", natural_doubles=False), 5, 16, 16),
        (LanguageRule("custom", (2, 3, 5)), 2, 3, 6),
        (LanguageRule("custom", (2, 3, 5)), 4, 5, 10),
        (LanguageRule("custom", (2, 3, 5), natural_doubles=False), 1, 2, 2),
        # A chart kept but not chosen plays nothing.
        (LanguageRule("book", (9, 9)), 2, 2, 4),
    ],
)
def test_each_chart_with_and_without_natural_linguist(
    checks: list,  # type: ignore[type-arg]
    rule: LanguageRule,
    rating: int,
    plain: int,
    natural: int,
) -> None:
    assert most(checks, rule, rating) == plain == rule.allowed(rating)
    assert most(checks, rule, rating, natural=True) == natural == rule.allowed(rating, True)


def test_the_book_leaves_the_checks_as_written(checks: list) -> None:  # type: ignore[type-arg]
    assert applied(checks, LanguageRule(), PAGE) == tuple(checks)


def test_a_chart_keeps_the_checks_keys_and_says_it_is_a_house_rule(checks: list) -> None:  # type: ignore[type-arg]
    before = [c for c in checks if counts_languages(c)]
    after = [c for c in applied(checks, LanguageRule("accelerated"), PAGE) if counts_languages(c)]

    assert [c.key for c in after] == [c.key for c in before]
    assert len(after) == 2
    assert {c.page for c in after} == {PAGE}
    assert [c.message for c in after] == [
        "This troupe's chart: 1, 2, 4, 8, 16, 24 and 32 languages at Linguistics 1 to 7,"
        " and 32 above.",
        "Natural Linguist doubles the troupe's chart: 2, 4, 8, 16, 32, 48 and 64 languages"
        " at Linguistics 1 to 7, and 64 above.",
    ]
    # Lore's own checks are left alone.
    others = [c for c in checks if not counts_languages(c)]
    assert [
        c for c in applied(checks, LanguageRule("accelerated"), PAGE) if not counts_languages(c)
    ] == others


def test_a_chart_in_words() -> None:
    assert chart_text(ACCELERATED).startswith("1, 2, 4, 8, 16, 24 and 32 languages")
    assert chart_text([1, 2, 3, 3, 3]) == "1, 2 and 3 languages at Linguistics 1 to 3, and 3 above"
    assert chart_text([1, 1]) == "1 language at any rating of Linguistics"
    assert LanguageRule().ratings(5) == [1, 2, 3, 4, 5]
    assert LanguageRule("accelerated").ratings(9)[-3:] == [32, 32, 32]


BY_THE_BOOK_AND_A_CHART = [LanguageRule(), LanguageRule("accelerated")]


@pytest.mark.parametrize("rule", BY_THE_BOOK_AND_A_CHART)
def test_a_language_with_no_linguistics_breaks_one_check_not_natural_linguists(
    checks: list,  # type: ignore[type-arg]
    rule: LanguageRule,
) -> None:
    found = violations(applied(checks, rule, PAGE), sheet(0, 1))

    assert len(found) == 1
    assert "Natural Linguist" not in found[0].message
    assert found[0].on_sheet.startswith("Holds Tongue 0 with no Linguistics. ")


@pytest.mark.parametrize("rule", BY_THE_BOOK_AND_A_CHART)
def test_natural_linguist_within_twice_the_limit_breaks_nothing(
    checks: list,  # type: ignore[type-arg]
    rule: LanguageRule,
) -> None:
    played = applied(checks, rule, PAGE)

    assert violations(played, sheet(1, rule.allowed(1, True), natural=True)) == []
    # One more breaks Natural Linguist's check alone.
    over = violations(played, sheet(1, rule.allowed(1, True) + 1, natural=True))
    assert over
    assert all(v.message.startswith("Natural Linguist") for v in over)


def test_the_sheet_names_the_languages_held_against_the_dots(checks: list) -> None:  # type: ignore[type-arg]
    found = violations(checks, sheet(2, 3))

    assert {v.on_sheet for v in found} == {
        "Holds Tongue 0, Tongue 1 and Tongue 2 with Linguistics 2, which allows 2."
        " A character has one language per dot of Linguistics, besides their native tongue."
        " (p. 94)"
    }
