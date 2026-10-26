"""A house merit's effect blocks do exactly what the book merit they copy does: the
same free dots, maximums, prices, in-clan disciplines and checks, from the same
engine (horatio.rules.house_effects)."""

import uuid
from collections.abc import Sequence
from dataclasses import replace
from functools import cache
from typing import Any

import pytest

from horatio.rules.checks import Context, Violation, violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.grants import Effects, effects, raised_by
from horatio.rules.house_effects import compile_effects, merged
from horatio.rules.model import (
    HouseTraitData,
    RuleSetData,
    SheetTrait,
    TraitData,
    TroupeRules,
    house_page,
)
from horatio.rules.pricing import trait_cost
from horatio.rules.splats import SPLATS, vampire_facts

HOUSE = uuid.UUID(int=1)


@cache
def book() -> RuleSetData:
    return load_rule_set(DATA_DIR / "bns_met_vampire.toml")


def house_trait(name: str, *blocks: dict[str, Any], category: str = "merits") -> HouseTraitData:
    return HouseTraitData(
        id=HOUSE,
        troupe_id=uuid.UUID(int=2),
        troupe_name="Night Court",
        category=category,
        name=name,
        points=3,
        kind="General",
        availability="building",
        effects=tuple(blocks),
    )


def with_house(name: str, *blocks: dict[str, Any], category: str = "merits") -> TroupeRules:
    """The book's rules with one house merit of these blocks, as a troupe's are read."""
    trait = house_trait(name, *blocks, category=category)
    traits = {
        **book().traits,
        (category, name): TraitData(
            category=category,
            name=name,
            description=None,
            page_reference=house_page("Night Court"),
            properties={"rating": 3, "type": "General", "house": True, "offered": True},
        ),
    }
    rule_set, found = merged(replace(book(), traits=traits), [trait])
    assert not compile_effects(found[0], rule_set).problems
    return TroupeRules(rule_set, house_traits=found)


def t(category: str, name: str, rating: int | None = 1, detail: str = "") -> SheetTrait:
    return SheetTrait(category=category, name=name, rating=rating, free_rating=0, detail=detail)


def sheet_of(clan: str, *traits: SheetTrait) -> list[SheetTrait]:
    return [t("clan", clan, None), t("backgrounds", "Generation", 3), *traits]


def given(rules: TroupeRules, sheet: Sequence[SheetTrait]) -> Effects:
    return effects(rules.rule_set.grants, sheet, rules.rule_set)


def without_givers(found: Effects) -> tuple[Any, ...]:
    """What grants do, leaving out which trait gives it."""
    return (
        found.added,
        found.free_up_to,
        sorted(found.raises, key=str),
        found.in_clan_priced,
        found.cost_percent,
        set(found.out_of_clan_priced),
        set(found.no_free_dot),
        len(found.unchosen),
    )


def broken(rules: TroupeRules, sheet: Sequence[SheetTrait], finished: bool = False) -> list[str]:
    """What the sheet breaks, as (strength, subject) with the merit's name made the same."""
    native = frozenset(SPLATS["vampire"].in_clan(rules, sheet))
    context = Context(in_clan=native, native=native, finished=finished, kinds=rules.rule_set.kinds)
    found: list[Violation] = violations(rules.checks(), sheet, context)
    return sorted(f"{v.check.strength} {v.subject.category}/{v.subject.full_name}" for v in found)


def same(found: list[str], book_merit: str, house_merit: str) -> list[str]:
    return [line.replace(book_merit, house_merit) for line in found]


# --- Free dots -----------------------------------------------------------------------------


@pytest.mark.parametrize("detail", ["Resources", "Herd", "Haven", "Fame", ""])
def test_free_dots_of_the_players_choice_are_personal_cults(detail: str) -> None:
    rules = with_house(
        "Old Money",
        {
            "kind": "free_up_to",
            "category": "backgrounds",
            "names": ["Haven", "Herd", "Resources"],
            "amount": 5,
        },
    )

    cult = given(rules, sheet_of("Brujah", t("merits", "Personal Cult", 1, detail)))
    house = given(rules, sheet_of("Brujah", t("merits", "Old Money", 3, detail)))

    assert without_givers(house) == without_givers(cult)


