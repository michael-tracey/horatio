"""Merits that change a character's in-clan disciplines (Shadows of the Past, Blight of
the Ever-Hungry, Inceptor), and the order rituals are learned in. Plain sheets
against the rule set as loaded, and a few through the API."""

import uuid
from collections.abc import Callable, Sequence
from functools import cache
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import XpEntry
from horatio.rules.checks import Context, violations
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import NotAllowed, trait_cost
from horatio.rules.splats import SPLATS, vampire_in_clan_disciplines
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_creation import FULL_BUILD, creating, pick
from tests.test_api_creation_rules import give_xp
from tests.test_api_grants import take


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@cache
def rules() -> TroupeRules:
    return TroupeRules(load_rule_set(DATA_DIR / "bns_met_vampire.toml"))


def t(category: str, name: str, rating: int | None = 1) -> SheetTrait:
    return SheetTrait(category=category, name=name, rating=rating, free_rating=0)


def sheet_of(clan: str, *traits: SheetTrait) -> list[SheetTrait]:
    return [t("clan", clan, None), t("backgrounds", "Generation", 3), *traits]


def in_clan(sheet: Sequence[SheetTrait]) -> set[str]:
    return set(vampire_in_clan_disciplines(rules(), sheet))


def broken(sheet: Sequence[SheetTrait], about: str, accepted: bool = False) -> list[str]:
    """Messages of the checks the sheet breaks about the trait named `about`."""
    native = frozenset(SPLATS["vampire"].in_clan(rules(), sheet))
    context = Context(in_clan=native, native=native, accepted=accepted)
    found = violations(rules().checks(), sheet, context)
    return [v.message for v in found if v.subject.name == about]


def cost(sheet: Sequence[SheetTrait], category: str, name: str, rating: int) -> int | str:
    trait = t(category, name, rating)
    try:
        return trait_cost(rules(), [*sheet, trait], trait).cost
    except NotAllowed:
        return "not allowed"


# --- Blight of the Ever-Hungry (Vol. 2, p. 62) ---------------------------------------------


def test_a_nagaraja_is_in_clan_for_auspex_dominate_and_the_ash_path() -> None:
    assert in_clan(sheet_of("Nagaraja")) == {"Auspex", "Dominate", "Necromancy: Ash Path"}


def test_blight_makes_the_in_clan_disciplines_auspex_potence_and_the_graveborn() -> None:
    sheet = sheet_of("Nagaraja", t("merits", "Blight of the Ever-Hungry", 3))

    assert in_clan(sheet) == {"Auspex", "Potence", "Necromancy: Path of the Graveborn"}


def test_blight_prices_potence_in_clan_and_dominate_out_of_it() -> None:
    plain = sheet_of("Nagaraja")
    blighted = sheet_of("Nagaraja", t("merits", "Blight of the Ever-Hungry", 3))

    # In-clan new levels cost 3 each; out-of-clan 4.
    assert cost(plain, "disciplines", "Dominate", 2) == 9
    assert cost(plain, "disciplines", "Potence", 2) == 12
    assert cost(blighted, "disciplines", "Dominate", 2) == 12
    assert cost(blighted, "disciplines", "Potence", 2) == 9


def test_blight_changes_which_disciplines_a_checks_calls_in_clan() -> None:
    # Before a home troupe accepts the character, out-of-clan disciplines stop at 3 dots.
    plain = sheet_of("Nagaraja")
    blighted = sheet_of("Nagaraja", t("merits", "Blight of the Ever-Hungry", 3))

    assert broken([*plain, t("disciplines", "Dominate", 4)], "Dominate") == []
    assert broken([*plain, t("disciplines", "Potence", 4)], "Potence")
    assert broken([*blighted, t("disciplines", "Potence", 4)], "Potence") == []
    assert broken([*blighted, t("disciplines", "Dominate", 4)], "Dominate")


def test_blight_keeps_extra_in_clan_disciplines_on_top() -> None:
    sheet = sheet_of(
        "Nagaraja",
        t("merits", "Blight of the Ever-Hungry", 3),
        t("merits", "Iron Scales", 1),
        t("extra_in_clan_disciplines", "Fortitude", 1),
    )

    assert "Fortitude" in in_clan(sheet)


# --- Shadows of the Past (Vol. 2, p. 260) --------------------------------------------------


