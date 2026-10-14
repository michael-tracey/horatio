"""A character's own log: when, who, and what."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def log(person: Person, character_id: str) -> list[tuple[str | None, str]]:
    response = person.client.get(f"/characters/{character_id}/log")
    assert response.status_code == 200, response.text
    return [(e["actor_name"], e["message"]) for e in response.json()]


def test_the_log_says_who_did_what(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    client = troupe.player.client
    client.put(
        f"/characters/{character_id}/traits",
        json={"category": "sect", "name": "Camarilla", "rating": None},
    )
    client.put(
        f"/characters/{character_id}/traits",
        json={"category": "skills", "name": "Brawl", "rating": 2},
    )
    client.put(
        f"/characters/{character_id}/traits",
        json={"category": "skills", "name": "Brawl", "rating": 1},
    )
    client.post(f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id})

    assert log(troupe.player, character_id) == [
        ("player", "Agnes joined the troupe as a draft."),
        ("player", "player lowered Agnes's Brawl from 2 to 1 (2 XP back)."),
        ("player", "player bought Brawl 2 for Agnes (3 XP)."),
        ("player", "player chose Camarilla as Agnes's sect."),
    ]
    entry = client.get(f"/characters/{character_id}/log").json()[0]
    assert entry["at"]


def test_staff_see_their_own_troupes_part(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    troupe.player.client.post(f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id})
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Elsewhere", "lead_email": troupe.stranger.email}
    ).json()["id"]
    troupe.player.client.post(f"/characters/{character_id}/troupes", json={"troupe_id": other})

    assert len(log(troupe.player, character_id)) == 2
    assert len(log(troupe.custodian, character_id)) == 2
    assert [m for _, m in log(troupe.assistant, character_id)] == [
        "Agnes joined the troupe as a draft."
    ]
    assert len(log(troupe.stranger, character_id)) == 1
    assert troupe.narrator.client.get(f"/characters/{character_id}/log").status_code == 404