def test_free_dots_of_one_trait_are_personal_cults_for_that_trait() -> None:
    rules = with_house(
        "Old Money",
        {"kind": "free_up_to", "category": "backgrounds", "names": ["Resources"], "amount": 5},
    )

    cult = given(rules, sheet_of("Brujah", t("merits", "Personal Cult", 1, "Resources")))
    house = given(rules, sheet_of("Brujah", t("merits", "Old Money")))

    assert house.free_up_to == cult.free_up_to == {("backgrounds", "Resources", ""): 5}
    assert house.sources == {("backgrounds", "Resources", ""): ["Old Money"]}


def test_two_free_dots_of_resources() -> None:
    rules = with_house(
        "Old Money",
        {"kind": "free_up_to", "category": "backgrounds", "names": ["Resources"], "amount": 2},
    )

    assert given(rules, sheet_of("Brujah", t("merits", "Old Money"))).free_up_to == {
        ("backgrounds", "Resources", ""): 2
    }
    assert given(rules, sheet_of("Brujah")).free_up_to == {}


# --- Maximums ------------------------------------------------------------------------------


def test_a_raised_maximum_and_free_lore_are_blood_of_the_tzimisces() -> None:
    rules = with_house(
        "Old Blood",
        {"kind": "free_up_to", "category": "skills", "names": ["Lore"], "amount": 2},
        {"kind": "raise_max", "category": "skills", "names": ["Lore"], "amount": 2},
    )

    tzimisce = given(rules, sheet_of("Tzimisce", t("merits", "Blood of the Tzimisce")))
    house = given(rules, sheet_of("Tzimisce", t("merits", "Old Blood")))

    assert without_givers(house) == without_givers(tzimisce)
    assert raised_by(house, "skills", "Lore", "") == raised_by(tzimisce, "skills", "Lore", "") == 2
    assert raised_by(house, "skills", "Dodge", "") == 0


def test_raising_a_whole_category_is_a_luminary_elders_skills() -> None:
    rules = with_house("Old Learning", {"kind": "raise_max", "category": "skills", "amount": 1})

    luminary = given(rules, [t("clan", "Brujah", None), t("backgrounds", "Generation", 5)])
    house = given(
        rules,
        [t("clan", "Brujah", None), t("backgrounds", "Generation", 1), t("merits", "Old Learning")],
    )

    assert (
        raised_by(house, "skills", "Dodge", "") == raised_by(luminary, "skills", "Dodge", "") == 1
    )


# --- Prices --------------------------------------------------------------------------------


@pytest.mark.parametrize("rating", [1, 4, 6])
def test_half_price_singing_is_supernatural_arias(rating: int) -> None:
    rules = with_house(
        "Golden Voice",
        {
            "kind": "cost_percent",
            "category": "skills",
            "names": ["Performance"],
            "detail": "Singing",
            "amount": 50,
        },
        {
            "kind": "raise_max",
            "category": "skills",
            "names": ["Performance"],
            "detail": "Singing",
            "amount": 3,
        },
    )
    singing = t("skills", "Performance", rating, "Singing")
    dancing = t("skills", "Performance", rating, "Dancing")

    for other in (singing, dancing):
        aria = sheet_of("Toreador", t("merits", "Supernatural Aria"), other)
        house = sheet_of("Toreador", t("merits", "Golden Voice"), other)
        assert trait_cost(rules, house, other) == trait_cost(rules, aria, other)
    aria_effects = given(rules, sheet_of("Toreador", t("merits", "Supernatural Aria")))
    house_effects = given(rules, sheet_of("Toreador", t("merits", "Golden Voice")))
    assert without_givers(house_effects) == without_givers(aria_effects)
    plain = sheet_of("Toreador", singing)
    assert (
        trait_cost(rules, plain, singing).cost
        > trait_cost(
            rules, sheet_of("Toreador", t("merits", "Golden Voice"), singing), singing
        ).cost
    )