def test_shadows_of_the_past_makes_them_daimoinon_obtenebration_and_dominate() -> None:
    plain = sheet_of("Baali: Angelis Ater")
    shadowed = sheet_of("Baali: Angelis Ater", t("merits", "Shadows of the Past", 3))

    assert in_clan(plain) == {"Daimoinon", "Dominate"}
    assert in_clan(shadowed) == {"Daimoinon", "Obtenebration", "Dominate"}
    assert cost(plain, "disciplines", "Obtenebration", 2) == 12
    assert cost(shadowed, "disciplines", "Obtenebration", 2) == 9


def test_a_trait_that_is_not_the_merit_changes_nothing() -> None:
    sheet = sheet_of("Baali: Angelis Ater", t("merits", "Iron Will", 1))

    assert in_clan(sheet) == {"Daimoinon", "Dominate"}


def test_a_merit_held_at_no_dots_changes_nothing() -> None:
    sheet = sheet_of("Nagaraja", t("merits", "Blight of the Ever-Hungry", 0))

    assert in_clan(sheet) == {"Auspex", "Dominate", "Necromancy: Ash Path"}


# --- Inceptor (Vol. 2 Issue 1, p. 46) -------------------------------------------------------


def build(player: Person, character_id: str, skip: str) -> None:
    """Every pick of the usual build but those in `skip`."""
    for category, name, rating in FULL_BUILD:
        if category != skip:
            assert pick(player, character_id, category, name, rating).status_code == 200, name


def caitiff(*traits: SheetTrait) -> list[SheetTrait]:
    inceptor = t("merits", "Inceptor", 3)
    return sheet_of("Caitiff", inceptor, *traits)


def test_inceptor_lets_a_caitiff_pick_kineticism_as_in_clan() -> None:
    kineticism = t("extra_in_clan_disciplines", "Kineticism")

    assert broken(caitiff(kineticism), "Kineticism") == []
    assert broken(sheet_of("Caitiff", kineticism), "Kineticism")  # Without Inceptor.
    assert in_clan(caitiff(kineticism)) == {"Kineticism"}
    assert cost(caitiff(kineticism), "disciplines", "Kineticism", 2) == 9
    assert cost(sheet_of("Caitiff"), "disciplines", "Kineticism", 2) == 12


def test_inceptor_lets_a_caitiff_pick_a_path_as_in_clan() -> None:
    path = t("extra_in_clan_disciplines", "Thaumaturgy: Path of Blood", None)
    mortis = t("extra_in_clan_disciplines", "Necromancy: Mortis Path", None)

    assert broken(caitiff(path), path.name) == []
    assert broken(caitiff(mortis), mortis.name) == []
    assert broken(sheet_of("Caitiff", path), path.name)  # Without Inceptor.
    assert broken(sheet_of("Brujah", path), path.name)
    # The path is in-clan, so it can be learned and costs the in-clan rate.
    held = [path, t("disciplines", "Thaumaturgy: Path of Blood", 2)]
    assert broken(caitiff(*held), "Thaumaturgy: Path of Blood") == []
    assert cost(caitiff(path), "disciplines", "Thaumaturgy: Path of Blood", 2) == 9


def test_inceptor_gives_one_choice_only() -> None:
    kineticism = t("extra_in_clan_disciplines", "Kineticism")
    blood = t("extra_in_clan_disciplines", "Thaumaturgy: Path of Blood", None)
    conjuring = t("extra_in_clan_disciplines", "Thaumaturgy: Path of Conjuring", None)
    ash = t("extra_in_clan_disciplines", "Necromancy: Ash Path", None)
    plain = t("extra_in_clan_disciplines", "Auspex", None)

    # Another ordinary discipline is still one of the three.
    assert broken(caitiff(kineticism, plain), "Kineticism") == []
    assert broken(caitiff(blood, plain), blood.name) == []
    for first, second in ((kineticism, blood), (blood, conjuring), (blood, ash), (ash, kineticism)):
        assert broken(caitiff(first, second), first.name), (first.name, second.name)
        assert broken(caitiff(first, second), second.name), (first.name, second.name)


def test_a_path_from_inceptor_is_no_blood_magic() -> None:
    path = t("extra_in_clan_disciplines", "Thaumaturgy: Path of Blood", None)
    held = t("disciplines", "Thaumaturgy: Path of Blood", 1)
    ritual = t("rituals", "Thaumaturgy: Blood Mastery", 1)

    assert broken(caitiff(path, held, ritual), ritual.name)
    # With a path of their own as well, a Caitiff may.
    own = t("disciplines", "Thaumaturgy: Path of Conjuring", 1)
    assert broken(caitiff(path, held, own, ritual), ritual.name) == []
    # And a Caitiff with no Inceptor path never meets the check.
    assert broken(sheet_of("Caitiff", held, ritual), ritual.name) == []


