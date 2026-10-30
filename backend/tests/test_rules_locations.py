"""The Stock Location catalogue's file (horatio.rules.locations): it reads, its
parts fit together, and what its suggested requirements name is in the rule set."""

import tomllib

import pytest

from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.locations import (
    LOCATIONS_FILE,
    catalogue_from,
    elysium_qualities,
    load_catalogue,
    played,
)


def test_every_suggested_trait_and_power_is_in_the_rule_set() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    names = {n for (_, n) in rules.traits}
    for q in load_catalogue().qualities:
        for s in q.suggested:
            for trait in (s.trait, *s.traits):
                if trait:
                    assert trait in names, (q.name, trait)
            if s.power:
                discipline = s.power.split(": ")[0]
                assert discipline in names, (q.name, s.power)


def test_house_options_change_the_catalogue() -> None:
    catalogue = load_catalogue()
    book = played(catalogue, set(catalogue.options))
    house = played(catalogue, set())
    assert "Library" in book.qualities and "Library" not in house.qualities
    assert book.qualities["Laboratory"].option is None
    assert house.qualities["Laboratory"].option == "two_laboratories"
    assert house.min_rating == {"Fancy": 4, "Lowdown and Dirty": 4}
    assert book.min_rating == {} and book.per_qualities == {}


def test_an_elysium_gains_qualities_with_time() -> None:
    assert [elysium_qualities(y) for y in (0, 9, 10, 99, 100, 250)] == [1, 1, 2, 2, 3, 4]


def test_a_quality_from_an_unknown_option_is_refused() -> None:
    with LOCATIONS_FILE.open("rb") as f:
        raw = tomllib.load(f)
    raw["qualities"].append({"name": "Moat", "kind": "standard", "text": "x", "option": "nope"})
    with pytest.raises(ValueError, match="unknown option"):
        catalogue_from(raw)
