"""The rule set's data from the supplements (MET: VTM Volume 2 Issue 1 and Volume
2): technique prerequisites, ritual levels, clans for merits and flaws, and the
new bloodlines. Checked on plain sheets against the rule set as loaded."""

from collections.abc import Sequence
from functools import cache

from horatio.rules.checks import Context, violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import RuleSetData, SheetTrait


@cache
def rules() -> RuleSetData:
    return load_rule_set(DATA_DIR / "bns_met_vampire.toml")


def t(category: str, name: str, rating: int | None = 1) -> SheetTrait:
    return SheetTrait(category=category, name=name, rating=rating, free_rating=0)


def clan(name: str) -> SheetTrait:
    return t("clan", name, None)


def broken(sheet: Sequence[SheetTrait], about: str) -> list[str]:
    """Messages of the checks the sheet breaks about the trait named `about`."""
    in_clan = frozenset(
        d
        for c in sheet
        if c.category == "clan"
        for d in rules().trait_properties("clan", c.name).get("in_clan", [])
    )
    found = violations(rules().checks, sheet, Context(in_clan=in_clan, native=in_clan))
    return [v.message for v in found if v.subject.name == about]


def checks_about(category: str, name: str) -> list[str]:
    return [c.message for c in rules().checks if c.category == category and c.name == name]


# --- techniques --------------------------------------------------------------------------


def test_every_technique_has_its_prerequisites() -> None:
    techniques = {n for (c, n) in rules().traits if c == "techniques"}
    checked = {c.name for c in rules().checks if c.category == "techniques"}

    assert techniques - checked == set()


def test_core_techniques_each_have_their_own_prerequisites() -> None:
    """Two core checks had been filed under the technique before them."""
    assert checks_about("techniques", "Telepathic Directive") == [
        "Telepathic Directive needs Auspex 4 and Dominate 1."
    ]
    assert sorted(checks_about("techniques", "Retain the Quick Blood")) == [
        "Diluted Blood bars Retain the Quick Blood.",
        "Retain the Quick Blood needs Quietus 2 and Celerity 2.",
    ]
    assert checks_about("techniques", "Will to Survive") == [
        "Will to Survive needs Fortitude 1 and Presence 1."
    ]
    assert checks_about("techniques", "Unnatural Grace") == [
        "Unnatural Grace needs Celerity 1, Fortitude 1 and Presence 1."
    ]


def test_a_supplement_technique_needs_its_disciplines() -> None:
    bullet_time = t("techniques", "Bullet Time")

    short = broken(
        [bullet_time, t("disciplines", "Temporis", 2), t("disciplines", "Auspex")], "Bullet Time"
    )
    assert short == ["Bullet Time needs Temporis 3 and Auspex 1. (Vol. 2 Issue 1, p. 62)"]
    assert (
        broken(
            [bullet_time, t("disciplines", "Temporis", 3), t("disciplines", "Auspex")],
            "Bullet Time",
        )
        == []
    )


def test_either_or_prerequisites() -> None:
    coven = t("techniques", "Press-Ganged Coven")
    dominate = t("disciplines", "Dominate", 4)

    assert broken([coven, dominate], "Press-Ganged Coven")
    assert (
        broken(
            [coven, dominate, t("disciplines", "Necromancy: Bone Path", 3)], "Press-Ganged Coven"
        )
        == []
    )
    assert (
        broken(
            [coven, dominate, t("disciplines", "Thaumaturgy: Path of Blood", 3)],
            "Press-Ganged Coven",
        )
        == []
    )
    cat = t("techniques", "That Damn Cat")
    dementation = t("disciplines", "Dementation", 2)
    assert broken([cat, dementation, t("disciplines", "Animalism", 3)], "That Damn Cat")
    assert broken([cat, dementation, t("disciplines", "Protean", 4)], "That Damn Cat") == []


# --- rituals --------------------------------------------------------------------------------


def test_every_ritual_has_a_level() -> None:
    unlevelled = [
        n
        for (c, n), tr in rules().traits.items()
        if c == "rituals" and "rating" not in tr.properties
    ]

    assert unlevelled == []


def test_core_ritual_levels_follow_the_book() -> None:
    def level(name: str) -> int:
        return rules().trait_properties("rituals", name)["rating"]

    # Necromancy pp. 182-184, Thaumaturgy pp. 208-209.
    assert level("Necromancy: Spirit Beacon") == 3
    assert level("Necromancy: Rise, Cerberus") == 3
    assert level("Necromancy: Lethe's Waters") == 4
    assert level("Thaumaturgy: Mirror Walk") == 4
    assert level("Thaumaturgy: Scry") == 4
    assert level("Thaumaturgy: Severed Hand") == 4
    # And from Volume 2.
    assert level("Abyssal: Avatar of Screams") == 5
    assert level("Thaumaturgy: Canopic Jar (Setite)") == 2