def test_kineticism_is_learned_only_in_clan() -> None:
    kineticism = t("disciplines", "Kineticism", 1)

    message = "Kineticism is learned only by a Caitiff with Inceptor. (Vol. 2, p. 72)"
    assert broken(sheet_of("Brujah", kineticism), "Kineticism", accepted=True) == [message]
    assert broken(sheet_of("Caitiff", kineticism), "Kineticism", accepted=True) == [message]
    assert (
        broken(caitiff(t("extra_in_clan_disciplines", "Kineticism"), kineticism), "Kineticism")
        == []
    )


def test_other_clans_are_in_clan_as_they_were() -> None:
    assert in_clan(sheet_of("Brujah")) == {"Celerity", "Potence", "Presence"}
    assert in_clan(sheet_of("Caitiff")) == set()


# --- Vestiges of Greatness (p. 246) ---------------------------------------------------------

VESTIGES_MESSAGE = "Vestiges of Greatness gives one in-clan discipline from the uncommon list"
VESTIGES_NEEDS = "Vestiges of Greatness: choose one of your in-clan disciplines from Dementation"


def vestiges(*extra: str) -> list[SheetTrait]:
    return sheet_of(
        "Caitiff",
        t("merits", "Vestiges of Greatness", 3),
        *(t("extra_in_clan_disciplines", name) for name in extra),
    )


def test_vestiges_gives_two_common_and_one_uncommon() -> None:
    sheet = vestiges("Auspex", "Celerity", "Dementation")

    assert in_clan(sheet) == {"Auspex", "Celerity", "Dementation"}
    assert all(broken(sheet, name) == [] for name in ("Auspex", "Celerity", "Dementation"))
    assert broken(sheet, "Vestiges of Greatness") == []


def test_vestiges_refuses_a_second_uncommon_discipline() -> None:
    sheet = vestiges("Auspex", "Dementation", "Protean")

    assert any(VESTIGES_MESSAGE in m for m in broken(sheet, "Protean"))
    assert any(VESTIGES_MESSAGE in m for m in broken(sheet, "Dementation"))
    # The common one is not the problem.
    assert broken(sheet, "Auspex") == []


def test_vestiges_with_none_from_the_uncommon_list_is_flagged() -> None:
    sheet = vestiges("Auspex", "Celerity", "Potence")

    assert any(VESTIGES_NEEDS in m for m in broken(sheet, "Vestiges of Greatness"))


# --- one ritual of each level before the next (pp. 180, 202; Vol. 2, pp. 98, 132, 162) ------


@pytest.mark.parametrize(
    ("magic", "path", "ones", "twos", "message"),
    [
        (
            "Thaumaturgy",
            "Thaumaturgy: Path of Blood",
            "Thaumaturgy: Blood Mastery",
            "Thaumaturgy: Blood Walk",
            "A thaumaturge learns a ritual of each level before one of the next. (p. 202)",
        ),
        (
            "Necromancy",
            "Necromancy: Ash Path",
            "Necromancy: Call of the Hungry Dead",
            "Necromancy: Black Blood",
            "A necromancer learns a ritual of each level before one of the next. (p. 180)",
        ),
        (
            "Abyssal",
            "Obtenebration",
            "Abyssal: Abyssal Ichor",
            "Abyssal: Echoes in Darkness",
            "An Abyss Mystic learns a ritual of each level before one of the next. (Vol. 2, p. 98)",
        ),
    ],
)
def test_a_ritual_needs_one_of_the_level_before(
    magic: str, path: str, ones: str, twos: str, message: str
) -> None:
    levels = {n: rules().rule_set.trait_properties("rituals", n)["rating"] for n in (ones, twos)}
    assert levels == {ones: 1, twos: 2}, "pick one ritual of level 1 and one of level 2"
    one, two = t("rituals", ones, 1), t("rituals", twos, 2)
    base = [t("clan", "Tremere", None), t("disciplines", path, 2)]

    assert message in broken([*base, two], twos)
    assert message not in broken([*base, one, two], twos)
    # Level 1 needs nothing before it.
    assert message not in broken([*base, one], ones)


