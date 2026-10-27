"""A house merit's effect blocks do exactly what the book merit they copy does: the
same free dots, maximums, prices, in-clan disciplines and checks, from the same
engine (horatio.rules.house_effects)."""

import json
import uuid
from collections.abc import Sequence
from dataclasses import replace
from functools import cache
from typing import Any

import pytest

from horatio import reference
from horatio.play import uses_per_game
from horatio.rules.allowance import allowance
from horatio.rules.checks import Context, Violation, violations
from horatio.rules.feeding import basis, need
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.grants import Effects, effects, raised_by
from horatio.rules.house_effects import compile_effects, merged
from horatio.rules.model import (
    ActionKindData,
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
        ({"kind": "teleport"}, "Choose what the effect does."),
    ],
)
def test_a_block_that_cannot_be_used_says_why(block: dict[str, Any], message: str) -> None:
    trait = house_trait("Old Money", block)

    problems = compile_effects(trait, book()).problems

    assert [(p.index, p.message) for p in problems] == [(0, message)]


# --- At a game, and between games ---------------------------------------------------------
#
# These become what a book merit has in the catalogue and the rules file, so the Play
# View and the downtimes read them as they read the book's.


def play_of(
    rules: TroupeRules, traits: Sequence[SheetTrait]
) -> tuple[dict[str, reference.TestPool], reference.Worked]:
    """The Play View's pools for the sheet, by key, and the switches."""
    sheet = reference.Sheet.of(traits, rules.rule_set)
    worked = reference.work_out(sheet, reference.technique_bases(rules.rule_set))
    found = reference.pools(sheet, worked.effects, 1, worked.hurts, worked.switches)
    return {p.key: p for p in found}, worked


