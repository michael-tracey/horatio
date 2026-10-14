"""Characters through the API: who can see and change them."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import TroupeMembership
from tests.api_helpers import Person, Troupe


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def create_character(person: Person, name: str = "Agnes") -> str:
    response = person.client.post("/characters", json={"splat": "vampire", "name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def join(session: Session, troupe: Troupe, character_id: str) -> None:
    # Joining through the API arrives with home troupes and approvals.
    session.add(
        TroupeMembership(troupe_id=uuid.UUID(troupe.id), character_id=uuid.UUID(character_id))
    )
    session.flush()


def test_new_characters_live_in_the_vault_outside_any_troupe(troupe: Troupe) -> None:
    character_id = create_character(troupe.player)

    character = troupe.player.client.get(f"/characters/{character_id}").json()

    assert character["status"] == "active"
    assert character["home_troupe_id"] is None
    assert [c["id"] for c in troupe.player.client.get("/characters").json()] == [character_id]


def test_a_character_needs_a_splat_with_rules(troupe: Troupe) -> None:
    response = troupe.player.client.post("/characters", json={"splat": "mummy", "name": "Ra"})

    assert response.status_code == 422


def test_other_players_cannot_see_a_character_at_all(troupe: Troupe) -> None:
    character_id = create_character(troupe.player)

    response = troupe.stranger.client.get(f"/characters/{character_id}")

    # 404, not 403: a stranger cannot even learn the character exists.
    assert response.status_code == 404
    assert troupe.stranger.client.get("/characters").json() == []


def test_running_staff_see_their_troupes_characters_and_narrators_do_not(
    troupe: Troupe, session: Session
) -> None:
    character_id = create_character(troupe.player)
    assert troupe.storyteller.client.get(f"/characters/{character_id}").status_code == 404

    join(session, troupe, character_id)

    for person in (troupe.lead, troupe.storyteller, troupe.assistant, troupe.custodian):
        assert person.client.get(f"/characters/{character_id}").status_code == 200
    assert troupe.narrator.client.get(f"/characters/{character_id}").status_code == 404


def test_only_the_player_changes_their_character(troupe: Troupe, session: Session) -> None:
    character_id = create_character(troupe.player)
    join(session, troupe, character_id)

    assert (
        troupe.storyteller.client.patch(
            f"/characters/{character_id}", json={"name": "Renamed"}
        ).status_code
        == 403
    )
    response = troupe.player.client.patch(f"/characters/{character_id}", json={"name": "Agatha"})

    assert response.status_code == 200
    assert response.json()["name"] == "Agatha"


def test_retired_characters_are_kept_but_cannot_be_changed(troupe: Troupe) -> None:
    character_id = create_character(troupe.player)

    response = troupe.player.client.post(f"/characters/{character_id}/retire")

    assert response.json()["status"] == "retired"
    assert troupe.player.client.get(f"/characters/{character_id}").status_code == 200
    assert (
        troupe.player.client.patch(f"/characters/{character_id}", json={"name": "x"}).status_code
        == 409
    )