def test_level_3_needs_a_level_2_ritual_and_not_just_a_level_1() -> None:
    path = t("disciplines", "Thaumaturgy: Path of Blood", 3)
    one = t("rituals", "Thaumaturgy: Blood Mastery", 1)
    two = t("rituals", "Thaumaturgy: Blood Walk", 2)
    three = t("rituals", "Thaumaturgy: Firewalker", 3)
    assert rules().rule_set.trait_properties("rituals", three.name)["rating"] == 3
    message = "A thaumaturge learns a ritual of each level before one of the next. (p. 202)"

    assert message in broken([path, one, three], three.name)
    assert message not in broken([path, one, two, three], three.name)


def test_the_ritual_order_is_per_magic() -> None:
    path = t("disciplines", "Necromancy: Ash Path", 2)
    thaumaturgy_one = t("rituals", "Thaumaturgy: Blood Mastery", 1)
    two = t("rituals", "Necromancy: Black Blood", 2)

    assert "A necromancer learns a ritual of each level before one of the next. (p. 180)" in broken(
        [path, thaumaturgy_one, two], two.name
    )


def test_a_sorcerous_dabbler_without_thaumaturgy_chooses_one_level() -> None:
    dabbler = t("merits", "Sorcerous Dabbler", 2)
    two = t("rituals", "Thaumaturgy: Blood Walk", 2)
    message = "A thaumaturge learns a ritual of each level before one of the next. (p. 202)"

    assert message not in broken([dabbler, two], two.name)
    # With Thaumaturgy of their own the order applies again.
    path = t("disciplines", "Thaumaturgy: Path of Blood", 2)
    assert message in broken([dabbler, path, two], two.name)


# --- through the API -----------------------------------------------------------------------


def test_a_caitiff_with_inceptor_picks_kineticism_and_pays_in_clan(troupe: Troupe) -> None:
    character_id = creating(troupe, clan="Caitiff")
    player = troupe.player

    refused = take(player, character_id, "extra_in_clan_disciplines", "Kineticism")
    assert refused.status_code == 409
    assert "only from its list" in refused.json()["detail"]

    assert pick(player, character_id, "merits", "Inceptor", 3).status_code == 200
    taken = take(player, character_id, "extra_in_clan_disciplines", "Kineticism")
    assert taken.status_code == 200, taken.text
    second = take(player, character_id, "extra_in_clan_disciplines", "Thaumaturgy: Path of Blood")
    assert second.status_code == 409
    assert "Kineticism or one path" in second.json()["detail"]

    unavailable = player.client.post(
        f"/characters/{character_id}/unavailable",
        json={"categories": ["extra_in_clan_disciplines"], "changes": []},
    ).json()["extra_in_clan_disciplines"]
    assert "Kineticism" not in unavailable  # Held.
    assert "Thaumaturgy: Path of Blood" in unavailable
    assert "Necromancy: Mortis Path" in unavailable
    assert "Auspex" not in unavailable


def test_the_add_panel_offers_kineticism_to_a_caitiff_only_with_inceptor(troupe: Troupe) -> None:
    character_id = creating(troupe, clan="Caitiff")
    player = troupe.player

    def kineticism_reason() -> Any:
        return (
            player.client.post(
                f"/characters/{character_id}/unavailable",
                json={"categories": ["extra_in_clan_disciplines"], "changes": []},
            )
            .json()["extra_in_clan_disciplines"]
            .get("Kineticism")
        )

    assert kineticism_reason() is not None
    assert pick(player, character_id, "merits", "Inceptor", 3).status_code == 200
    assert kineticism_reason() is None


def test_blight_changes_what_a_nagaraja_pays_through_the_api(troupe: Troupe) -> None:
    character_id = creating(troupe, clan="Nagaraja")
    player = troupe.player

    def quote(name: str) -> int:
        return player.client.post(
            f"/characters/{character_id}/quote",
            json={"category": "disciplines", "name": name, "rating": 2},
        ).json()["cost"]

    before = (quote("Dominate"), quote("Potence"))
    blight = pick(player, character_id, "merits", "Blight of the Ever-Hungry", 3)
    assert blight.status_code == 200, blight.text
    after = (quote("Dominate"), quote("Potence"))

    assert (before, after) == ((9, 12), (12, 9))