def renamed(value: Any, book_name: str, house_name: str) -> Any:
    """A pool or a switch as plain data, the book's name made the house one's."""
    if isinstance(value, dict):
        value = {k: v.model_dump() for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    elif hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.loads(json.dumps(value).replace(book_name, house_name))


def fighter(*traits: SheetTrait) -> list[SheetTrait]:
    return sheet_of(
        "Brujah",
        t("attributes", "Physical", 5),
        t("attributes", "Social", 3),
        t("attributes", "Mental", 4),
        t("skills", "Brawl", 3),
        t("skills", "Dodge", 2),
        t("disciplines", "Auspex", 2),
        *traits,
    )


def test_an_always_on_pool_bonus_is_slow_reactions() -> None:
    rules = with_house(
        "Sluggish", {"kind": "pool_bonus", "pools": ["initiative"], "amount": -5}, category="flaws"
    )

    book_pools, _ = play_of(rules, fighter(t("flaws", "Slow Reactions", 3)))
    house_pools, _ = play_of(rules, fighter(t("flaws", "Sluggish", 3)))

    assert house_pools["initiative"].total == book_pools["initiative"].total == 0
    assert renamed(book_pools, "Slow Reactions", "Sluggish") == renamed(house_pools, "", "")
    assert rules.house_traits[0].summary == "−5 to initiative."


def test_a_bonus_only_some_of_the_time_is_black_hand_memberships() -> None:
    when = "against Telepathy and mind reading"
    rules = with_house(
        "Iron Will",
        {"kind": "pool_bonus", "pools": ["defense:Mental"], "amount": 3, "when": when},
    )

    book_pools, _ = play_of(rules, fighter(t("merits", "Black Hand Membership", 2)))
    house_pools, _ = play_of(rules, fighter(t("merits", "Iron Will", 3)))

    mental = house_pools["defense:Mental"]
    assert [(v.when, v.total) for v in mental.variants] == [(f"A{when[1:]}", 7)]
    assert renamed(book_pools, "Black Hand Membership", "Iron Will") == renamed(house_pools, "", "")


def test_a_bonus_to_every_pool_is_a_note_as_necrophiles_is() -> None:
    when = "until you have spent 10 minutes among corpses tonight"
    rules = with_house(
        "Grave Hunger",
        {"kind": "pool_bonus", "pools": ["all"], "amount": -1, "when": when},
        category="flaws",
    )

    _, book_worked = play_of(rules, fighter(t("flaws", "Necrophile", 1)))
    _, house_worked = play_of(rules, fighter(t("flaws", "Grave Hunger", 3)))

    assert reference.other_notes(house_worked.effects) == [
        n.replace("Necrophile", "Grave Hunger") for n in reference.other_notes(book_worked.effects)
    ]


def test_a_switch_is_bullet_times() -> None:
    note = "Ends if you spend an action moving."
    rules = with_house(
        "Bullet Dodge",
        {"kind": "switch", "changes": [{"pool": "dodge", "amount": 5}], "note": note},
    )

    book_pools, book_worked = play_of(rules, fighter(t("techniques", "Bullet Time", None)))
    house_pools, house_worked = play_of(rules, fighter(t("merits", "Bullet Dodge", 3)))

    [book_switch] = [s for s in book_worked.switches if s.key == "Bullet Time"]
    [house_switch] = house_worked.switches
    assert (house_switch.key, house_switch.name, house_switch.page) == (
        "Bullet Dodge",
        "Bullet Dodge",
        "House rule — Night Court",
    )
    for field in ("changes", "notes", "form", "health", "attributes"):
        assert getattr(house_switch, field) == getattr(book_switch, field), field
    assert house_switch.changes == ["+5 Dodge"]
    assert renamed(book_pools["dodge"], "Bullet Time", "Bullet Dodge") == renamed(
        house_pools["dodge"], "", ""
    )
    assert house_pools["dodge"].switched[0].value == 5


def test_a_switch_on_an_attribute_is_steal_the_minds() -> None:
    rules = with_house(
        "Stolen Wits", {"kind": "switch", "changes": [{"pool": "attribute:Mental", "amount": 3}]}
    )
    power = t("elder_disciplines", "Mytherceria: Steal the Mind", None)

    book_pools, book_worked = play_of(rules, fighter(power))
    house_pools, house_worked = play_of(rules, fighter(t("merits", "Stolen Wits", 3)))

    [book_switch] = book_worked.switches
    [house_switch] = house_worked.switches
    assert house_switch.attributes == book_switch.attributes
    assert house_switch.changes == book_switch.changes == ["+3 Mental"]
    for key in ("defense:Mental", "discipline:Auspex", "initiative"):
        assert renamed(book_pools[key], "Steal the Mind", "Stolen Wits") == renamed(
            house_pools[key], "", ""
        ), key
    assert [s.value for s in house_pools["defense:Mental"].switched] == [3]


def test_battle_trance_switches_brawl_up_and_mental_down() -> None:
    rules = with_house(
        "Battle Trance",
        {
            "kind": "switch",
            "changes": [
                {"pool": "attack:Brawl", "amount": 2},
                {"pool": "attribute:Mental", "amount": -2},
            ],
        },
        {"kind": "uses_per_game", "amount": 1},
    )

    pools, worked = play_of(rules, fighter(t("merits", "Battle Trance", 3)))

    [switch] = worked.switches
    assert switch.changes == ["+2 Brawl attacks", "-2 Mental"]
    brawl = pools["attack:Brawl"]
    assert (brawl.total, [(s.switch, s.value) for s in brawl.switched]) == (
        8,
        [("Battle Trance", 2)],
    )
    assert [(s.attribute, s.value) for s in pools["defense:Mental"].switched] == [("Mental", -2)]
    assert rules.house_traits[0].summary == (
        "Switched on in play: +2 to Brawl attacks and −2 to Mental pools. 1 use a game."
    )


def test_uses_a_game_are_oracular_abilitys() -> None:
    rules = with_house("Second Sight", {"kind": "uses_per_game", "amount": 1})

    book = rules.rule_set.trait_properties("merits", "Oracular Ability")["uses_per_game"]
    house = rules.rule_set.trait_properties("merits", "Second Sight")["uses_per_game"]

    assert uses_per_game(house, 3, {}) == uses_per_game(book, 2, {}) == 1


def test_fewer_downtime_actions_are_hunteds() -> None:
    rules = with_house(
        "Hounded",
        {"kind": "downtime_action", "action_kind": "general", "amount": -2},
        category="flaws",
    )

    book = allowance(rules, sheet_of("Brujah", t("flaws", "Hunted", 4)))
    house = allowance(rules, sheet_of("Brujah", t("flaws", "Hounded", 3)))

    assert house[0] == book[0]
    assert house[0]["general"] == 1
    assert [(x.action_kind, x.amount) for x in house[1]] == [
        (x.action_kind, x.amount) for x in book[1]
    ]
    assert [x.source for x in house[1]] == ["Everyone", "Hounded"]
    assert rules.house_traits[0].summary == "2 fewer Downtime actions."


def test_an_extra_downtime_action_of_a_kind() -> None:
    rules = with_house(
        "Ledger Keeper", {"kind": "downtime_action", "action_kind": "resources", "amount": 1}
    )

    totals, lines = allowance(rules, sheet_of("Brujah", t("merits", "Ledger Keeper", 3)))

    assert totals["resources"] == 1
    assert ("resources", "Ledger Keeper", 1) in [(x.action_kind, x.source, x.amount) for x in lines]
    assert rules.house_traits[0].summary == "1 more Resources action."


def test_a_troupes_own_kind_of_action_can_be_given() -> None:
    trait = house_trait("Night Watch", {"kind": "downtime_action", "action_kind": "patrol"})
    kinds = {**book().action_kinds, "patrol": ActionKindData("patrol", "Patrol action", house=True)}

    assert compile_effects(trait, book()).problems[0].message == (
        "Choose a kind of downtime action."
    )
    found = compile_effects(
        replace(trait, effects=({**trait.effects[0], "amount": 1},)), book(), kinds
    )
    assert not found.problems
    assert found.summary == "1 more Patrol action."


@pytest.mark.parametrize(
    ("book_trait", "block"),
    [
        (("merits", "Efficient Digestion"), {"herd_factor": 2}),
        (("flaws", "Disease Carrier"), {"amount": 1}),
        (("flaws", "Methuselah's Thirst"), {"herd_factor": 0, "always_half": True}),
    ],
)
def test_feeding_is_the_books_feeding_modifiers(
    book_trait: tuple[str, str], block: dict[str, Any]
) -> None:
    category, name = book_trait
    rules = with_house("Fussy Eater", {"kind": "feeding", **block}, category=category)

    book_basis = basis(rules, sheet_of("Brujah", t(category, name, 2), t("backgrounds", "Herd", 2)))
    house_basis = basis(
        rules, sheet_of("Brujah", t(category, "Fussy Eater", 3), t("backgrounds", "Herd", 2))
    )

    def plain(found: dict[str, Any]) -> dict[str, Any]:
        return {
            **found,
            "modifiers": [{**m, "source": "", "page": None} for m in found["modifiers"]],
        }

    assert plain(house_basis) == plain(book_basis)
    assert house_basis["modifiers"][0]["source"] == "Fussy Eater"
    assert house_basis["modifiers"][0]["page"] == "House rule — Night Court"
    book_need = need(1, "", book_basis)
    house_need = need(1, "", house_basis)
    assert (house_need.needed, house_need.herd_factor, house_need.always_half) == (
        book_need.needed,
        book_need.herd_factor,
        book_need.always_half,
    )


def test_the_feeding_summary() -> None:
    rules = with_house("Fussy Eater", {"kind": "feeding", "amount": -1, "herd_factor": 2})

    assert rules.house_traits[0].summary == (
        "Feeding: 1 fewer feeding action needed and each dot of Herd counts twice."
    )


def test_a_holder_that_is_not_held_changes_nothing() -> None:
    rules = with_house(
        "Battle Trance", {"kind": "switch", "changes": [{"pool": "attack:Brawl", "amount": 2}]}
    )

    pools, worked = play_of(rules, fighter())

    assert worked.switches == []
    assert pools["attack:Brawl"].switched == []


@pytest.mark.parametrize(
    ("blocks", "message"),
    [
        ([{"kind": "pool_bonus", "pools": [], "amount": 2}], "Choose at least one pool."),
        (
            [{"kind": "pool_bonus", "pools": ["attack:Lockpicking"], "amount": 2}],
            "attack:Lockpicking is not one of the Play View's pools.",
        ),
        (
            [{"kind": "pool_bonus", "pools": ["attribute:Mental"], "amount": 2}],
            "Only a switch can change Every pool made on Mental.",
        ),
        (
            [{"kind": "pool_bonus", "pools": ["dodge"], "amount": 0}],
            "A bonus of 0 changes nothing.",
        ),
        ([{"kind": "pool_bonus", "pools": ["dodge"], "amount": 9}], "The bonus is -5 to 5."),
        ([{"kind": "switch", "changes": []}], "Choose at least one pool it changes."),
        (
            [{"kind": "switch", "changes": [{"pool": "skill:Computer", "amount": 2}]}],
            "A switch cannot change Computer (a note: it has no pool).",
        ),
        (
            [{"kind": "switch", "changes": [{"pool": "dodge", "amount": 0}]}],
            "Each change is −5 to +5, and not 0.",
        ),
        ([{"kind": "uses_per_game", "amount": 0}], "Uses a game is 1 to 10."),
        (
            [{"kind": "downtime_action", "action_kind": "", "amount": 1}],
            "Choose a kind of downtime action.",
        ),
        (
            [{"kind": "downtime_action", "action_kind": "general", "amount": 0}],
            "Add or take away at least one.",
        ),
        ([{"kind": "feeding"}], "Choose what it changes when feeding."),
        ([{"kind": "feeding", "herd_factor": 5}], "Each dot of Herd counts 0 to 3 times."),
    ],
)
def test_a_play_block_that_cannot_be_used_says_why(
    blocks: list[dict[str, Any]], message: str
) -> None:
    problems = compile_effects(house_trait("Battle Trance", *blocks), book()).problems

    assert [(p.index, p.message) for p in problems] == [(0, message)]


def test_one_switch_and_one_number_of_uses_a_merit() -> None:
    switch = {"kind": "switch", "changes": [{"pool": "dodge", "amount": 1}]}
    uses = {"kind": "uses_per_game", "amount": 1}
    general = {"kind": "downtime_action", "action_kind": "general", "amount": 1}

    problems = compile_effects(
        house_trait("Battle Trance", switch, uses, switch, uses, general, general), book()
    ).problems

    assert [(p.index, p.message) for p in problems] == [
        (2, "A merit has one switch; put all it changes in it."),
        (3, "A merit has one number of uses a game."),
        (5, "That kind of action is given twice."),
    ]
