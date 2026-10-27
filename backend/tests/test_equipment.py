"""Equipment qualities (issue #279): every kind and quality of the book in the rules
data, with its effect and page, and the check refusing each rule between them."""

import tomllib
from typing import Any

import pytest

from horatio.equipment import EquipmentRefused, check
from horatio.rules.equipment import (
    EquipmentRules,
    Facts,
    ItemQuality,
    assess,
    equipment_from,
)
from horatio.rules.files import DATA_DIR, load_rule_set

EQUIPMENT_FILE = DATA_DIR / "bns_met_vampire_equipment.toml"
RULES = load_rule_set(DATA_DIR / "bns_met_vampire.toml").equipment

# The issue's table (MET: VTM pp. 516-521).
QUALITIES = {
    "melee": [
        "Accurate",
        "Antique",
        "Armor Piercing",
        "Artisan",
        "Balanced",
        "Brutal",
        "Cold Iron",
        "Concealable",
        "Deadly",
        "Disabling",
        "Fast",
        "Flaming",
        "Impaling",
        "Masterwork",
        "Quick Draw",
        "Reach",
        "Silver",
        "Staking",
        "Strange Composition",
        "Trip",
    ],
    "ranged": [
        "Accurate",
        "Ammo Capacity I",
        "Ammo Capacity II",
        "Antique",
        "Armor Piercing",
        "Artisan",
        "Automatic",
        "Brutal",
        "Cold Iron",
        "Concealable",
        "Deadly",
        "Fast",
        "Incendiary Ammunition",
        "Knockback",
        "Long Range",
        "Masterwork",
        "Quick Draw",
        "Rapid Reload",
        "Silver Ammunition",
        "Spread",
        "Staking",
        "Strange Composition",
    ],
    "protective": [
        "Ballistic",
        "Chest Plate",
        "Concealable",
        "Full Body",
        "Hardened",
        "HazMat",
        "Impact Absorption",
        "Rugged",
    ],
    "miscellaneous": [
        "Antique",
        "Artisan",
        "Concealable",
        "Customized",
        "Flashy",
        "Masterwork",
        "Nondescript",
        "Secure",
        "Streamlined",
        "Stylish",
        "Sturdy",
        "Superior",
    ],
}


def q(*names: str, **details: str) -> list[ItemQuality]:
    """Qualities by name; a detail by its name with spaces as underscores."""
    return [ItemQuality(n, details.get(n.replace(" ", "_"), "")) for n in names]


def problems(kind: str, qualities: list[ItemQuality], grade: str = "standard", **kw: Any) -> str:
    return " ".join(assess(RULES, kind, qualities, grade, **kw).problems)


def test_every_quality_of_the_book_is_in_the_data_and_nothing_more() -> None:
    for kind, names in QUALITIES.items():
        assert sorted(q.name for q in RULES.qualities_of(kind)) == sorted(names), kind
    assert len(RULES.qualities) == sum(len(n) for n in QUALITIES.values())


def test_every_quality_has_its_effect_and_page() -> None:
    for quality in RULES.qualities.values():
        assert quality.effect.endswith("."), quality
        assert quality.page, quality
    # The errata supersede p. 519.
    for name in ("Ballistic", "Hardened"):
        assert "Vol. II Issue 1, p. 23" in (RULES.qualities[("protective", name)].page or "")
    assert "firearms" in RULES.qualities[("protective", "Ballistic")].effect


def test_the_kinds_their_defaults_and_the_grades() -> None:
    assert list(RULES.kinds) == ["melee", "ranged", "protective", "miscellaneous"]
    melee, ranged = RULES.kinds["melee"], RULES.kinds["ranged"]
    assert (melee.hands, melee.damage, melee.shots) == (1, 1, None)
    assert (ranged.hands, ranged.damage, ranged.shots, ranged.range) == (1, 2, 12, "50 steps")
    assert RULES.kinds["protective"].hands is None
    assert {g.key: g.max_qualities for g in RULES.grades.values()} == {
        "cheap": 1,
        "standard": 2,
        "special": None,
    }


def test_the_properties_between_qualities() -> None:
    def of(kind: str, prop: str) -> set[str]:
        return {q.name for q in RULES.qualities_of(kind) if getattr(q, prop)}

    assert of("melee", "two_handed") == {"Brutal", "Reach"}
    assert of("ranged", "two_handed") == {
        "Brutal",
        "Long Range",
        "Ammo Capacity II",
        "Deadly",
        "Staking",
    }
    assert of("melee", "needs_one_hand") == of("ranged", "needs_one_hand")
    assert of("ranged", "needs_one_hand") == {"Concealable", "Quick Draw"}
    for kind in ("melee", "ranged", "miscellaneous"):
        assert of(kind, "no_slot_when_crafted") == {"Artisan", "Masterwork"}
    assert {q.name for q in RULES.qualities.values() if q.repeatable} == {"Superior"}
    needs_detail = {(q.kind, q.name) for q in RULES.qualities.values() if q.needs_detail}
    assert needs_detail == {
        ("melee", "Strange Composition"),
        ("ranged", "Strange Composition"),
        ("protective", "HazMat"),
        ("miscellaneous", "Customized"),
    }
    assert of("ranged", "ammo") == {"Silver Ammunition", "Incendiary Ammunition", "Cold Iron"}
    # Masterwork's story effect is optional.
    assert RULES.qualities[("melee", "Masterwork")].detail_prompt
    assert not RULES.qualities[("melee", "Masterwork")].needs_detail