def test_a_ritual_of_level_2_is_refused_until_one_of_level_1_is_held(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player, clan="Tremere")
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="award",
            amount=100,
            reason="Test",
            entered_by=uuid.UUID(troupe.custodian.id),
        )
    )
    troupe.session.flush()
    take(troupe.player, character_id, "disciplines", "Thaumaturgy: Path of Blood", 2)

    refused = take(troupe.player, character_id, "rituals", "Thaumaturgy: Blood Walk", 2)

    assert refused.status_code == 409
    assert "each level before one of the next" in refused.json()["detail"]
    assert (
        take(troupe.player, character_id, "rituals", "Thaumaturgy: Blood Mastery", 1).status_code
        == 200
    )
    assert (
        take(troupe.player, character_id, "rituals", "Thaumaturgy: Blood Walk", 2).status_code
        == 200
    )


def test_two_uncommon_disciplines_with_vestiges_are_refused(troupe: Troupe) -> None:
    character_id = creating(troupe, clan="Caitiff")
    player = troupe.player
    assert pick(player, character_id, "merits", "Vestiges of Greatness", 3).status_code == 200

    assert take(player, character_id, "extra_in_clan_disciplines", "Dementation").status_code == 200
    refused = take(player, character_id, "extra_in_clan_disciplines", "Protean")

    assert refused.status_code == 409
    assert VESTIGES_MESSAGE in refused.json()["detail"]


def test_vestiges_without_an_uncommon_discipline_cannot_finish(troupe: Troupe) -> None:
    character_id = creating(troupe, clan="Caitiff")
    player = troupe.player
    for name in ("Auspex", "Celerity", "Potence"):
        assert take(player, character_id, "extra_in_clan_disciplines", name).status_code == 200
    assert pick(player, character_id, "merits", "Vestiges of Greatness", 3).status_code == 200
    build(player, character_id, skip="disciplines")
    for name, rating in (("Celerity", 2), ("Auspex", 1), ("Potence", 1)):
        assert pick(player, character_id, "disciplines", name, rating).status_code == 200

    problems = player.client.get(f"/characters/{character_id}/sheet").json()["problems"]
    flagged = next(p for p in problems if p["name"] == "Vestiges of Greatness")
    refused = player.client.post(f"/characters/{character_id}/creation/complete")

    assert flagged["strength"] == "complete"
    # It says what it looks at, so the wizard can show it where in-clan disciplines are chosen.
    assert {"category": "extra_in_clan_disciplines", "name": None} in flagged["looks_at"]
    assert refused.status_code == 409
    assert VESTIGES_NEEDS in refused.json()["detail"]


def test_the_starting_disciplines_follow_merits_that_change_what_is_in_clan(
    troupe: Troupe,
) -> None:
    character_id = creating(troupe, clan="Nagaraja")
    player = troupe.player
    build(player, character_id, skip="disciplines")
    # The Ash Path's pick is left for later: out of clan, a path needs a merit for it.
    for name, rating in (("Dominate", 2), ("Auspex", 1)):
        assert pick(player, character_id, "disciplines", name, rating).status_code == 200

    def at(rating: int) -> dict[str, Any]:
        pools = player.client.get(f"/characters/{character_id}/creation").json()["pools"]
        return next(p for p in pools if p["category"] == "disciplines" and p["rating"] == rating)

    assert at(2)["options"] == ["Auspex", "Dominate", "Necromancy: Ash Path"]
    # Blight of the Ever-Hungry sets the in-clan disciplines (Vol. 2, p. 62): Dominate's
    # dots are kept, but no longer fit.
    blight = pick(player, character_id, "merits", "Blight of the Ever-Hungry", 3)
    assert blight.status_code == 200, blight.text

    assert at(2)["options"] == ["Auspex", "Necromancy: Path of the Graveborn", "Potence"]
    assert at(2)["traits"] == [
        {"name": "Dominate", "detail": "", "pick": 2, "fits": False, "because": [], "freed_by": []}
    ]


def test_a_merit_that_gives_a_discipline_in_clan_opens_its_starting_dots(troupe: Troupe) -> None:
    character_id = creating(troupe, clan="Followers of Set: Vipers")
    player = troupe.player

    def options() -> list[str]:
        pools = player.client.get(f"/characters/{character_id}/creation").json()["pools"]
        return next(p for p in pools if p["category"] == "disciplines")["options"]

    assert "Fortitude" not in options()
    assert pick(player, character_id, "merits", "Iron Scales", 2).status_code == 200
    assert "Fortitude" in options()


