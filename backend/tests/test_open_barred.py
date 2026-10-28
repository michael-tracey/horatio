"""Merits that open one power the character's Generation bars (horatio.rules.grants,
open_barred): Hard as Steel, Trials of the Blood and Shrinking Violet (Vol. 2 Issue 1,
pp. 45 and 27; Vol. 2, p. 49). The power costs 20 XP (an elder power) or 12 (a
technique), the three Generation checks (p. 101) are set aside for it alone, and
everything else still applies."""

import pytest

from horatio.rules.checks import violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.grants import GrantData, opened, opening, set_aside, validate_grant
from horatio.rules.model import FreeChoice, SheetTrait, TroupeRules
from horatio.rules.pricing import NotAllowed, purchase_cost, trait_cost

RULES = TroupeRules(rule_set=load_rule_set(DATA_DIR / "bns_met_vampire.toml"))


def trait(category: str, name: str, rating: int | None = 1, **extra: object) -> SheetTrait:
    return SheetTrait(category=category, name=name, rating=rating, **extra)  # type: ignore[arg-type]


def vampire(clan: str, generation: int, *others: SheetTrait) -> list[SheetTrait]:
    return [
        trait("clan", clan, None),
        trait("backgrounds", "Generation", generation),
        *others,
    ]


def merit(name: str, *kept: tuple[str, str]) -> SheetTrait:
    """The merit, keeping the powers it opened, as (category, name)."""
    grant = next(g for g in RULES.rule_set.grants if g.source["name"] == name)
    return trait(
        "merits",
        name,
        3,
        choices=tuple(
            FreeChoice(
                grant=grant.key, name=n, amount=20 if c == "elder_disciplines" else 12, category=c
            )
            for c, n in kept
        ),
    )


def buying(sheet: list[SheetTrait], category: str, name: str) -> int:
    """What buying the trait's first dot costs."""
    return purchase_cost(RULES, sheet, trait(category, name, 0), 1).cost


def generation_checks(sheet: list[SheetTrait]) -> list[str]:
    """The Generation checks (p. 101) the sheet breaks, after what merits set aside,
    as messages about traits."""
    aside = set_aside(RULES, sheet)
    return [
        f"{v.subject.name}: {v.check.message}"
        for v in violations(RULES.checks(), sheet)
        if v.check.page == "101" and v.key not in aside
    ]


def crusader(*others: SheetTrait) -> list[SheetTrait]:
    """A Neonate Crusader with Fortitude 5."""
    return vampire("Ventrue: Crusader", 1, trait("disciplines", "Fortitude", 5), *others)


def test_a_neonate_buys_one_elder_power_for_20_xp() -> None:
    sheet = crusader(merit("Hard as Steel"))

    assert buying(sheet, "elder_disciplines", "Fortitude: Personal Armor") == 20
    found = opening(RULES, sheet, trait("elder_disciplines", "Fortitude: Personal Armor"))
    assert found is not None and found.because == "Hard as Steel: 20 XP"
    # Bought and kept on the merit, the Generation check is set aside for it.
    held = crusader(
        merit("Hard as Steel", ("elder_disciplines", "Fortitude: Personal Armor")),
        trait("elder_disciplines", "Fortitude: Personal Armor"),
    )
    assert generation_checks(held) == []
    assert trait_cost(RULES, held, held[-1]).cost == 20


def test_without_the_merit_a_neonate_still_cannot() -> None:
    sheet = crusader()

    with pytest.raises(NotAllowed):
        buying(sheet, "elder_disciplines", "Fortitude: Personal Armor")
    assert generation_checks([*sheet, trait("elder_disciplines", "Fortitude: Personal Armor")]) == [
        "Fortitude: Personal Armor: A Neonate's or Ancilla's blood is too thin for elder powers."
    ]


def test_one_purchase_only_and_never_the_luminary_power() -> None:
    sheet = crusader(
        merit("Hard as Steel", ("elder_disciplines", "Fortitude: Personal Armor")),
        trait("elder_disciplines", "Fortitude: Personal Armor"),
    )

    with pytest.raises(NotAllowed):
        buying(sheet, "elder_disciplines", "Fortitude: Resilient Mind")
    assert generation_checks([*sheet, trait("elder_disciplines", "Fortitude: Resilient Mind")]) == [
        "Fortitude: Resilient Mind: A Neonate's or Ancilla's blood is too thin for elder powers."
    ]
    unused = crusader(merit("Hard as Steel"))
    with pytest.raises(NotAllowed):
        buying(unused, "luminary_disciplines", "Fortitude: Indestructible")
    assert (
        opening(RULES, unused, trait("luminary_disciplines", "Fortitude: Indestructible")) is None
    )


def test_only_its_own_discipline() -> None:
    sheet = crusader(trait("disciplines", "Auspex", 5), merit("Hard as Steel"))

    with pytest.raises(NotAllowed):
        buying(sheet, "elder_disciplines", "Auspex: Clairvoyance")


