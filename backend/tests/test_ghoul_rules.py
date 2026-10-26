"""The ghoul rule set (MET: VTM pp. 296–297): its costs, what it leaves out of the
vampire's catalogue, and the checks that keep a ghoul to its domitor."""

import re
from pathlib import Path

import pytest

from horatio.rules.checks import Context, violations
from horatio.rules.files import DATA_DIR, load_rule_set, names_left_out
from horatio.rules.model import RuleSetData, SheetTrait, TroupeRules
from horatio.rules.pricing import NotAllowed, purchase_cost, trait_cost
from horatio.rules.splats import SPLATS


@pytest.fixture(scope="module")
def ghoul() -> RuleSetData:
    return load_rule_set(DATA_DIR / "bns_met_ghoul.toml")


@pytest.fixture(scope="module")
def vampire() -> RuleSetData:
    return load_rule_set(DATA_DIR / "bns_met_vampire.toml")


def toreador(*traits: SheetTrait) -> list[SheetTrait]:
    return [SheetTrait("clan", "Toreador"), *traits]


def dots(category: str, name: str, rating: int, free: int = 0) -> SheetTrait:
    return SheetTrait(category, name, rating, free_rating=free)


def broken(rule_set: RuleSetData, sheet: list[SheetTrait], **context: object) -> list[str]:
    rules = TroupeRules(rule_set)
    native = frozenset(SPLATS[rule_set.splat].in_clan(rules, sheet))
    found = violations(
        rules.checks(),
        sheet,
        Context(
            in_clan=native,
            native=native,
            kinds=rule_set.kinds,
            tags=rule_set.tags,
            **context,  # type: ignore[arg-type]
        ),
    )
    return [v.check.key for v in found]


# --- costs (p. 296) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("category", "name", "rating", "expected"),
    [
        # An attribute, 3 XP a dot.
        ("attributes", "Physical", 2, 6),
        # A skill or background, the new level × 1.
        ("skills", "Brawl", 3, 1 + 2 + 3),
        ("backgrounds", "Resources", 2, 1 + 2),
        # A merit, its rating.
        ("merits", "Lucky", 2, 2),
        # A flaw gives its rating back, as a vampire's does.
        ("flaws", "Amnesia", 1, -1),
    ],
)
def test_what_a_ghoul_pays(
    ghoul: RuleSetData, category: str, name: str, rating: int, expected: int
) -> None:
    trait = dots(category, name, rating)

    assert trait_cost(TroupeRules(ghoul), toreador(trait), trait).cost == expected


def test_a_skill_dot_costs_its_new_level(ghoul: RuleSetData) -> None:
    brawl = dots("skills", "Brawl", 3)

    assert purchase_cost(TroupeRules(ghoul), toreador(brawl), brawl, 4).cost == 4


def test_disciplines_cannot_be_bought_with_xp(ghoul: RuleSetData) -> None:
    auspex = dots("disciplines", "Auspex", 2, free=2)
    rules = TroupeRules(ghoul)

    # The dots placed at creation are free...
    assert trait_cost(rules, toreador(auspex), auspex).cost == 0
    # ...and no more can be bought, in-clan or not.
    with pytest.raises(NotAllowed):
        purchase_cost(rules, toreador(auspex), auspex, 3)
    potence = dots("disciplines", "Potence", 0)
    with pytest.raises(NotAllowed):
        purchase_cost(rules, toreador(potence), potence, 1)


def test_in_clan_is_the_domitors_clans(ghoul: RuleSetData) -> None:
    facts = SPLATS["ghoul"].facts
    rules = TroupeRules(ghoul)
    sheet = toreador()

    assert facts(rules, sheet, dots("disciplines", "Auspex", 1))["in_clan"] is True
    assert facts(rules, sheet, dots("disciplines", "Potence", 1))["in_clan"] is False
    tremere = [SheetTrait("clan", "Tremere")]
    path = SheetTrait("disciplines", "Thaumaturgy: Path of Blood", 1)
    assert facts(rules, tremere, path)["in_clan"] is True
    assert "generation" not in facts(rules, tremere, path)


# --- what a ghoul does not have --------------------------------------------------------


def test_no_generation_humanity_paths_or_elder_powers(ghoul: RuleSetData) -> None:
    assert ("backgrounds", "Generation") not in ghoul.traits
    assert ("paths", "Humanity") not in ghoul.traits
    for category in (
        "paths",
        "techniques",
        "elder_disciplines",
        "luminary_disciplines",
        "extra_in_clan_disciplines",
    ):
        assert category not in ghoul.categories
        assert all(c != category for c, _ in ghoul.traits)
    assert all(s.name != "Humanity" for s in ghoul.starting_traits)
    # Nor anything about them: the check that a vampire needs a dot of Generation,
    # or a Path merit's grant of its Path.
    assert not any(names_left_out(c.requires, [{"category": "paths"}]) for c in ghoul.checks)
    assert all(g.kind != "convert" for g in ghoul.grants)
    assert all(c.get("name") != "Generation" for c in ghoul.creation_only)


