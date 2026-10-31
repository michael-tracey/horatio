"""Troupes switch checks off or change how strict they are; review holds a change
for the home troupe."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character

pytestmark = pytest.mark.usefixtures("without_bank")

CALM_HEART = "merits/Calm Heart/1"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(person: Person, character_id: str, name: str, rating: int) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "merits", "name": name, "rating": rating},
    )


def house(troupe: Troupe, person: Person, key: str, strength: str | None) -> Any:
    return person.client.put(f"/troupes/{troupe.id}/checks/{key}", json={"strength": strength})


def accepted_brujah(troupe: Troupe) -> str:
    character_id = new_character(troupe, troupe.player, clan="Brujah")
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    return character_id


def test_storytellers_set_checks_and_others_see_them(troupe: Troupe) -> None:
    assert house(troupe, troupe.assistant, CALM_HEART, "off").status_code == 403
    assert house(troupe, troupe.storyteller, "merits/Juggling/1", "off").status_code == 404

    changed = house(troupe, troupe.storyteller, CALM_HEART, "note")

    assert (changed.json()["strength"], changed.json()["house"]) == ("refuse", "note")
    listed = troupe.assistant.client.get(f"/troupes/{troupe.id}/checks").json()
    assert next(c for c in listed if c["key"] == CALM_HEART)["house"] == "note"
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/checks").status_code == 403


def test_a_check_switched_off_no_longer_refuses(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    assert take(troupe.player, character_id, "Calm Heart", 1).status_code == 409

    house(troupe, troupe.storyteller, CALM_HEART, "off")

    assert take(troupe.player, character_id, "Calm Heart", 1).status_code == 200


def test_review_holds_the_change_for_the_home_troupe(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    house(troupe, troupe.storyteller, CALM_HEART, "review")
    before = troupe.player.client.get(f"/characters/{character_id}/sheet").json()["xp"]["balance"]

    taken = take(troupe.player, character_id, "Calm Heart", 1)

    assert taken.status_code == 200, taken.text
    [request] = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()
    # A merit taken once accepted is asked of staff anyway, with the check it breaks.
    assert request["kind"] == "merit_flaw"
    assert request["player_note"].startswith("Brujah cannot take Calm Heart")
    assert request["discipline"]["name"] == "Calm Heart"

    troupe.lead.client.post(f"/approvals/{request['id']}/decline", json={})

    after = troupe.player.client.get(f"/characters/{character_id}/sheet").json()
    assert "Calm Heart" not in [t["name"] for t in after["traits"]]
    assert after["xp"]["balance"] == before


def test_house_rules_apply_once_the_troupe_is_home(troupe: Troupe) -> None:
    house(troupe, troupe.storyteller, CALM_HEART, "off")
    character_id = new_character(troupe, troupe.player, clan="Brujah")

    assert take(troupe.player, character_id, "Calm Heart", 1).status_code == 409