def test_abyss_mysticism_needs_walk_the_abyss_and_obtenebration() -> None:
    ritual = t("rituals", "Abyssal: Echoes in Darkness", 2)
    first = t("rituals", "Abyssal: Abyssal Ichor", 1)
    walk = t("merits", "Walk the Abyss", 3)

    assert broken(
        [clan("Lasombra"), first, ritual, t("disciplines", "Obtenebration", 2)], ritual.name
    ) == ["Abyss Mysticism needs the Lasombra merit Walk the Abyss. (Vol. 2, p. 98)"]
    assert broken(
        [clan("Lasombra"), first, ritual, walk, t("disciplines", "Obtenebration", 1)], ritual.name
    ) == ["A level 2 Abyss Mysticism ritual needs Obtenebration 2 or more. (Vol. 2, p. 99)"]
    assert (
        broken(
            [clan("Lasombra"), first, ritual, walk, t("disciplines", "Obtenebration", 2)],
            ritual.name,
        )
        == []
    )


# --- Dark Thaumaturgy (the V20 LARP SRD, issue #414) ----------------------------------------

SRD_RULES = "https://www.oneworldofdarkness.com/srd-v20/thaumaturgy/dark-thaumaturgy"
DARK_LEVELS = {
    "Apport Object": 1,
    "Fragments of the Forgotten": 1,
    "Knotted Chord": 1,
    "Scribing the Unknown": 1,
    "Terrorize": 1,
    "Whispers of Chaos": 1,
    "Allies Below": 2,
    "Fires of the Inferno": 2,
    "Horrifying Spectacle": 2,
    "Learn the Heart's Pain": 2,
    "Recrimination": 2,
    "Blade of the Forgotten": 3,
    "Mutual Damnation": 3,
    "Nightmares of the Subconscious": 3,
    "Waves of Agony": 3,
    "Fool the Heart's Eye": 4,
    "Suppression of the Outward Soul": 4,
    "Vile Swarm": 4,
    "Call Forth the Host": 5,
    "House the Maeljin": 5,
}


def dark(name: str) -> SheetTrait:
    return t("rituals", f"Dark Thaumaturgy: {name}", DARK_LEVELS[name])


def test_the_dark_thaumaturgy_rituals_are_a_family_at_the_srds_levels() -> None:
    found = {
        n.removeprefix("Dark Thaumaturgy: "): trait
        for (c, n), trait in rules().traits.items()
        if c == "rituals" and n.startswith("Dark Thaumaturgy: ")
    }
    assert {n: trait.properties["rating"] for n, trait in found.items()} == DARK_LEVELS
    for trait in found.values():
        assert trait.description
        assert (trait.page_reference or "").startswith(
            "https://www.oneworldofdarkness.com/srd-v20/rituals/"
        )
    assert {c.page for c in rules().checks if c.name_prefix == "Dark Thaumaturgy: "} == {SRD_RULES}


def test_dark_thaumaturgy_needs_thaumaturgy_and_evil_revelations_or_infernal_power() -> None:
    ritual = dark("Apport Object")
    path = t("disciplines", "Thaumaturgy: Path of Blood", 1)
    needs = (
        "Dark Thaumaturgy needs a path of Thaumaturgy and the Path of Evil Revelations,"
        " or Infernal Power. (V20 LARP SRD)"
    )

    assert broken([clan("Tremere"), path, ritual], ritual.name) == [needs]
    assert needs in broken(
        [clan("Tremere"), t("merits", "Path of Evil Revelations", 3), ritual], ritual.name
    )
    assert (
        broken(
            [clan("Tremere"), path, t("merits", "Path of Evil Revelations", 3), ritual], ritual.name
        )
        == []
    )
    # Infernal Power, or Infernal Heritage which includes it, opens them with no path.
    assert broken([clan("Brujah"), t("merits", "Infernal Power", 3), ritual], ritual.name) == []
    assert broken([clan("Baali"), t("merits", "Infernal Heritage", 1), ritual], ritual.name) == []


def test_a_dark_thaumaturgy_ritual_is_no_higher_than_the_path_but_through_infernal_power() -> None:
    revelations = t("merits", "Path of Evil Revelations", 3)
    first = dark("Apport Object")
    second = dark("Allies Below")

    def sheet(*more: SheetTrait, dots: int = 1) -> list[SheetTrait]:
        return [
            clan("Tremere"),
            revelations,
            t("disciplines", "Thaumaturgy: Path of Blood", dots),
            *more,
        ]

    assert broken(sheet(first, second), second.name) == [
        "A level 2 Dark Thaumaturgy ritual needs a path of Thaumaturgy at 2 or more,"
        " or Infernal Power. (V20 LARP SRD)"
    ]
    assert broken(sheet(first, second, dots=2), second.name) == []
    assert broken(sheet(first, second, t("merits", "Infernal Power", 3)), second.name) == []
    # Infernal Power's rituals stop at level 4: a level 5 one needs the path at 5.
    four, five = dark("Vile Swarm"), dark("Call Forth the Host")
    infernal = [clan("Brujah"), t("merits", "Infernal Power", 3)]
    assert broken([*infernal, dark("Waves of Agony"), four], four.name) == []
    assert broken([*infernal, four, five], five.name) == [
        "A level 5 Dark Thaumaturgy ritual needs a path of Thaumaturgy at 5 or more. (V20 LARP SRD)"
    ]
    assert broken(sheet(four, five, dots=5), five.name) == []


