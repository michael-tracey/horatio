"""NPC kinds as rules data, and the Stock NPC rules (MET: VTM pp. 489–505)."""

import pytest

from horatio.rules.files import DATA_DIR, all_rule_set_files, load_rule_set
from horatio.rules.npc_kinds import NpcKind, Resource, custom_kind, npc_kinds, stock_blood
from horatio.rules.stock import Specialization, StockError, check, stat_block

VAMPIRE = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
SKILLS = {name for (category, name) in VAMPIRE.traits if category == "skills"}
DISCIPLINES = {name for (category, name) in VAMPIRE.traits if category == "disciplines"}
KINDS = npc_kinds()


def skill(name: str) -> Specialization:
    return Specialization("skill", name)


def power(name: str) -> Specialization:
    return Specialization("power", name)


def allowed(kind: str, rating: int, *specializations: Specialization) -> str | None:
    """None if the rules allow it, else the reason they do not."""
    try:
        check(KINDS[kind], rating, specializations, SKILLS, DISCIPLINES)
    except StockError as error:
        return str(error)
    return None


# --- the rules data --------------------------------------------------------------------


def test_every_kind_has_a_page_a_resource_and_a_nature() -> None:
    assert len(KINDS) >= 14
    for kind in KINDS.values():
        assert 489 <= kind.page <= 505, kind.key
        assert kind.to_page is None or kind.page < kind.to_page <= 505, kind.key
        assert kind.resource.name and kind.resource.size >= 1, kind.key
        assert kind.nature in ("mortal", "partly_mortal", "supernatural"), kind.key


def test_the_book_kinds_are_all_there() -> None:
    assert {
        "vampire",
        "ghoul",
        "mortal",
        "hunter_inquisition",
        "hunter_arcanum",
        "hunter_twilight",
        "werewolf",
        "mage",
        "fae",
        "wraith",
        "demon",
        "blood_brother",
        "lhiannan",
        "custom",
    } <= set(KINDS)
    assert [k.key for k in KINDS.values() if k.custom] == ["custom"]


def test_the_kinds_file_is_not_a_rule_set() -> None:
    assert "bns_met_npc_kinds.toml" not in [p.name for p in all_rule_set_files()]


def test_every_name_in_the_kinds_is_a_discipline_or_its_own_numina() -> None:
    for kind in KINDS.values():
        if kind.specializations != "any":
            for pattern in kind.specializations:
                found = (
                    any(d.startswith(pattern[:-1]) for d in DISCIPLINES)
                    if pattern.endswith(": *")
                    else pattern in DISCIPLINES
                )
                assert found, (kind.key, pattern)
        for p in kind.powers:
            if p.dots is not None:
                assert p.name in DISCIPLINES, (kind.key, p.name)
            if p.discipline is not None:
                assert p.discipline in DISCIPLINES, (kind.key, p.discipline)
        for n in kind.numina:
            assert n.name not in DISCIPLINES and len(n.levels) == 5, (kind.key, n.name)


@pytest.mark.parametrize(
    ("kind", "name", "size", "per_turn"),
    [
        ("werewolf", "Rage", 10, 3),
        ("mage", "Essence", 10, 3),
        ("fae", "Glamour", 10, 1),
        ("wraith", "Pathos", 10, 3),
        ("demon", "Faith", 10, 3),
        ("hunter_arcanum", "Mana", 5, 1),
        ("hunter_twilight", "Focus", 5, 1),
    ],
)
def test_each_kind_has_its_own_resource(kind: str, name: str, size: int, per_turn: int) -> None:
    resource = KINDS[kind].resource
    assert (resource.name, resource.size, resource.per_turn) == (name, size, per_turn)
    assert resource.regains


# --- Stock NPC rules (pp. 489–490) -----------------------------------------------------


def test_blood_is_5_for_mortals_and_ghouls_and_10_for_supernaturals() -> None:
    assert stock_blood("supernatural") == Resource("Blood", 10, 1)
    assert stock_blood("partly_mortal") == Resource("Blood", 5, 1)
    # Only ghouls can spend a mortal's Blood (p. 490).
    assert stock_blood("mortal") == Resource("Blood", 5, 0)
    assert KINDS["vampire"].resource == Resource("Blood", 10, 1)
    assert KINDS["ghoul"].resource == Resource("Blood", 5, 1)
    assert KINDS["mortal"].resource.size == 5
    assert KINDS["blood_brother"].resource.size == 10


def test_the_pool_is_twice_the_rating_and_5_more_with_a_skill() -> None:
    # The book's bartender, rating 3, Brawl (p. 489).
    stats = stat_block(KINDS["mortal"], 3, [skill("Brawl")])

    assert stats.pool == 6
    assert stats.skill_pools == (("Brawl", 11),)


def test_nemian_the_nosferatu() -> None:
    # The sample on p. 490.
    stats = stat_block(
        KINDS["vampire"],
        4,
        [skill("Brawl"), skill("Stealth"), power("Potence"), power("Obfuscate")],
    )

    assert stats.pool == 8
    assert dict(stats.skill_pools) == {"Brawl": 13, "Stealth": 13}
    assert dict(stats.powers) == {"Potence": 4, "Obfuscate": 4}
    assert stats.health == 4
    assert stats.resource == Resource("Blood", 10, 1)
    assert (stats.willpower, stats.retests) == (0, False)


def test_health_is_the_rating_or_twice_it_for_some_kinds() -> None:
    assert stat_block(KINDS["mortal"], 2, []).health == 2
    # A werewolf rated 3 has 6 health levels (p. 494).
    assert stat_block(KINDS["werewolf"], 3, []).health == 6
    # The Fearsome Courage gestalt, rating 8, has 16 (p. 504).
    assert stat_block(KINDS["blood_brother"], 8, []).health == 16