def test_the_prerequisites_still_apply() -> None:
    sheet = vampire(
        "Ventrue: Crusader",
        1,
        trait("disciplines", "Fortitude", 4),
        merit("Hard as Steel", ("elder_disciplines", "Fortitude: Personal Armor")),
        trait("elder_disciplines", "Fortitude: Personal Armor"),
    )
    aside = set_aside(RULES, sheet)

    broken = [v.check.message for v in violations(RULES.checks(), sheet) if v.key not in aside]
    assert "An elder power needs all 5 dots of its discipline first." in broken


def test_a_power_the_generation_allows_leaves_the_merit_unused() -> None:
    # A Neonate learns techniques anyway, at the usual 12 XP: the merit is not spent.
    sheet = crusader(trait("disciplines", "Obtenebration", 3), merit("Hard as Steel"))

    assert opening(RULES, sheet, trait("techniques", "Armor of Darkness")) is None


def vizier(*others: SheetTrait) -> list[SheetTrait]:
    """A Pretender Elder Vizier with Auspex 5 and one Auspex elder power."""
    return vampire(
        "Assamite: Vizier",
        3,
        trait("disciplines", "Auspex", 5),
        trait("elder_disciplines", "Auspex: Clairvoyance"),
        *others,
    )


def test_a_pretender_elder_buys_a_second_elder_power_for_20_xp() -> None:
    sheet = vizier(merit("Trials of the Blood"))

    assert buying(sheet, "elder_disciplines", "Auspex: Fog of War") == 20
    held = vizier(
        merit("Trials of the Blood", ("elder_disciplines", "Auspex: Fog of War")),
        trait("elder_disciplines", "Auspex: Fog of War"),
    )
    # Neither the opened power nor the first breaks "only one elder power".
    assert generation_checks(held) == []
    # A third is refused, as a second is without the merit.
    third = [*held, trait("elder_disciplines", "Auspex: Psychic Assault")]
    assert "Auspex: Psychic Assault: A Pretender Elder can learn only one elder power." in (
        generation_checks(third)
    )


def test_without_the_merit_a_pretender_elder_has_one() -> None:
    sheet = vizier()

    # The cost rules sell it; the check refuses it.
    assert buying(sheet, "elder_disciplines", "Auspex: Fog of War") == 18
    assert "Auspex: Fog of War: A Pretender Elder can learn only one elder power." in (
        generation_checks([*sheet, trait("elder_disciplines", "Auspex: Fog of War")])
    )


def creep(*others: SheetTrait) -> list[SheetTrait]:
    """A Master Elder Creep with what Misleading Wounds needs, and Animal Succulence too."""
    return vampire(
        "Nosferatu: Creeps",
        4,
        trait("disciplines", "Obfuscate", 5),
        trait("disciplines", "Animalism", 5),
        trait("disciplines", "Fortitude", 5),
        *others,
    )


def test_a_master_elder_buys_a_technique_needing_obfuscate_for_12_xp() -> None:
    sheet = creep(merit("Shrinking Violet"))

    assert buying(sheet, "techniques", "Misleading Wounds") == 12
    held = creep(
        merit("Shrinking Violet", ("techniques", "Misleading Wounds")),
        trait("techniques", "Misleading Wounds"),
    )
    assert generation_checks(held) == []
    # One without Obfuscate is refused as before.
    with pytest.raises(NotAllowed):
        buying(sheet, "techniques", "Animal Succulence")


def test_without_the_merit_a_master_elder_learns_no_technique() -> None:
    with pytest.raises(NotAllowed):
        buying(creep(), "techniques", "Misleading Wounds")


def test_a_cart_power_not_yet_kept_uses_the_merit_up() -> None:
    # The sheet as a cart would leave it: one power bought, not yet kept on the merit.
    sheet = crusader(
        merit("Hard as Steel"), trait("elder_disciplines", "Fortitude: Personal Armor")
    )

    assert opened(RULES.rule_set, sheet) == {}
    assert opening(RULES, sheet, trait("elder_disciplines", "Fortitude: Resilient Mind")) is None


def test_a_grant_names_its_discipline_what_it_opens_and_the_checks() -> None:
    known = set(RULES.rule_set.traits)
    categories = set(RULES.rule_set.categories)
    good = next(g for g in RULES.rule_set.grants if g.kind == "open_barred")
    validate_grant(good, known, categories)

    for target, message in [
        ({**good.target, "discipline": "Nonsense"}, "must name the discipline"),
        ({**good.target, "opens": []}, "must say what it opens"),
        ({**good.target, "sets_aside": []}, "must name the checks"),
    ]:
        bad = GrantData(good.key, good.source, "open_barred", target, 1)
        with pytest.raises(ValueError, match=message):
            validate_grant(bad, known, categories)