# --- merits whose point is an in-clan discipline the player chooses (#216) -----------------

COMMON_THREE = ["Auspex", "Celerity", "Potence"]


def cart(player: Person, character_id: str, changes: list[dict[str, Any]], dry_run: bool) -> Any:
    out = player.client.post(
        f"/characters/{character_id}/cart", json={"changes": changes, "dry_run": dry_run}
    )
    assert out.status_code == 200, out.text
    return out.json()


def swap(player: Person, character_id: str, out: str, to: str, dry_run: bool = False) -> Any:
    """What the Concept step's in-clan picker sends to swap one choice for another."""
    change = {"kind": "set", "category": "extra_in_clan_disciplines", "detail": "", "teacher": ""}
    return cart(
        player,
        character_id,
        [{**change, "name": out, "rating": 0}, {**change, "name": to, "rating": 1}],
        dry_run,
    )


def making_room(player: Person, character_id: str, name: str) -> Any:
    """What the in-clan picker offers to swap out for `name`."""
    out = player.client.get(
        f"/characters/{character_id}/making-room",
        params={"category": "extra_in_clan_disciplines", "name": name},
    )
    assert out.status_code == 200, out.text
    return out.json()


def ready_to_finish(troupe: Troupe, clan: str, in_clan: Sequence[str]) -> str:
    """A character with every pick placed: the usual build, its in-clan choices, and
    starting dots on three of its in-clan disciplines."""
    character_id = creating(troupe, clan=clan)
    player = troupe.player
    for name in in_clan:
        assert take(player, character_id, "extra_in_clan_disciplines", name).status_code == 200
    build(player, character_id, skip="disciplines")
    options = next(
        p["options"]
        for p in player.client.get(f"/characters/{character_id}/creation").json()["pools"]
        if p["category"] == "disciplines"
    )
    for name, rating in zip(sorted(options), (2, 1, 1), strict=False):
        assert pick(player, character_id, "disciplines", name, rating).status_code == 200, name
    return character_id


def finish(player: Person, character_id: str) -> Any:
    return player.client.post(f"/characters/{character_id}/creation/complete")


def move_dot(player: Person, character_id: str, out: str, to: str) -> None:
    """Moves the starting dots on a discipline swapped out, as the Disciplines step does."""
    state = player.client.get(f"/characters/{character_id}/creation").json()
    picks = [
        {"name": to if t["name"] == out else t["name"], "rating": p["rating"]}
        for p in state["pools"]
        if p["category"] == "disciplines"
        for t in p["traits"]
    ]
    moved = player.client.put(
        f"/characters/{character_id}/creation/categories/disciplines", json={"picks": picks}
    )
    assert moved.status_code == 200, moved.text


@pytest.mark.parametrize(
    ("merit", "to"),
    [
        ("Vestiges of Greatness", "Dementation"),
        ("Inceptor", "Kineticism"),
        ("Inceptor", "Necromancy: Mortis Path"),
    ],
)
def test_a_caitiff_merit_that_changes_one_of_the_three_blocks_finishing_until_swapped_in(
    troupe: Troupe, merit: str, to: str
) -> None:
    character_id = ready_to_finish(troupe, "Caitiff", COMMON_THREE)
    player = troupe.player
    assert pick(player, character_id, "merits", merit, 3).status_code == 200

    refused = finish(player, character_id)
    assert refused.status_code == 409
    assert f"{merit}: choose" in refused.json()["detail"]
    # All three are chosen, so the new one is refused alone, but swaps in for any of them.
    alone = take(player, character_id, "extra_in_clan_disciplines", to)
    assert alone.status_code == 409
    assert "Caitiff choose three" in alone.json()["detail"]
    for out in COMMON_THREE:
        tried = swap(player, character_id, out, to, dry_run=True)
        assert all(line["refused"] is None for line in tried["lines"]), (out, tried)
    # The picker is offered the same swaps, asked all at once.
    assert making_room(player, character_id, to) == COMMON_THREE

    assert swap(player, character_id, "Auspex", to)["applied"]
    # The starting dot on Auspex is kept until it moves (the Disciplines step).
    assert "Auspex" in finish(player, character_id).json()["detail"]
    if not to.startswith("Necromancy: "):
        move_dot(player, character_id, "Auspex", to)
        assert finish(player, character_id).status_code == 200