def test_the_sample_items_are_templates() -> None:
    templates = {t.name: t for t in RULES.templates}
    assert len(templates) == 22
    assert templates["Katana"].qualities == tuple(q("Accurate", "Brutal"))
    assert templates["Silver Dagger"].qualities == tuple(q("Concealable", "Silver"))
    assert templates["Wooden Stake"].qualities == tuple(q("Concealable", "Staking"))
    assert templates["Shotgun"].qualities == tuple(q("Spread", "Accurate"))
    assert templates["Gaming Laptop"].qualities == tuple(
        q("Superior", "Customized", Customized="video games")
    )
    assert templates["Table-Leg Club (Improvised)"].grade == "cheap"


def test_the_ghoul_rule_set_has_the_same_equipment() -> None:
    assert load_rule_set(DATA_DIR / "bns_met_ghoul.toml").equipment == RULES


# --- the facts it works out -------------------------------------------------------------


def test_shotgun_spread_accurate_one_hand_and_six_shots() -> None:
    facts = check(RULES, "ranged", q("Spread", "Accurate"), "standard")
    assert facts == Facts(hands=1, damage=2, shots=6, range="50 steps")


def test_hands() -> None:
    assert check(RULES, "melee", q("Accurate", "Brutal"), "standard").hands == 2
    assert check(RULES, "melee", q("Deadly"), "standard").hands == 1  # melee Deadly: one hand
    assert check(RULES, "ranged", q("Deadly"), "standard").hands == 2  # ranged: two
    assert check(RULES, "ranged", q("Staking"), "standard").hands == 2
    assert check(RULES, "protective", q("Rugged"), "standard").hands is None


def test_shots() -> None:
    assert check(RULES, "ranged", [], "standard").shots == 12
    assert check(RULES, "ranged", q("Ammo Capacity I"), "standard").shots == 30
    assert check(RULES, "ranged", q("Ammo Capacity II"), "standard").shots == 100
    # Spread holds 6 unless it also has Ammo Capacity (p. 519).
    assert check(RULES, "ranged", q("Spread", "Ammo Capacity I"), "standard").shots == 30
    assert check(RULES, "ranged", q("Staking"), "standard").shots == 1
    assert check(RULES, "melee", q("Fast"), "standard").shots is None


def test_damage_and_range() -> None:
    sniper = check(RULES, "ranged", q("Accurate", "Long Range"), "standard")
    assert (sniper.damage, sniper.range) == (2, "half a mile")
    spear = check(RULES, "melee", q("Staking", "Reach"), "standard")
    assert (spear.damage, spear.range) == (1, "4 steps")
    dagger = check(RULES, "melee", q("Concealable", "Silver"), "standard")
    assert dagger.aggravated_against == ("werewolves and others vulnerable to silver",)
    jade = check(RULES, "melee", q("Strange Composition", Strange_Composition="jade"), "cheap")
    assert jade.aggravated_against == ("those vulnerable to jade, at the storyteller's discretion",)
    assert check(RULES, "miscellaneous", q("Superior"), "cheap").damage is None


# --- what it refuses ------------------------------------------------------------------


def test_refused_raises_with_every_problem() -> None:
    with pytest.raises(EquipmentRefused) as refused:
        check(RULES, "ranged", q("Long Range", "Quick Draw", "Spread"), "standard")
    assert refused.value.problems == (
        "Standard or expensive gear has at most 2 qualities, not 3.",
        "Long Range needs two hands, so it can't be Quick Draw.",
        "An item can't be both Long Range and Spread.",
    )


def test_how_many_qualities_by_grade() -> None:
    assert problems("melee", q("Accurate", "Fast"), "cheap") == (
        "Cheap gear has at most 1 quality, not 2."
    )
    assert problems("melee", q("Accurate"), "cheap") == ""
    assert problems("melee", q("Accurate", "Fast", "Silver")) == (
        "Standard or expensive gear has at most 2 qualities, not 3."
    )
    assert problems("melee", q("Accurate", "Fast")) == ""
    # A special item has no limit, but keeps the other rules.
    assert problems("melee", q("Accurate", "Fast", "Silver", "Trip", "Disabling"), "special") == ""
    assert problems("melee", q("Accurate", "Brutal", "Concealable"), "special") == (
        "Brutal needs two hands, so it can't be Concealable."
    )
    assert "grade" in problems("melee", q("Accurate"), "priceless")