def test_a_path_priced_in_clan_is_thaumaturgic_expertises() -> None:
    path = "Thaumaturgy: Path of Conjuring"
    rules = with_house(
        "Hedge Scholar",
        {"kind": "price_in_clan", "category": "disciplines", "names": [path]},
    )
    bought = t("disciplines", path, 3)

    expertise = sheet_of("Tremere", t("merits", "Thaumaturgic Expertise", 1, path), bought)
    house = sheet_of("Tremere", t("merits", "Hedge Scholar"), bought)

    assert trait_cost(rules, house, bought) == trait_cost(rules, expertise, bought)
    assert trait_cost(rules, house, bought) != trait_cost(
        rules, sheet_of("Tremere", bought), bought
    )


def test_a_discipline_priced_out_of_clan_is_inepts() -> None:
    rules = with_house(
        "Weak Blood",
        {"kind": "price_out_of_clan", "category": "disciplines", "names": ["Potence"]},
        category="flaws",
    )
    bought = t("disciplines", "Potence", 2)

    inept = sheet_of("Brujah", t("flaws", "Inept", 1, "Potence"), bought)
    house = sheet_of("Brujah", t("flaws", "Weak Blood"), bought)

    assert trait_cost(rules, house, bought) == trait_cost(rules, inept, bought)
    assert vampire_facts(rules, house, bought)["in_clan"] is False
    assert vampire_facts(rules, house, bought)["no_free_dot"] is True


# --- Health levels -------------------------------------------------------------------------


def test_more_health_levels_are_ruggeds() -> None:
    rules = with_house(
        "Hard to Kill",
        {
            "kind": "add",
            "category": "health_levels",
            "names": ["Healthy", "Injured", "Incapacitated"],
            "amount": 1,
        },
    )

    rugged = given(rules, sheet_of("Brujah", t("merits", "Rugged")))
    house = given(rules, sheet_of("Brujah", t("merits", "Hard to Kill")))

    assert without_givers(house) == without_givers(rugged)


def test_one_fewer_is_low_pain_thresholds() -> None:
    rules = with_house(
        "Glass Bones",
        {
            "kind": "add",
            "category": "health_levels",
            "names": ["Injured", "Incapacitated"],
            "amount": -1,
        },
        category="flaws",
    )

    flaw = given(rules, sheet_of("Brujah", t("flaws", "Low Pain Threshold")))
    house = given(rules, sheet_of("Brujah", t("flaws", "Glass Bones")))

    assert without_givers(house) == without_givers(flaw) != without_givers(Effects())


# --- An extra in-clan discipline -----------------------------------------------------------

COMMON = [
    "Animalism",
    "Auspex",
    "Celerity",
    "Dominate",
    "Fortitude",
    "Obfuscate",
    "Potence",
    "Presence",
]


@pytest.fixture
def common_house() -> TroupeRules:
    return with_house("Wide Blood", {"kind": "extra_in_clan", "names": COMMON})


