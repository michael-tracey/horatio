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
