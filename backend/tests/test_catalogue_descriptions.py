"""Every trait a player chooses from a list says what it is (issues #31, #42)."""

import re
import tomllib
from collections import Counter
from typing import Any

from horatio.rules.files import DATA_DIR, load_rule_set

DESCRIBED = (
    "attributes",
    "focus_physicals",
    "focus_socials",
    "focus_mentals",
    "skills",
    "backgrounds",
    "disciplines",
    "merits",
    "flaws",
)


def test_every_trait_players_choose_has_a_description() -> None:
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")

    missing = sorted(
        f"{category}: {name}"
        for (category, name), trait in rules.traits.items()
        if category in DESCRIBED and not trait.description
    )
    assert missing == []


# Not in the core book's list (p. 87), which invites players to make their own:
# they came with the Yorick catalogue, so they have no page to give.
NOT_IN_THE_BOOK = {("archetype", "Hedonist"), ("archetype", "Hunter")}


def test_every_skill_and_archetype_says_what_it_does_and_where() -> None:
    """Skills give their System and archetypes their line from the book, each
    with a real page, for the Play View's Sheet tab (issue #212)."""
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    found = {key: trait for key, trait in rules.traits.items() if key[0] in ("skills", "archetype")}

    missing = sorted(
        f"{category}: {name}"
        for (category, name), trait in found.items()
        if not trait.description
        or (
            (category, name) not in NOT_IN_THE_BOOK
            and not (trait.page_reference or "")[:1].isdigit()
        )
    )
    assert missing == []


TRAITS_FILE = DATA_DIR / "bns_met_vampire_traits.toml"
# Where the page is not MET: VTM's: "Vol. 2, p. 269", "Vol. 2 Issue 1, pp. 34, 41".
PAGE = re.compile(r"(?:Vol\. 2(?: Issue 1)?, pp?\. )?\d+(?:(?:-|, )\d+)?")
# Wording that stands in for a description rather than giving one (issue #315).
PLACEHOLDERS = {"clan flaw for a second caste", "tbd", "todo", "description"}


def test_every_clan_and_bloodline_gives_its_write_ups_page() -> None:
    """The wizard's clan choices show where the book describes each one (issue #1113)."""
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")

    unplaced = sorted(
        name
        for (category, name), trait in rules.traits.items()
        if category == "clan" and not PAGE.fullmatch(trait.page_reference or "")
    )
    assert unplaced == []
    # The core book's write-up, not Volume 2's page that changes only the weakness.
    assert rules.traits["clan", "Tremere"].page_reference == "61"
    assert rules.traits["clan", "Gangrel: Anda"].page_reference == "Vol. 2, p. 31"


def merits_and_flaws() -> list[dict[str, Any]]:
    """As the file has them: the loader keeps no `unsourced`."""
    with TRAITS_FILE.open("rb") as f:
        return [t for t in tomllib.load(f)["traits"] if t["category"] in ("merits", "flaws")]


def test_every_merit_and_flaw_says_what_it_does_in_its_own_words() -> None:
    """No empty or placeholder description, and none shared by more than two: a pair
    is two merits that do the same (Kupala's Bounty and Thaumaturgically Gifted)."""
    traits = merits_and_flaws()
    wording = Counter((t.get("description") or "").strip().lower() for t in traits)

    unsaid = sorted(
        f"{t['category']}: {t['name']}"
        for t in traits
        if (said := (t.get("description") or "").strip().lower()) in PLACEHOLDERS | {""}
        or wording[said] > 2
    )
    assert unsaid == []


def test_no_trait_is_listed_twice_under_names_that_differ_only_by_the() -> None:
    """ "Blood of Tzimisce" and "Blood of the Tzimisce" were one merit listed twice, so
    creation offered it twice (#811). Two traits of a category whose names are the
    same but for "the" are one trait, spelt one way: the book's."""
    with TRAITS_FILE.open("rb") as f:
        traits = tomllib.load(f)["traits"]

    def bare(name: str) -> str:
        return " ".join(w for w in name.lower().split() if w != "the")

    names: dict[tuple[str, str], set[str]] = {}
    for t in traits:
        names.setdefault((t["category"], bare(t["name"])), set()).add(t["name"])

    assert sorted(sorted(n) for n in names.values() if len(n) > 1) == []


def test_every_merit_and_flaw_gives_its_page_or_says_why_not() -> None:
    """The checks, grants and wizard cite a trait's page; one that no book we have
    describes says so in `unsourced` instead (issue #315)."""
    traits = merits_and_flaws()

    unplaced = sorted(
        f"{t['category']}: {t['name']}"
        for t in traits
        if not (
            PAGE.fullmatch(t.get("page_reference", ""))
            if "page_reference" in t
            else (t.get("unsourced") or "").strip()
        )
        or ("page_reference" in t and "unsourced" in t)
    )
    assert unplaced == []


def test_each_merit_and_flaw_is_listed_once_as_the_book_spells_it() -> None:
    names = {(t["category"], t["name"]) for t in merits_and_flaws()}

    for misspelt in (
        ("flaws", "Followers of Set: Temperment of Storms"),
        ("merits", "Thaumaturgical Expertise"),
        ("flaws", "Daughters of Cacophany: No Encore"),
        ("merits", "No Place Like.Home"),
    ):
        assert misspelt not in names


def test_every_technique_elder_and_luminary_power_says_what_it_does_and_where() -> None:
    """A player reads what a power does before taking it (issue #1000): its cost,
    action, test and effect in a line of our own, and the book's page."""
    with TRAITS_FILE.open("rb") as f:
        powers = [
            t
            for t in tomllib.load(f)["traits"]
            if t["category"] in ("techniques", "elder_disciplines", "luminary_disciplines")
        ]

    unsaid = sorted(
        f"{t['category']}: {t['name']}"
        for t in powers
        if not (t.get("description") or "").strip()
        or not PAGE.fullmatch(t.get("page_reference", ""))
    )
    assert unsaid == []


# The Dark Thaumaturgy rituals come from the V20 LARP SRD, whose page is a link.
SRD_RITUAL = re.compile(r"https://www\.oneworldofdarkness\.com/srd-v20/rituals/[a-z0-9-]+")


def test_every_ritual_says_what_it_does_and_where() -> None:
    """A player reads what a ritual does before learning it (issue #1024): its cost,
    casting time, test and effect in a line of our own, and the book's page. The
    Sabbat's ritae too, which the NPC builder lists among them."""
    with TRAITS_FILE.open("rb") as f:
        rituals = [
            t for t in tomllib.load(f)["traits"] if t["category"] in ("rituals", "sabbat_rituals")
        ]

    unsaid = sorted(
        f"{t['category']}: {t['name']}"
        for t in rituals
        if not (t.get("description") or "").strip()
        or not (
            PAGE.fullmatch(page := t.get("page_reference", ""))
            or (t["name"].startswith("Dark Thaumaturgy: ") and SRD_RITUAL.fullmatch(page))
        )
    )
    assert rituals and unsaid == []
