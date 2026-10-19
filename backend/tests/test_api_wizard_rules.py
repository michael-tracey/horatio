"""Rules the creation wizard follows: what a step needs before moving on, and
traits only for a sect the troupe takes."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def creation(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/creation")
    assert response.status_code == 200, response.text
    return response.json()


def choose(person: Person, character_id: str, category: str, name: str) -> None:
    chosen = person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": None},
    )
    assert chosen.status_code == 200, chosen.text


def catalogue(troupe: Troupe) -> dict[str, Any]:
    response = troupe.player.client.get("/rules/vampire", params={"troupe_id": troupe.id})
    assert response.status_code == 200, response.text
    return response.json()


def limit_sects(troupe: Troupe, sects: list[str]) -> None:
    response = troupe.lead.client.patch(f"/troupes/{troupe.id}", json={"allowed_sects": sects})
    assert response.status_code == 200, response.text


# --- what a step needs -------------------------------------------------------------------------


def test_a_vampire_needs_generation_before_leaving_backgrounds(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Brujah")

    assert creation(troupe.player, character_id)["needs"] == [
        {
            "step": "backgrounds",
            "message": "A vampire needs at least 1 dot of Generation; without one the"
            " character is mortal. (p. 98)",
        }
    ]
    saved = troupe.player.client.put(
        f"/characters/{character_id}/creation/categories/backgrounds",
        json={"picks": [{"name": "Generation", "rating": 1}]},
    )
    assert saved.status_code == 200, saved.text
    assert creation(troupe.player, character_id)["needs"] == []


def test_a_troupe_that_switches_the_check_off_needs_nothing(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, finished=False, clan="Brujah")
    built = troupe.player.client.put(
        f"/characters/{character_id}/building-troupe", json={"troupe_id": troupe.id}
    )
    assert built.status_code == 200, built.text
    checks = troupe.lead.client.get(f"/troupes/{troupe.id}/checks").json()
    generation = next(c for c in checks if c["message"].startswith("A vampire needs"))
    switched = troupe.lead.client.put(
        f"/troupes/{troupe.id}/checks/{generation['key']}", json={"strength": "off"}
    )
    assert switched.status_code == 200, switched.text

    assert creation(troupe.player, character_id)["needs"] == []


# --- traits for one sect -----------------------------------------------------------------------


def test_a_troupe_without_the_sabbat_does_not_see_rituals(troupe: Troupe) -> None:
    def offered() -> tuple[bool, bool]:
        found = catalogue(troupe)
        return (
            any(t["name"] == "Rituals" for t in found["traits"]),
            any(c["key"] == "sabbat_rituals" for c in found["categories"]),
        )

    assert offered() == (True, True)  # every sect is welcome
    limit_sects(troupe, ["Anarch", "Camarilla"])
    assert offered() == (False, False)
    limit_sects(troupe, ["Camarilla", "Sabbat"])
    assert offered() == (True, True)
    # Without a troupe, the rule set shows everything.
    plain = troupe.player.client.get("/rules/vampire").json()
    assert any(t["name"] == "Rituals" for t in plain["traits"])


def test_only_the_sabbat_take_rituals(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Lasombra")
    choose(troupe.player, character_id, "sect", "Camarilla")

    unavailable = troupe.player.client.get(
        f"/characters/{character_id}/unavailable", params={"category": "backgrounds"}
    ).json()
    assert unavailable["Rituals"] == (
        "Only members of the Sabbat can take the Rituals background. (p. 452)"
    )
    bought = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "backgrounds", "name": "Rituals", "rating": 1},
    )
    assert bought.status_code == 409

    choose(troupe.player, character_id, "sect", "Sabbat")
    bought = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "backgrounds", "name": "Rituals", "rating": 1},
    )
    assert bought.status_code == 200, bought.text
