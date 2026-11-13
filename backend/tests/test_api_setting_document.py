"""The parts of a troupe's Setting Style Document built from its own settings (issue
#771): its setting and factions, clan rarity changes with their reasons, cost changes,
setting-specific mechanics and the New Character Incentive (MET: VTM pp. 331-336,
349); and the document on the troupe's profile when its storytellers show it."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_own_checks import OLD_BLOOD

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def generated(troupe: Troupe, person: Person | None = None) -> dict[str, Any]:
    response = (person or troupe.player).client.get(f"/troupes/{troupe.id}/setting")
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()["generated"]
    return found


def changed(troupe: Troupe, **body: Any) -> dict[str, Any]:
    response = troupe.lead.client.patch(f"/troupes/{troupe.id}", json=body)
    assert response.status_code == 200, response.text
    out: dict[str, Any] = response.json()
    return out


def log(troupe: Troupe) -> list[str]:
    return [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]


def test_a_troupe_as_the_book_has_it_keeps_the_settings_default(troupe: Troupe) -> None:
    assert generated(troupe) == {
        "sects": [],
        "setting": None,
        "clan_rarity": [],
        "costs": [],
        "initial_xp": 30,
        "incentive": None,
        "graduated": False,
        "mechanics": [],
    }


def test_one_sect_is_the_chronicles_setting_and_several_are_factions(troupe: Troupe) -> None:
    changed(troupe, allowed_sects=["Camarilla"])
    one = generated(troupe)
    assert (one["sects"], one["setting"]) == (["Camarilla"], "Camarilla")

    changed(troupe, allowed_sects=["Camarilla", "Anarch"])
    found = generated(troupe)
    assert (found["sects"], found["setting"]) == (["Anarch", "Camarilla"], None)


def test_clan_rarity_changes_carry_the_books_rarity_and_their_reason(troupe: Troupe) -> None:
    changed(troupe, allowed_sects=["Camarilla"])
    st = troupe.storyteller.client
    response = st.put(
        f"/troupes/{troupe.id}/clan-rarity",
        json={
            "rarities": {"Lasombra": "uncommon", "Ventrue": "uncommon"},
            # A reason for a clan not rated here is dropped.
            "notes": {"Lasombra": "  due to   story ", "Brujah": "never kept"},
        },
    )
    assert response.status_code == 200, response.text
    rows = {r["clan"]: r for r in response.json()["clans"]}
    assert (rows["Lasombra"]["note"], rows["Brujah"]["note"]) == ("due to story", "")

    assert generated(troupe)["clan_rarity"] == [
        {"clan": "Lasombra", "rarity": "uncommon", "book": "rare", "note": "due to story"},
        {"clan": "Ventrue", "rarity": "uncommon", "book": "common", "note": ""},
    ]
    assert "set how rare clans are here: Lasombra uncommon (due to story), Ventrue uncommon." in (
        " ".join(log(troupe))
    )

    # Rating clans again without reasons keeps those of the clans still rated.
    st.put(f"/troupes/{troupe.id}/clan-rarity", json={"rarities": {"Lasombra": "common"}})
    assert generated(troupe)["clan_rarity"] == [
        {"clan": "Lasombra", "rarity": "common", "book": "rare", "note": "due to story"}
    ]

    # With several sects, each character goes by its own sect's book rarity.
    changed(troupe, allowed_sects=["Camarilla", "Anarch"])
    [row] = generated(troupe)["clan_rarity"]
    assert row["book"] is None
    # How rare clans are is its own section, not one of the mechanics.
    assert not any("Lasombra" in line for line in generated(troupe)["mechanics"])


def test_cost_changes_list_prices_own_merits_and_banned_traits(troupe: Troupe) -> None:
    st = troupe.storyteller.client
    st.post(
        f"/troupes/{troupe.id}/costs",
        json={"category": "attributes", "scheme": "per_dot", "rate": 4},
    )
    st.post(
        f"/troupes/{troupe.id}/house-traits",
        json={
            "category": "merits",
            "name": "Child of the Crossroads",
            "points": 2,
            "availability": "building",
        },
    )
    # One only staff give is no cost players pay.
    st.post(
        f"/troupes/{troupe.id}/house-traits",
        json={"category": "flaws", "name": "Old Debt", "points": 1, "availability": "staff"},
    )
    banned = st.put(
        f"/troupes/{troupe.id}/book-traits",
        json={"category": "merits", "name": "Lucky", "banned": True, "ban_reason": "Too swingy"},
    )
    assert banned.status_code == 200, banned.text

    assert generated(troupe)["costs"] == [
        "All Attributes: 4 XP per dot (the book: 3 XP per dot)",
        "Child of the Crossroads: a 2-point merit of the troupe's own",
        "Lucky is not used here: Too swingy",
    ]


def test_mechanics_name_starting_points_checks_game_xp_and_house_rules(troupe: Troupe) -> None:
    st = troupe.storyteller.client
    st.put(f"/troupes/{troupe.id}/creation/merits", json={"rules": [{"points": 5}]})
    st.put(f"/troupes/{troupe.id}/checks/merits/Calm Heart/1", json={"strength": "off"})
    own = st.post(f"/troupes/{troupe.id}/house-checks", json=OLD_BLOOD)
    assert own.status_code == 201, own.text
    st.put(f"/troupes/{troupe.id}/starting-blood", json={"blood": 5})
    chart = st.put(
        f"/troupes/{troupe.id}/game-xp",
        json={
            "bands": [
                {"up_to": 100, "attended": 10, "absentee": 0},
                {"up_to": None, "attended": 6, "absentee": 0},
            ]
        },
    )
    assert chart.status_code == 200, chart.text

    found = generated(troupe)
    lines = found["mechanics"]
    assert "Merits: 5 points (the book: 7 points)" in lines
    assert "Daughters of Cacophony and Nagaraja can be no older than Generation 4." in lines
    assert any("Calm Heart" in line and line.endswith(": does not apply") for line in lines)
    assert "Blood at the start of a game: 5 Blood (the book: full)" in lines
    assert any(line.startswith("Game XP, by earned XP: 10 XP a game") for line in lines)
    assert found["graduated"] is True


def test_the_new_character_incentive_gives_a_quarter_of_the_earned_xp(troupe: Troupe) -> None:
    set_by_hand = troupe.lead.client.put(
        f"/troupes/{troupe.id}/xp-range",
        json={"floor": 150, "ceiling": 230, "reason": "Began before Horatio"},
    )
    assert set_by_hand.status_code == 200, set_by_hand.text
    # Off, a new character starts at the floor.
    off = changed(troupe)
    assert (off["new_character_incentive"], off["new_character_xp"]) == (False, 150)
    assert generated(troupe)["initial_xp"] == 150

    on = changed(troupe, new_character_incentive=True)
    # 30 XP to start, and a quarter of the 200 XP a character could have earned.
    assert (on["new_character_incentive"], on["new_character_xp"]) == (True, 80)
    found = generated(troupe)
    assert (found["initial_xp"], found["incentive"]) == (
        80,
        {"base": 30, "earned": 200, "bonus": 50, "total": 80},
    )
    assert "switched on the New Character Incentive." in " ".join(log(troupe))

    made = troupe.player.client.post(
        "/characters", json={"splat": "vampire", "name": "Bram", "building_troupe_id": troupe.id}
    )
    assert made.status_code == 201, made.text
    xp = troupe.player.client.get(f"/characters/{made.json()['id']}/xp").json()
    [start] = [e for e in xp if e["reason"].startswith("Starting experience")]
    assert (start["amount"], start["reason"]) == (
        80,
        "Starting experience: Lords of the Night's New Character Incentive",
    )

    # Only those who manage house rules switch it.
    refused = troupe.assistant.client.patch(
        f"/troupes/{troupe.id}", json={"new_character_incentive": False}
    )
    assert refused.status_code == 403


def test_the_profile_shows_the_document_when_storytellers_choose(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    anyone = client_for()
    troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": True})
    profile = anyone.get(f"/troupes/{troupe.id}/profile")
    assert profile.status_code == 200, profile.text
    assert profile.json()["setting_document"] is False
    assert anyone.get(f"/troupes/{troupe.id}/setting").status_code == 404

    # Assistants write the document, but only storytellers put it on the profile.
    refused = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/setting/public", json={"public": True}
    )
    assert refused.status_code == 403
    assert troupe.assistant.client.get(f"/troupes/{troupe.id}/setting").json()["can_publish"] is (
        False
    )
    shown = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/setting/public", json={"public": True}
    )
    assert shown.status_code == 200, shown.text
    assert (shown.json()["public"], shown.json()["can_publish"]) == (True, True)
    assert "set the troupe's profile so it shows its setting." in " ".join(log(troupe))

    assert anyone.get(f"/troupes/{troupe.id}/profile").json()["setting_document"] is True
    read = anyone.get(f"/troupes/{troupe.id}/setting")
    assert read.status_code == 200, read.text
    assert (read.json()["troupe"], read.json()["can_edit"], read.json()["can_publish"]) == (
        "Lords of the Night",
        False,
        False,
    )

    # A private profile shows it to no one signed out.
    troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": False})
    assert anyone.get(f"/troupes/{troupe.id}/setting").status_code == 404
