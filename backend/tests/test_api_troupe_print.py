"""Printing several of a troupe's sheets at once."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def member(troupe: Troupe, name: str) -> str:
    character_id = new_character(troupe, troupe.player, name)
    joined = troupe.player.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id}
    )
    assert joined.status_code == 201, joined.text
    return character_id


def printed(person: Person, troupe: Troupe, *characters: str) -> list[str]:
    response = person.client.get(
        f"/troupes/{troupe.id}/print", params={"characters": list(characters)}
    )
    assert response.status_code == 200, response.text
    return [s["character_name"] for s in response.json()]


def test_print_every_character_in_the_troupe(troupe: Troupe) -> None:
    member(troupe, "Mara")
    agnes = member(troupe, "Agnes")
    troupe.assistant.client.put(
        f"/troupes/{troupe.id}/characters/{agnes}/titles", json={"titles": ["Soldier"]}
    )

    sheets = troupe.lead.client.get(f"/troupes/{troupe.id}/print").json()

    assert [s["character_name"] for s in sheets] == ["Agnes", "Mara"]
    assert {s["troupe_name"] for s in sheets} == {"Lords of the Night"}
    assert sheets[0]["titles"] == ["Soldier"]
    assert sheets[0]["traits"]


def test_print_the_characters_chosen_in_their_order(troupe: Troupe) -> None:
    agnes, mara, nell = member(troupe, "Agnes"), member(troupe, "Mara"), member(troupe, "Nell")

    assert printed(troupe.assistant, troupe, nell, agnes) == ["Nell", "Agnes"]
    assert mara  # not asked for, not printed


def test_only_the_troupes_own_characters(troupe: Troupe) -> None:
    member(troupe, "Agnes")
    elsewhere = new_character(troupe, troupe.player, "Elsewhere")

    response = troupe.lead.client.get(
        f"/troupes/{troupe.id}/print", params={"characters": [elsewhere]}
    )
    assert response.status_code == 404


def test_narrators_and_players_cannot_print_the_troupe(troupe: Troupe) -> None:
    member(troupe, "Agnes")

    for person in (troupe.narrator, troupe.player):
        assert person.client.get(f"/troupes/{troupe.id}/print").status_code == 403