@pytest.mark.parametrize("clan", ["Brujah", "Caitiff"])
@pytest.mark.parametrize(
    "extras",
    [[], ["Auspex"], ["Protean"], ["Auspex", "Dominate"]],
)
@pytest.mark.parametrize("finished", [False, True])
def test_an_extra_in_clan_discipline_is_additional_common_disciplines(
    common_house: TroupeRules, clan: str, extras: list[str], finished: bool
) -> None:
    rules = common_house
    caitiff = ["Celerity", "Fortitude", "Obfuscate"] if clan == "Caitiff" else []
    held = [t("extra_in_clan_disciplines", n) for n in caitiff + extras]
    acd = sheet_of(clan, t("merits", "Additional Common Discipline", 4), *held)
    house = sheet_of(clan, t("merits", "Wide Blood", 3), *held)

    assert same(broken(rules, acd, finished), "Additional Common Discipline", "Wide Blood") == (
        broken(rules, house, finished)
    )
    assert SPLATS["vampire"].in_clan(rules, house) == SPLATS["vampire"].in_clan(rules, acd)
    for name in extras:
        bought = t("disciplines", name, 1)
        assert (
            vampire_facts(rules, [*house, bought], bought)["no_free_dot"]
            == (vampire_facts(rules, [*acd, bought], bought)["no_free_dot"])
        )
        assert trait_cost(rules, [*house, bought], bought) == trait_cost(
            rules, [*acd, bought], bought
        )


def test_without_the_merit_an_extra_in_clan_discipline_is_refused(
    common_house: TroupeRules,
) -> None:
    sheet = sheet_of("Brujah", t("extra_in_clan_disciplines", "Auspex"))

    assert "refuse extra_in_clan_disciplines/Auspex" in broken(common_house, sheet)


def test_an_extra_in_clan_discipline_waits_to_be_chosen(common_house: TroupeRules) -> None:
    sheet = sheet_of("Brujah", t("merits", "Wide Blood", 3))
    native = frozenset(SPLATS["vampire"].in_clan(common_house, sheet))
    messages = [
        v.message
        for v in violations(common_house.checks(), sheet, Context(in_clan=native, native=native))
    ]

    assert (
        "Wide Blood: choose the in-clan discipline it adds. (House rule — Night Court)" in messages
    )
    assert broken(common_house, sheet, finished=True) == []


def test_only_one_merit_adds_an_in_clan_discipline(common_house: TroupeRules) -> None:
    sheet = sheet_of(
        "Brujah",
        t("merits", "Wide Blood", 3),
        t("merits", "Additional Common Discipline", 4),
        t("extra_in_clan_disciplines", "Auspex"),
    )

    assert "refuse merits/Wide Blood" in broken(common_house, sheet, finished=True)


# --- Requires and Not with -----------------------------------------------------------------


def checked(*blocks: dict[str, Any]) -> TroupeRules:
    return with_house("Old Money", *blocks)


@pytest.mark.parametrize(
    ("block", "allowed", "refused"),
    [
        (
            {"kind": "requires", "test": "clan", "names": ["Brujah"]},
            [t("clan", "Brujah", None), t("clan", "Brujah: True Brujah", None)],
            [t("clan", "Ventrue", None)],
        ),
        (
            {"kind": "forbids", "test": "clan", "names": ["Brujah"]},
            [t("clan", "Ventrue", None)],
            [t("clan", "Brujah", None)],
        ),
        (
            {"kind": "requires", "test": "sect", "names": ["Camarilla", "Anarch"]},
            [t("sect", "Anarch", None)],
            [t("sect", "Sabbat", None)],
        ),
        (
            {
                "kind": "requires",
                "test": "trait",
                "category": "backgrounds",
                "name": "Resources",
                "rating": 1,
            },
            [t("backgrounds", "Resources", 1), t("backgrounds", "Resources", 3)],
            [t("backgrounds", "Herd", 2)],
        ),
        (
            {
                "kind": "forbids",
                "test": "trait",
                "category": "backgrounds",
                "name": "Resources",
                "rating": 3,
            },
            [t("backgrounds", "Resources", 2)],
            [t("backgrounds", "Resources", 3)],
        ),
        (
            {"kind": "forbids", "test": "trait", "category": "flaws", "name": "Inept"},
            [t("flaws", "Intolerance")],
            [t("flaws", "Inept", 1, "Potence")],
        ),
    ],
)
def test_requires_and_not_with(
    block: dict[str, Any], allowed: list[SheetTrait], refused: list[SheetTrait]
) -> None:
    rules = checked(block)
    merit = t("merits", "Old Money", 3)
    for trait in allowed:
        assert "refuse merits/Old Money" not in broken(rules, [merit, trait]), trait
    for trait in refused:
        assert "refuse merits/Old Money" in broken(rules, [merit, trait]), trait
    # Without the merit, nothing is asked.
    assert "refuse merits/Old Money" not in broken(rules, refused)


