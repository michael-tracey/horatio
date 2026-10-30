"""The merits a clan needs (MET: VTM pp. 237-238, #313): a bloodline's merit, and the
rarity merit its setting asks for, taken from the merit points while the character is
built, and given back when another clan is chosen."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.clan_merits import Setting, needed
from horatio.rules.files import DATA_DIR, load_rule_set
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_creation import FULL_BUILD, creation, pick

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def choose(person: Person, character_id: str, category: str, name: str) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": None},
    )


def merits(person: Person, character_id: str, names: list[str]) -> Any:
    return person.client.put(
        f"/characters/{character_id}/creation/categories/merits",
        json={"picks": [{"name": n} for n in names]},
    )


def clan_merits(state: dict[str, Any]) -> list[tuple[str, int]]:
    return [(m["name"], m["points"]) for m in state["clan_merits"]]


def budget(state: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in state["pools"] if p["category"] == "merits")


def held_merits(person: Person, character_id: str) -> dict[str, int]:
    traits = person.client.get(f"/characters/{character_id}/sheet").json()["traits"]
    return {t["name"]: t["rating"] for t in traits if t["category"] == "merits"}


def test_a_bloodline_takes_its_merit_from_the_points(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Gangrel: Coyote")

    state = creation(troupe.player, character_id)
    assert clan_merits(state) == [("Bloodline: Coyote", 2)]
    assert state["clan_merits"][0]["why"] == "Gangrel: Coyote is a bloodline."
    assert state["clan_merits"][0]["page"] == "238"
    # The clan's, not a pick: its points are used, but it is not among the picks.
    assert (budget(state)["used"], budget(state)["remaining"]) == (2, 5)
    assert budget(state)["traits"] == []
    assert held_merits(troupe.player, character_id) == {"Bloodline: Coyote": 2}

    # Saving the step's picks keeps it, and counts it.
    saved = merits(troupe.player, character_id, ["Code of Honor"])
    assert saved.status_code == 200, saved.text
    assert budget(saved.json())["used"] == 4
    over = merits(troupe.player, character_id, ["Code of Honor", "Rugged", "Calm Heart"])
    assert over.status_code == 409
    assert over.json()["detail"] == "That is 8 points, with the clan's 2; the budget is 7."

    # Another clan gives it back.
    assert choose(troupe.player, character_id, "clan", "Gangrel").status_code == 200
    state = creation(troupe.player, character_id)
    assert clan_merits(state) == []
    assert budget(state)["used"] == 2
    assert held_merits(troupe.player, character_id) == {"Code of Honor": 2}


def test_a_bloodline_that_does_not_fit_is_refused(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Tzimisce")
    saved = merits(troupe.player, character_id, ["Iron Will", "Code of Honor", "Lucky"])
    assert saved.status_code == 200, saved.text

    refused = choose(troupe.player, character_id, "clan", "Tzimisce: Koldun")

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Tzimisce: Koldun needs Bloodline: Koldun (4 points), which does not fit: 7 of the"
        " 7 merit points are spent on other merits. Take some off first, or choose another"
        " clan."
    )
    sheet = troupe.player.client.get(f"/characters/{character_id}/sheet").json()
    assert next(t["name"] for t in sheet["traits"] if t["category"] == "clan") == "Tzimisce"


def test_clan_merits_are_not_picked_or_taken_off_by_hand(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Gangrel")

    refused = merits(troupe.player, character_id, ["Bloodline: Noiad"])
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Bloodline: Noiad comes with its bloodline's clan: choose that clan instead."
    )

    assert choose(troupe.player, character_id, "clan", "Gangrel: Noiad").status_code == 200
    taken_off = troupe.player.client.post(
        f"/characters/{character_id}/creation/picks/remove",
        json={"category": "merits", "name": "Bloodline: Noiad"},
    )
    assert taken_off.status_code == 409
    assert taken_off.json()["detail"] == (
        "Bloodline: Noiad comes with the clan; choose another clan to take it off."
    )
    # Picking it again changes nothing.
    assert pick(troupe.player, character_id, "merits", "Bloodline: Noiad").status_code == 200
    assert held_merits(troupe.player, character_id) == {"Bloodline: Noiad": 2}


def test_the_setting_gives_the_rarity(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Lasombra")
    # With no sect yet, the rarity is the player's to pick.
    assert creation(troupe.player, character_id)["rarity_known"] is False
    assert clan_merits(creation(troupe.player, character_id)) == []

    assert choose(troupe.player, character_id, "sect", "Camarilla").status_code == 200

    state = creation(troupe.player, character_id)
    assert state["rarity_known"] is True
    assert state["clan_merits"] == [
        {
            "name": "Rare Clan",
            "points": 4,
            "why": "Lasombra is rare in the Camarilla setting.",
            "page": "403-404",
            "detail": "",
        }
    ]
    # In the Sabbat setting, Lasombra are common.
    assert choose(troupe.player, character_id, "sect", "Sabbat").status_code == 200
    assert clan_merits(creation(troupe.player, character_id)) == []
    assert held_merits(troupe.player, character_id) == {}


def test_a_troupe_of_one_sect_is_the_setting_and_names_its_own_rarities(troupe: Troupe) -> None:
    limited = troupe.lead.client.patch(f"/troupes/{troupe.id}", json={"allowed_sects": ["Sabbat"]})
    assert limited.status_code == 200, limited.text
    character_id = new_character(troupe, troupe.player, finished=False, clan="Tremere")
    built_here = troupe.player.client.put(
        f"/characters/{character_id}/building-troupe", json={"troupe_id": troupe.id}
    )
    assert built_here.status_code == 200, built_here.text
    # The Sabbat plays the Telyav as its Tremere, so the clan's own line is one step rarer.
    assert clan_merits(creation(troupe.player, character_id)) == [("Rare Clan", 4)]
    assert choose(troupe.player, character_id, "clan", "Tremere: Telyav").status_code == 200
    assert clan_merits(creation(troupe.player, character_id)) == [("Uncommon Clan", 2)]

    rarity = troupe.lead.client.get(f"/troupes/{troupe.id}/clan-rarity").json()
    assert rarity["setting"] == "Sabbat"
    assert rarity["sects"] == ["Anarch", "Camarilla", "Sabbat"]
    tremere = next(c for c in rarity["clans"] if c["clan"] == "Tremere")
    assert tremere == {
        "clan": "Tremere",
        "book": {"Anarch": "rare", "Camarilla": "common", "Sabbat": "uncommon"},
        "house": None,
    }
    assert next(c for c in rarity["clans"] if c["clan"] == "Lhiannan")["book"] == {
        "Anarch": "rare",
        "Camarilla": "rare",
        "Sabbat": "rare",
    }

    # A storyteller rates Tremere common here: the character built here follows.
    assert (
        troupe.player.client.put(
            f"/troupes/{troupe.id}/clan-rarity", json={"rarities": {"Tremere": "common"}}
        ).status_code
        == 403
    )
    named = troupe.lead.client.put(
        f"/troupes/{troupe.id}/clan-rarity", json={"rarities": {"Tremere": "common"}}
    )
    assert named.status_code == 200, named.text
    assert next(c for c in named.json()["clans"] if c["clan"] == "Tremere")["house"] == "common"
    assert clan_merits(creation(troupe.player, character_id)) == []
    assert held_merits(troupe.player, character_id) == {}
    bloodline = troupe.lead.client.put(
        f"/troupes/{troupe.id}/clan-rarity", json={"rarities": {"Tremere: Telyav": "rare"}}
    )
    assert bloodline.status_code == 422


def test_more_than_seven_points_is_restricted_clan(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Tzimisce: Koldun")
    assert choose(troupe.player, character_id, "sect", "Camarilla").status_code == 200

    state = creation(troupe.player, character_id)

    assert state["clan_merits"] == [
        {
            "name": "Restricted Clan",
            "points": 6,
            "why": "Tzimisce: Koldun would cost 8 merit points, Rare Clan (4) and Bloodline:"
            " Koldun (4), more than 7: Restricted Clan covers it.",
            "page": "237",
            "detail": "",
        }
    ]


def test_independent_bloodlines_carry_their_rarity(troupe: Troupe) -> None:
    lhiannan = new_character(troupe, troupe.player, "Brigid", finished=False, clan="Lhiannan")
    nagaraja = new_character(troupe, troupe.player, "Ankou", finished=False, clan="Nagaraja")

    assert clan_merits(creation(troupe.player, lhiannan)) == [("Rare Clan", 4)]
    assert clan_merits(creation(troupe.player, nagaraja)) == [("Uncommon Clan", 2)]


def test_finishing_with_a_clan_merit(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Toreador: Ishtarri")
    for category, name, rating in FULL_BUILD:
        if category == "disciplines":
            continue
        assert pick(troupe.player, character_id, category, name, rating).status_code == 200
    for name, rating in (("Celerity", 2), ("Fortitude", 1), ("Presence", 1)):
        assert pick(troupe.player, character_id, "disciplines", name, rating).status_code == 200

    done = troupe.player.client.post(f"/characters/{character_id}/creation/complete")

    assert done.status_code == 200, done.text
    assert held_merits(troupe.player, character_id) == {"Bloodline: Ishtarri": 2}
    # Once finished, the clan cannot change, and the merit stays.
    assert choose(troupe.player, character_id, "clan", "Toreador").status_code == 409


def test_the_book_tables() -> None:
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")

    def value(name: str) -> int:
        rating = rule_set.trait_properties("merits", name)["rating"]
        assert isinstance(rating, int)
        return rating

    def names(clan: str, sect: str | None) -> list[tuple[str, int]]:
        return [(m.name, m.points) for m in needed(rule_set, clan, Setting(sect), value)]

    # The Camarilla's default Assamites are Viziers (p. 403): they pay the clan's
    # rarity only, and the warrior caste a step more.
    assert names("Assamite: Vizier", "Camarilla") == [("Uncommon Clan", 2)]
    assert names("Assamite", "Camarilla") == [("Rare Clan", 4)]
    assert names("Assamite: Sorcerer", "Camarilla") == [
        ("Uncommon Clan", 2),
        ("Bloodline: Sorcerer", 4),
    ]
    # The book's own examples: a Lamia in the Camarilla is Restricted Clan (p. 237),
    # a true Cappadocian too (p. 238).
    assert names("Cappadocians: Lamia", "Camarilla") == [("Restricted Clan", 6)]
    assert names("Cappadocians", "Camarilla") == [("Restricted Clan", 6)]
    # The Sabbat's Gangrel are Coyote by default: free; a plain Gangrel pays 2 (p. 450).
    assert names("Gangrel: Coyote", "Sabbat") == []
    assert names("Gangrel", "Sabbat") == [("Uncommon Clan", 2)]
    # A clan the setting does not name is restricted (p. 404).
    assert names("Baali", "Camarilla") == [("Restricted Clan", 6)]
    # A default bloodline's merit is worth the 2 points one step rarer stands for, but
    # for the Carpathians' 3: a plain Tzimisce in the Camarilla pays 6, not 7.
    for (category, name), trait in rule_set.traits.items():
        if category == "clan" and trait.properties.get("default_in"):
            worth = 3 if name == "Tzimisce: Carpathian" else 2
            assert value(f"Bloodline: {name.split(': ')[1]}") == worth, name


def test_every_bloodline_has_its_merit() -> None:
    rule_set = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    for category, name in rule_set.traits:
        if category == "clan" and ":" in name:
            merit = f"Bloodline: {name.split(': ')[1]}"
            assert ("merits", merit) in rule_set.traits, name