def test_crafted_artisan_and_masterwork_take_no_slot() -> None:
    four = q("Accurate", "Fast", "Artisan", "Masterwork")
    assert problems("melee", four) == "Standard or expensive gear has at most 2 qualities, not 4."
    assert problems("melee", four, crafted=True) == ""
    assert problems("melee", q("Accurate", "Artisan"), "cheap", crafted=True) == ""
    assert problems("melee", q("Accurate", "Fast", "Silver"), crafted=True) != ""


def test_a_quality_of_another_kind() -> None:
    assert problems("ranged", q("Silver")) == "Silver isn't a ranged weapon quality."
    assert problems("protective", q("Superior")) == "Superior isn't a protective gear quality."
    assert problems("melee", q("Ballistic")) == "Ballistic isn't a melee weapon quality."
    assert (
        problems("ballistae", q("Accurate")) == "There's no kind of equipment called 'ballistae'."
    )


def test_a_repeat_only_of_a_repeatable_quality() -> None:
    assert problems("melee", q("Accurate", "Accurate")) == "Accurate can only be taken once."
    assert problems("miscellaneous", q("Superior", "Superior")) == ""
    # Each Superior takes a slot.
    assert problems("miscellaneous", q("Superior", "Superior", "Superior")) != ""


def test_a_missing_detail() -> None:
    assert problems("miscellaneous", q("Customized")) == (
        "Customized needs a detail: the circumstance, such as hacking."
    )
    assert problems("miscellaneous", q("Customized", Customized="  ")) != ""
    assert problems("miscellaneous", q("Customized", Customized="hacking")) == ""
    assert problems("protective", q("HazMat")) == "HazMat needs a detail: the hazard, such as heat."
    assert problems("protective", q("HazMat", HazMat="heat")) == ""
    for kind in ("melee", "ranged"):
        assert "needs a detail" in problems(kind, q("Strange Composition"))
    # Masterwork's story effect may be left out; a quality with no detail takes none.
    assert problems("melee", q("Masterwork")) == ""
    assert problems("melee", q("Masterwork", Masterwork="cuts chains")) == ""
    assert problems("melee", q("Accurate", Accurate="very")) == "Accurate takes no detail."


@pytest.mark.parametrize(
    ("kind", "two_handed"),
    [
        ("melee", "Brutal"),
        ("melee", "Reach"),
        ("ranged", "Brutal"),
        ("ranged", "Long Range"),
        ("ranged", "Ammo Capacity II"),
        ("ranged", "Deadly"),
        ("ranged", "Staking"),
    ],
)
def test_two_handed_is_never_concealable_or_quick_draw(kind: str, two_handed: str) -> None:
    for one_hand in ("Concealable", "Quick Draw"):
        assert problems(kind, q(two_handed, one_hand)) == (
            f"{two_handed} needs two hands, so it can't be {one_hand}."
        )
    assert problems(kind, q(two_handed)) == ""


def test_melee_deadly_can_be_concealable() -> None:
    assert problems("melee", q("Deadly", "Concealable")) == ""


@pytest.mark.parametrize(
    ("kind", "first", "second"),
    [
        ("ranged", "Automatic", "Spread"),
        ("ranged", "Spread", "Long Range"),
        ("protective", "Concealable", "Full Body"),
        ("ranged", "Staking", "Ammo Capacity I"),
    ],
)
def test_exclusions(kind: str, first: str, second: str) -> None:
    assert problems(kind, q(first, second), "special") == (
        f"An item can't be both {first} and {second}."
    )
    assert problems(kind, q(second, first), "special") == (
        f"An item can't be both {second} and {first}."
    )


def test_staking_cannot_take_ammo_capacity_ii() -> None:
    assert "can't be both Staking and Ammo Capacity II" in problems(
        "ranged", q("Staking", "Ammo Capacity II")
    )


# --- the data's own checks -------------------------------------------------------------


def raw_data() -> dict[str, Any]:
    with EQUIPMENT_FILE.open("rb") as f:
        return tomllib.load(f)


def with_quality(raw: dict[str, Any], kind: str, name: str, **changes: Any) -> dict[str, Any]:
    return {
        **raw,
        "qualities": [
            {**q, **changes} if (q["kind"], q["name"]) == (kind, name) else q
            for q in raw["qualities"]
        ],
    }


def test_loading_refuses_bad_data() -> None:
    raw = raw_data()
    assert isinstance(equipment_from(raw), EquipmentRules)
    with pytest.raises(ValueError, match="not the other way"):
        equipment_from(with_quality(raw, "ranged", "Spread", excludes=["Long Range"]))
    with pytest.raises(ValueError, match="unknown properties"):
        equipment_from(with_quality(raw, "melee", "Fast", two_hands=True))
    with pytest.raises(ValueError, match="needs a detail_prompt"):
        equipment_from(with_quality(raw, "melee", "Fast", needs_detail=True))
    with pytest.raises(ValueError, match="template 'Two-Handed Sword'"):
        equipment_from(with_quality(raw, "melee", "Accurate", needs_one_hand=True))