def test_a_dark_thaumaturgy_ritual_follows_one_of_either_kind_a_level_lower() -> None:
    base = [clan("Tremere"), t("merits", "Path of Evil Revelations", 3)]
    base.append(t("disciplines", "Thaumaturgy: Path of Blood", 3))
    blade = dark("Blade of the Forgotten")
    lower = (
        "Above level 1, a Dark Thaumaturgy ritual needs a Thaumaturgy ritual, of either kind,"
        " one level lower. (V20 LARP SRD)"
    )

    assert broken([*base, blade], blade.name) == [lower]
    # A level 1 is not enough for a level 3: it must be one level lower.
    assert broken([*base, dark("Terrorize"), blade], blade.name) == [lower]
    assert broken([*base, dark("Recrimination"), blade], blade.name) == []
    assert broken([*base, t("rituals", "Thaumaturgy: Blood Walk", 2), blade], blade.name) == []


def test_ritual_master_doubles_the_clans_own_rituals() -> None:
    path = t("disciplines", "Thaumaturgy: Path of Blood", 1)
    two = [
        t("rituals", "Thaumaturgy: Blood Mastery", 1),
        t("rituals", "Thaumaturgy: Warding Circle", 1),
    ]
    master = t("merits", "Ritual Master")

    assert broken([clan("Tremere"), path, *two], two[0].name)
    assert broken([clan("Tremere"), path, master, *two], two[0].name) == []
    # A Giovanni's Ritual Master is for Necromancy, not Thaumaturgy.
    assert broken([clan("Giovanni"), path, master, *two], two[0].name)
    assert broken([clan("Brujah"), master], "Ritual Master") == [
        "Ritual Master is only for Giovanni and Tremere. (Vol. 2 Issue 1, p. 34)"
    ]


# --- merits, flaws and bloodlines ----------------------------------------------------------


def test_supplement_clan_merits_are_for_their_clan_or_bloodline() -> None:
    timely = t("merits", "Timely Intervention")

    assert broken([clan("Brujah"), timely], timely.name)
    assert broken([clan("Brujah: True Brujah"), timely], timely.name) == []
    assert rules().trait_properties("merits", "Inceptor")["rating"] == 3
    # The Salubri warrior caste's merits are not for Healers.
    sight = t("merits", "Sight Beyond Sight")
    assert broken([clan("Salubri"), sight], sight.name) == []
    assert broken([clan("Salubri: Healer"), sight], sight.name)


def test_alternative_clan_flaws_are_for_their_clan() -> None:
    fetish = t("flaws", "Malkavian: Feeding Fetish")

    assert broken([clan("Toreador"), fetish], fetish.name)
    assert broken([clan("Malkavian"), fetish], fetish.name) == []
    assert (
        broken(
            [clan("Cappadocians: Samedi"), t("flaws", "Cappadocian: Falling Apart", 3)],
            "Cappadocian: Falling Apart",
        )
        == []
    )
    assert broken(
        [clan("Brujah: True Brujah"), t("flaws", "Brujah: Coldly Logical")],
        "Brujah: Coldly Logical",
    )


def test_volume_2_bloodlines_are_clans_with_their_merits() -> None:
    assert rules().trait_properties("clan", "Gangrel: Anda")["in_clan"] == [
        "Animalism",
        "Potence",
        "Protean",
    ]
    assert "Thaumaturgy: Green Path" in rules().trait_properties("clan", "Lhiannan")["in_clan"]
    toys = t("merits", "All the Best Toys", 2)
    assert broken([clan("Gangrel"), toys], toys.name)
    assert broken([clan("Gangrel: Anda"), toys], toys.name) == []
    # Lhiannan merits were recorded for the bloodline before it was a clan here.
    woads = t("merits", "Runic Woads")
    assert broken([clan("Gangrel"), woads], woads.name)
    assert broken([clan("Lhiannan"), woads], woads.name) == []


def test_flaws_that_bar_other_traits() -> None:
    carrion = t("flaws", "Baali: Carrion Comfort", 2)

    assert broken([clan("Baali"), carrion, t("backgrounds", "Herd")], "Herd") == [
        "Carrion Comfort bars the Herd background. (Vol. 2, p. 281)"
    ]