def test_the_rest_of_the_catalogue_is_the_vampires(
    ghoul: RuleSetData, vampire: RuleSetData
) -> None:
    left_out = {"paths", "techniques", "elder_disciplines", "luminary_disciplines"}
    left_out.add("extra_in_clan_disciplines")
    kept = {
        k for k in vampire.traits if k[0] not in left_out and k != ("backgrounds", "Generation")
    }

    assert set(ghoul.traits) == kept
    assert ghoul.traits[("clan", "Toreador")].properties["in_clan"] == [
        "Auspex",
        "Celerity",
        "Presence",
    ]
    assert set(ghoul.action_kinds) == set(vampire.action_kinds)


def test_the_vampires_checks_keep_their_keys(ghoul: RuleSetData, vampire: RuleSetData) -> None:
    """A troupe's house strength for a check is kept by its key, for every splat."""
    vampire_checks = {c.key: c for c in vampire.checks}

    for check in ghoul.checks:
        if not check.key.startswith("ghoul/"):
            assert vampire_checks[check.key] == check


def test_a_leave_out_that_leaves_out_nothing_is_refused(tmp_path: Path) -> None:
    # The ghoul's file elsewhere, its included files named in full, and a misspelling.
    source = re.sub(
        r'"(bns_met_\w+\.toml)"',
        lambda m: f'"{DATA_DIR / m.group(1)}"',
        (DATA_DIR / "bns_met_ghoul.toml").read_text(),
    )
    path = tmp_path / "ghoul.toml"
    path.write_text(source.replace('name = "Generation"', 'name = "Generashun"'))

    with pytest.raises(ValueError, match="leaves out nothing"):
        load_rule_set(path)


# --- checks ------------------------------------------------------------------------------


def test_never_more_than_five_discipline_dots(ghoul: RuleSetData) -> None:
    five = toreador(dots("disciplines", "Auspex", 3), dots("disciplines", "Celerity", 2))
    six = toreador(dots("disciplines", "Auspex", 3), dots("disciplines", "Celerity", 3))

    assert "ghoul/disciplines/five-dots" not in broken(ghoul, five)
    assert "ghoul/disciplines/five-dots" in broken(ghoul, six)


def test_disciplines_are_the_domitors_in_clan_ones(ghoul: RuleSetData) -> None:
    assert "ghoul/disciplines/in-clan" not in broken(
        ghoul, toreador(dots("disciplines", "Auspex", 1))
    )
    assert "ghoul/disciplines/in-clan" in broken(ghoul, toreador(dots("disciplines", "Potence", 1)))
    # Once a home troupe accepts the ghoul, its staff answer for them.
    assert "ghoul/disciplines/in-clan" not in broken(
        ghoul, toreador(dots("disciplines", "Potence", 1)), accepted=True
    )


def test_only_powers_a_linked_domitor_has(ghoul: RuleSetData) -> None:
    sheet = toreador(dots("disciplines", "Auspex", 3))
    key = "ghoul/disciplines/domitor-powers"

    assert key in broken(ghoul, sheet, domitor_clan="Toreador", domitor_powers={"Auspex": 2})
    assert key not in broken(ghoul, sheet, domitor_clan="Toreador", domitor_powers={"Auspex": 3})
    # With no domitor linked, staff check the powers.
    assert key not in broken(ghoul, sheet)


def test_the_clan_is_the_linked_domitors(ghoul: RuleSetData) -> None:
    key = "ghoul/clan/domitor"

    assert key not in broken(ghoul, toreador(), domitor_clan="Toreador", domitor_powers={})
    assert key in broken(ghoul, toreador(), domitor_clan="Brujah", domitor_powers={})
    assert key not in broken(ghoul, toreador())


@pytest.mark.parametrize(
    ("category", "name", "key"),
    [
        # About the vampiric condition (tagged in the catalogue).
        ("merits", "Calm Heart", "ghoul/merits/vampire-only"),
        ("merits", "Unbondable", "ghoul/merits/vampire-only"),
        ("flaws", "Beast in the Mirror", "ghoul/flaws/vampire-only"),
        ("flaws", "Thin Blooded", "ghoul/flaws/vampire-only"),
        # A Morality merit.
        ("merits", "Path of Caine", "ghoul/merits/morality"),
        # The domitor's clan's own merits and flaws are for vampires of the clan.
        ("merits", "Absent Sway", "ghoul/merits/clan"),
        ("flaws", "Toreador: Obsession", "ghoul/flaws/clan"),
    ],
)
def test_merits_and_flaws_a_ghoul_cannot_take(
    ghoul: RuleSetData, category: str, name: str, key: str
) -> None:
    assert (category, name) in ghoul.traits
    trait = dots(category, name, ghoul.traits[(category, name)].properties["rating"])

    assert key in broken(ghoul, toreador(trait))


@pytest.mark.parametrize(
    "name",
    # The bloodline and rarity merits its domitor's clan needs (p. 296), and a general one.
    ["Bloodline: Ishtarri", "Uncommon Clan", "Lucky"],
)
def test_merits_a_ghoul_can_take(ghoul: RuleSetData, name: str) -> None:
    trait = dots("merits", name, ghoul.traits[("merits", name)].properties["rating"])

    assert not [k for k in broken(ghoul, toreador(trait)) if k.startswith("ghoul/")]


def test_a_vampire_is_not_held_to_the_ghouls_checks(vampire: RuleSetData) -> None:
    calm = dots("merits", "Calm Heart", 1)

    assert not [k for k in broken(vampire, toreador(calm)) if k.startswith("ghoul/")]
    assert vampire.tags[("merits", "Calm Heart")] == frozenset({"vampire_only"})
