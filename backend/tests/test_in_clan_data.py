"""The in-clan disciplines in the rules data (#312): every name a clan or a grant gives
is a discipline the catalogue has, and every clan, alone and with each merit that
sets its in-clan disciplines, has as many in-clan disciplines to put its starting
picks on as it has picks, once its own choices are made."""

from collections.abc import Sequence
from functools import cache

import pytest

from horatio.rules.checks import matches
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.splats import SPLATS

# Categories whose traits are disciplines, by the name a clan or grant gives them.
DISCIPLINES = ("disciplines", "extra_in_clan_disciplines")
# The kinds of grant that add in-clan disciplines or set them.
IN_CLAN_KINDS = ("add", "replace_in_clan", "no_free_dot", "price_in_clan")
# A Caitiff chooses its three from the common disciplines (MET: VTM p. 246); a test of
# its own (test_api_creation_rules) covers the choosing.
CAITIFF_THREE = ("Animalism", "Auspex", "Celerity")


@cache
def rules(file: str = "bns_met_vampire.toml") -> TroupeRules:
    return TroupeRules(load_rule_set(DATA_DIR / file))


def clans(file: str = "bns_met_vampire.toml") -> list[str]:
    return sorted(n for c, n in rules(file).rule_set.traits if c == "clan")


@pytest.mark.parametrize("file", ["bns_met_vampire.toml", "bns_met_ghoul.toml"])
def test_every_clans_in_clan_disciplines_are_in_the_catalogue(file: str) -> None:
    rule_set = rules(file).rule_set
    missing = [
        f"{clan}: {name}"
        for clan in clans(file)
        for key in ("in_clan", "choices")
        for name in rule_set.trait_properties("clan", clan).get(key, [])
        if ("disciplines", name) not in rule_set.traits
    ]
    assert missing == []


@pytest.mark.parametrize(
    ("file", "category"),
    [
        ("bns_met_vampire.toml", "extra_in_clan_disciplines"),
        ("bns_met_ghoul.toml", "domitor_in_clan_disciplines"),
    ],
)
def test_every_in_clan_discipline_to_choose_is_a_discipline(file: str, category: str) -> None:
    """A Caitiff's three, and a merit's fourth, are disciplines a starting pick can go on."""
    traits = rules(file).rule_set.traits
    assert sorted(n for c, n in traits if c == category and ("disciplines", n) not in traits) == []


def test_every_discipline_a_grant_gives_in_clan_is_in_the_catalogue() -> None:
    rule_set = rules().rule_set
    missing: list[str] = []
    for grant in rule_set.grants:
        if grant.kind not in IN_CLAN_KINDS:
            continue
        categories = [c for c in grant.categories if c in DISCIPLINES]
        choose = grant.target.get("choose")
        named = [
            grant.target.get("name"),
            *grant.target.get("names", []),
            *(choose if isinstance(choose, list) else []),
        ]
        for category in categories:
            for name in named:
                if name and (category, name) not in rule_set.traits:
                    missing.append(f"{grant.source['name']}: {category} {name}")
    assert missing == []


def test_a_misspelt_in_clan_discipline_is_caught() -> None:
    """The test above fails on a name the catalogue lacks, as Valeran was."""
    rule_set = rules().rule_set
    assert ("disciplines", "Valeren") in rule_set.traits
    assert ("disciplines", "Valeran") not in rule_set.traits


def replacing_merits() -> list[str]:
    """The merits that set a character's in-clan disciplines in place of its clan's."""
    grants = rules().rule_set.grants
    return sorted({g.source["name"] for g in grants if g.kind == "replace_in_clan"})


def picks(sheet: Sequence[SheetTrait]) -> int:
    """The starting picks restricted to in-clan disciplines, as the sheet has them."""
    blank = SheetTrait(category="", name="")
    return sum(
        rule.picks or 0
        for rule in rules().creation_rules()
        if rule.category == "disciplines"
        and rule.restriction == "in_clan"
        and (not rule.when or matches(rule.when, sheet, blank))
    )


def fillable(sheet: Sequence[SheetTrait]) -> list[str]:
    """The disciplines a starting pick can go on: in-clan, with a free dot."""
    facts = SPLATS["vampire"].facts
    found = []
    for category, name in rules().rule_set.traits:
        if category != "disciplines":
            continue
        fact = facts(rules(), sheet, SheetTrait(category=category, name=name, rating=0))
        if fact["in_clan"] and not fact["no_free_dot"]:
            found.append(name)
    return found


def sheets_for(clan: str) -> list[tuple[str, list[SheetTrait]]]:
    """The clan as each of its players could make it: with each in-clan choice it
    leaves them, and a Caitiff with its three chosen."""
    choices = rules().rule_set.trait_properties("clan", clan).get("choices", [])
    extra = [
        SheetTrait(category="extra_in_clan_disciplines", name=n, rating=1)
        for n in (CAITIFF_THREE if clan == "Caitiff" else ())
    ]
    if not choices:
        return [(clan, [SheetTrait(category="clan", name=clan), *extra])]
    return [
        (f"{clan} ({c})", [SheetTrait(category="clan", name=clan, detail=c), *extra])
        for c in choices
    ]


@pytest.mark.parametrize("merit", [None, *replacing_merits()])
def test_every_clans_starting_picks_can_all_be_placed(merit: str | None) -> None:
    short: list[str] = []
    for clan in clans():
        for label, sheet in sheets_for(clan):
            if merit is not None:
                sheet = [*sheet, SheetTrait(category="merits", name=merit, rating=3)]
            options = fillable(sheet)
            if len(options) < picks(sheet):
                short.append(f"{label}: {options} for {picks(sheet)} picks")
    assert short == []


def test_a_clan_with_a_choice_has_too_few_until_it_is_made() -> None:
    sheet = [SheetTrait(category="clan", name="Baali: Angelis Ater")]
    assert sorted(fillable(sheet)) == ["Daimoinon", "Dominate"]
    assert picks(sheet) == 3