def test_discipline_dots_reach_the_rating_and_no_further_than_5() -> None:
    assert dict(stat_block(KINDS["ghoul"], 3, [power("Potence")]).powers) == {"Potence": 3}
    gestalt = stat_block(KINDS["blood_brother"], 8, [skill("Brawl"), skill("Melee")])
    assert gestalt.pool == 16
    assert dict(gestalt.skill_pools) == {"Brawl": 21, "Melee": 21}
    assert dict(gestalt.powers) == {"Celerity": 5, "Fortitude": 5, "Potence": 5}


def test_a_kinds_own_powers_come_with_it() -> None:
    # Wormwood, rating 2 (p. 503): 5 Daimoinon, Fortitude and Potence at 2.
    demon = stat_block(KINDS["demon"], 2, [skill("Subterfuge"), power("Chimerstry")])
    assert dict(demon.powers) == {"Daimoinon": 5, "Fortitude": 2, "Potence": 2, "Chimerstry": 2}
    assert demon.built_in == ()
    # Rated 4, it also has one Daimoinon elder power.
    assert [p.name for p in stat_block(KINDS["demon"], 4, []).built_in] == ["Daimoinon elder power"]
    # Every wraith has 2 Dementation; a specialization takes it higher (p. 500).
    assert dict(stat_block(KINDS["wraith"], 1, []).powers) == {"Dementation": 2}
    assert dict(stat_block(KINDS["wraith"], 3, [power("Dementation")]).powers) == {"Dementation": 3}
    werewolf = stat_block(KINDS["werewolf"], 2, [])
    assert [p.name for p in werewolf.built_in] == [
        "Feral Claws",
        "Shape of the Beast: fight form",
        "Shape of the Beast's Wrath",
    ]


def test_the_specializations_are_capped_at_the_rating() -> None:
    assert allowed("mortal", 2, skill("Brawl"), skill("Dodge")) is None
    assert "2 at most" in str(allowed("mortal", 2, skill("Brawl"), skill("Dodge"), skill("Melee")))
    assert "already" in str(allowed("mortal", 2, skill("Brawl"), skill("Brawl")))


def test_the_rating_is_1_to_5_or_higher_where_the_kind_allows() -> None:
    assert "rated 1 to 5" in str(allowed("vampire", 6))
    assert "rated 1 to 5" in str(allowed("vampire", 0))
    assert allowed("blood_brother", 8) is None
    assert allowed("blood_brother", 21) is not None


def test_mortals_cannot_take_discipline_specializations() -> None:
    assert allowed("mortal", 3, power("Potence")) == (
        "A mortal Stock NPC takes skill specialisations only (p. 489)."
    )
    assert allowed("ghoul", 3, power("Potence")) is None
    assert allowed("vampire", 3, power("Thaumaturgy: Path of Blood")) is None


def test_hunters_take_only_their_own_numina_and_powers() -> None:
    assert allowed("hunter_inquisition", 3, skill("Melee"), power("True Faith")) is None
    assert allowed("hunter_inquisition", 3, power("Potence")) is not None
    assert allowed("hunter_arcanum", 4, power("Thaumaturgy: Lure of Flames")) is None
    assert allowed("hunter_arcanum", 4, power("Thaumaturgy: Path of Blood")) is not None
    assert allowed("hunter_twilight", 3, power("Auspex")) is None
    # True Faith gives a dot a rating (p. 491).
    faith = stat_block(KINDS["hunter_inquisition"], 3, [power("True Faith")])
    assert dict(faith.powers) == {"True Faith": 3}


def test_supernaturals_take_the_disciplines_their_kind_lists() -> None:
    assert allowed("werewolf", 3, power("Obeah")) is None
    assert "cannot specialise in Dominate" in str(allowed("werewolf", 3, power("Dominate")))
    # A mage may take any path of Necromancy or Thaumaturgy (p. 496).
    assert allowed("mage", 2, power("Necromancy: Mortis Path")) is None
    assert allowed("mage", 2, power("Thaumaturgy: Path of Blood")) is None
    assert allowed("mage", 2, power("Potence")) is not None
    assert "not a skill" in str(allowed("vampire", 1, skill("Potence")))
    assert allowed("vampire", 1, power("Brawl")) is not None


def test_a_custom_kind_is_set_up_by_the_storyteller() -> None:
    base: NpcKind = KINDS["custom"]
    angel = custom_kind(base, "Angel", "supernatural", Resource("Grace", 7, 2, "at dawn"))
    hermit = custom_kind(base, "Hermit", "mortal", Resource("Blood", 5, 0))

    assert (angel.label, angel.resource.name) == ("Angel", "Grace")
    assert stat_block(angel, 3, []).resource == Resource("Grace", 7, 2, "at dawn")
    check(angel, 3, [power("Presence")], SKILLS, DISCIPLINES)
    with pytest.raises(StockError, match="skill specialisations only"):
        check(hermit, 3, [power("Presence")], SKILLS, DISCIPLINES)


def test_only_vampiric_kinds_have_the_beast_humanity_and_generation_panels() -> None:
    kinds = npc_kinds()

    for key in ("vampire", "ghoul", "blood_brother"):
        assert all(vars(kinds[key].panels).values()), key
    for key in ("mortal", "werewolf", "mage", "fae", "wraith", "demon", "hunter_arcanum", "custom"):
        assert not any(vars(kinds[key].panels).values()), key