def test_a_check_can_wait_for_the_end_of_creation() -> None:
    rules = checked(
        {
            "kind": "requires",
            "test": "trait",
            "category": "backgrounds",
            "name": "Resources",
            "rating": 1,
            "strength": "complete",
        }
    )

    assert broken(rules, [t("merits", "Old Money", 3)]) == ["complete merits/Old Money"]


# --- What it says, and what it refuses ------------------------------------------------------


def test_the_summary_says_what_each_block_does() -> None:
    rules = with_house(
        "Old Money",
        {"kind": "free_up_to", "category": "backgrounds", "names": ["Resources"], "amount": 2},
        {"kind": "raise_max", "category": "skills", "names": ["Lore"], "amount": 2},
        {
            "kind": "cost_percent",
            "category": "skills",
            "names": ["Performance"],
            "detail": "Singing",
            "amount": 50,
        },
        {"kind": "add", "category": "health_levels", "names": ["Healthy"], "amount": 1},
        {"kind": "extra_in_clan", "names": ["Auspex", "Celerity"]},
        {
            "kind": "requires",
            "test": "trait",
            "category": "backgrounds",
            "name": "Resources",
            "rating": 1,
        },
        {"kind": "forbids", "test": "clan", "names": ["Caitiff"], "strength": "review"},
    )

    assert rules.house_traits[0].summary == (
        "The first 2 dots of Resources are free. "
        "Lore can go 2 higher than usual. "
        "Performance: Singing costs 50% of the usual XP. "
        "1 more Healthy health level. "
        "Adds one in-clan discipline, chosen from Auspex or Celerity. "
        "Needs Resources 1 or more. "
        "Not for Caitiff, or staff approve it."
    )
    assert rules.house_traits[0].in_clan == ("Auspex", "Celerity")


@pytest.mark.parametrize(
    ("block", "message"),
    [
        (
            {"kind": "free_up_to", "category": "backgrounds", "names": [], "amount": 2},
            "Choose at least one trait.",
        ),
        (
            {"kind": "free_up_to", "category": "backgrounds", "names": ["Wealth"], "amount": 2},
            "Wealth is not one of the backgrounds.",
        ),
        (
            {"kind": "free_up_to", "category": "clan", "names": ["Brujah"], "amount": 1},
            "Clan have no dots for this.",
        ),
        (
            {"kind": "free_up_to", "category": "merits", "names": ["Old Money"], "amount": 1},
            "An effect of Old Money cannot be about itself.",
        ),
        (
            {"kind": "raise_max", "category": "skills", "names": ["Lore"], "amount": 9},
            "How much higher is 1 to 5.",
        ),
        (
            {
                "kind": "free_choices",
                "category": "backgrounds",
                "names": ["Herd"],
                "count": 2,
                "amount": 1,
            },
            "The player picks 1 to 1 of them.",
        ),
        (
            {"kind": "requires", "test": "clan", "names": ["Martians"]},
            "Martians: no such clan in these rules.",
        ),
        (
            {
                "kind": "requires",
                "test": "trait",
                "category": "backgrounds",
                "name": "Resources",
                "rating": 0,
            },
            "The rating is 1 to 20.",
        ),
        ({"kind": "pool_bonus"}, "Choose what the effect does."),
    ],
)
def test_a_block_that_cannot_be_used_says_why(block: dict[str, Any], message: str) -> None:
    trait = house_trait("Old Money", block)

    problems = compile_effects(trait, book()).problems

    assert [(p.index, p.message) for p in problems] == [(0, message)]