def test_vestiges_refuses_a_second_uncommon_swap(troupe: Troupe) -> None:
    character_id = ready_to_finish(troupe, "Caitiff", COMMON_THREE)
    player = troupe.player
    assert pick(player, character_id, "merits", "Vestiges of Greatness", 3).status_code == 200
    assert swap(player, character_id, "Auspex", "Dementation")["applied"]

    lines = swap(player, character_id, "Celerity", "Protean", dry_run=True)["lines"]
    assert any(VESTIGES_MESSAGE in (line["refused"] or "") for line in lines)
    # In place of the first, it is allowed.
    lines = swap(player, character_id, "Dementation", "Protean", dry_run=True)["lines"]
    assert all(line["refused"] is None for line in lines)
    # The picker offers that one swap alone.
    assert making_room(player, character_id, "Protean") == ["Dementation"]
    # Nothing is offered for one already held, nor one the rule set does not have.
    assert making_room(player, character_id, "Dementation") == []
    unknown = player.client.get(
        f"/characters/{character_id}/making-room",
        params={"category": "extra_in_clan_disciplines", "name": "Juggling"},
    )
    assert unknown.status_code == 404


@pytest.mark.parametrize(
    ("clan", "in_clan", "merit", "points", "to", "not_on_its_list"),
    [
        ("Brujah", [], "Additional Common Discipline", 4, "Auspex", "Protean"),
        ("Brujah", [], "Additional Uncommon Discipline", 5, "Protean", "Auspex"),
        ("Nosferatu", [], "Pliable Blood", 3, "Dementation", "Animalism"),
        ("Caitiff", COMMON_THREE, "Additional Common Discipline", 4, "Dominate", "Kineticism"),
        ("Caitiff", COMMON_THREE, "Additional Uncommon Discipline", 5, "Quietus", "Vicissitude"),
    ],
)
def test_a_merit_that_adds_an_in_clan_discipline_blocks_finishing_until_it_is_chosen(
    troupe: Troupe,
    clan: str,
    in_clan: list[str],
    merit: str,
    points: int,
    to: str,
    not_on_its_list: str,
) -> None:
    character_id = ready_to_finish(troupe, clan, in_clan)
    player = troupe.player
    assert pick(player, character_id, "merits", merit, points).status_code == 200

    refused = finish(player, character_id)
    assert refused.status_code == 409
    assert f"{merit}: choose the in-clan discipline it adds." in refused.json()["detail"]
    assert (
        take(player, character_id, "extra_in_clan_disciplines", not_on_its_list).status_code == 409
    )

    assert take(player, character_id, "extra_in_clan_disciplines", to).status_code == 200
    # The one it adds starts without a free dot, so nothing moves.
    assert finish(player, character_id).status_code == 200, finish(player, character_id).text


def test_a_merit_that_adds_one_bought_after_creation_is_not_held_back(troupe: Troupe) -> None:
    character_id = ready_to_finish(troupe, "Brujah", [])
    player = troupe.player
    assert finish(player, character_id).status_code == 200
    give_xp(troupe, character_id, 20)
    merit = {"kind": "set", "category": "merits", "name": "Additional Common Discipline"}

    bought = cart(player, character_id, [{**merit, "detail": "", "rating": 4}], dry_run=True)

    assert [line["refused"] for line in bought["lines"]] == [None]


def test_bonds_of_stolen_vitae_is_taken_with_its_discipline_chosen(troupe: Troupe) -> None:
    character_id = ready_to_finish(troupe, "Gargoyles", [])
    player = troupe.player

    unchosen = pick(player, character_id, "merits", "Bonds of Stolen Vitae", 2)
    assert unchosen.status_code == 409
    assert "Say which for Bonds of Stolen Vitae" in unchosen.json()["detail"]
    chosen = player.client.put(
        f"/characters/{character_id}/creation/picks",
        json={
            "category": "merits",
            "name": "Bonds of Stolen Vitae",
            "rating": 2,
            "detail": "Protean",
        },
    )
    assert chosen.status_code == 200, chosen.text

    assert "Protean" in in_clan_now(player, character_id)
    assert finish(player, character_id).status_code == 200


def in_clan_now(player: Person, character_id: str) -> list[str]:
    pools = player.client.get(f"/characters/{character_id}/creation").json()["pools"]
    return next(p["options"] for p in pools if p["category"] == "disciplines")
