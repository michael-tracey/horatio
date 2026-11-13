"""Being built (#774): the characters built to a troupe's rules that haven't asked to
join it yet, for its storytellers and assistant storytellers."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character
from tests.api_helpers import Person, Troupe, finish
from tests.test_api_creation import pick

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def building(troupe: Troupe, name: str, troupe_id: str | None = None) -> str:
    """A new Vampire its player builds to a troupe's rules: this one's unless named."""
    response = troupe.player.client.post(
        "/characters",
        json={"splat": "vampire", "name": name, "building_troupe_id": troupe_id or troupe.id},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def choose_clan(troupe: Troupe, character_id: str, clan: str) -> None:
    chosen = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": clan, "rating": None},
    )
    assert chosen.status_code == 200, chosen.text


def builds(troupe: Troupe, person: Person | None = None) -> Any:
    return (person or troupe.storyteller).client.get(f"/troupes/{troupe.id}/builds")


def listed(troupe: Troupe) -> list[dict[str, Any]]:
    response = builds(troupe)
    assert response.status_code == 200, response.text
    return response.json()


def count(troupe: Troupe) -> int:
    response = troupe.storyteller.client.get(f"/troupes/{troupe.id}/builds/count")
    assert response.status_code == 200, response.text
    return response.json()["count"]


def test_a_character_in_creation_is_listed_with_what_is_left_to_place(troupe: Troupe) -> None:
    agnes = building(troupe, "Agnes")
    choose_clan(troupe, agnes, "Brujah")

    [entry] = listed(troupe)

    assert entry["character_id"] == agnes
    assert entry["character_name"] == "Agnes"
    assert entry["player_name"] == "player"
    assert entry["player_handle"] == troupe.player.handle
    assert entry["clan"] == "Brujah"
    assert entry["creation_complete"] is False
    assert "Attributes" in entry["to_place"]
    assert count(troupe) == 1


def test_a_finished_character_not_yet_submitted_is_listed(troupe: Troupe) -> None:
    agnes = building(troupe, "Agnes")
    finish(troupe, agnes)

    [entry] = listed(troupe)

    assert entry["creation_complete"] is True
    assert entry["to_place"] == []


def test_asking_to_join_moves_it_to_the_approval_queue(troupe: Troupe) -> None:
    agnes = building(troupe, "Agnes")
    finish(troupe, agnes)
    asked = troupe.player.client.post(
        f"/characters/{agnes}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code in (200, 201), asked.text

    assert listed(troupe) == []
    assert count(troupe) == 0

    # Withdrawn, it is being built here again.
    assert troupe.player.client.delete(f"/characters/{agnes}/home-troupe").status_code < 300
    assert [e["character_id"] for e in listed(troupe)] == [agnes]


def test_an_accepted_character_is_not_listed(troupe: Troupe) -> None:
    agnes = building(troupe, "Agnes")
    finish(troupe, agnes)
    request = troupe.player.client.post(
        f"/characters/{agnes}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    assert troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={}).status_code < 300

    assert listed(troupe) == []


def test_npcs_and_other_troupes_builds_are_not_listed(troupe: Troupe) -> None:
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Court of Thorns", "lead_handle": troupe.lead.handle}
    ).json()["id"]
    building(troupe, "Elsewhere", other)
    building(troupe, "Plain", None)
    plain = troupe.player.client.post("/characters", json={"splat": "vampire", "name": "None"})
    assert plain.status_code == 201
    made = troupe.lead.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Mystery Woman"})
    assert made.status_code == 201, made.text

    assert [e["character_name"] for e in listed(troupe)] == ["Plain"]


def test_a_retired_character_is_not_listed(troupe: Troupe) -> None:
    agnes = building(troupe, "Agnes")
    finish(troupe, agnes)
    retired = troupe.player.client.post(
        f"/characters/{agnes}/retire", json={"reason": "off_field", "listed": False}
    )
    assert retired.status_code < 300, retired.text

    assert listed(troupe) == []


def test_only_running_staff_and_the_custodian_see_the_list(troupe: Troupe) -> None:
    building(troupe, "Agnes")

    for person in (troupe.lead, troupe.storyteller, troupe.assistant, troupe.custodian):
        assert builds(troupe, person).status_code == 200
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert builds(troupe, person).status_code == 403
        assert person.client.get(f"/troupes/{troupe.id}/builds/count").status_code == 403


def test_no_email_is_ever_shown(troupe: Troupe) -> None:
    building(troupe, "Agnes")

    assert "@example.com" not in builds(troupe).text


def test_the_checks_finish_creation_refuses_on_are_listed(troupe: Troupe) -> None:
    check = {
        "category": "merits",
        "name": "Iron Will",
        "mode": "requires",
        "condition": {"clan_family": ["Ventrue"]},
        "strength": "complete",
        "message": "Iron Will is for the Ventrue here.",
    }
    added = troupe.storyteller.client.post(f"/troupes/{troupe.id}/house-checks", json=check)
    assert added.status_code == 201, added.text
    agnes = building(troupe, "Agnes")
    choose_clan(troupe, agnes, "Brujah")
    took = pick(troupe.player, agnes, "merits", "Iron Will")
    assert took.status_code == 200, took.text

    [entry] = listed(troupe)

    assert any(b.startswith("Iron Will is for the Ventrue here.") for b in entry["broken"])


def test_the_most_recently_changed_comes_first(troupe: Troupe, session: Session) -> None:
    first = building(troupe, "First")
    second = building(troupe, "Second")
    third = building(troupe, "Third")
    # A test runs in one transaction, where every row shares one time: set them apart.
    now = datetime.now(UTC)
    for character_id, ago in ((first, 0), (second, 2), (third, 1)):
        row = session.get_one(Character, uuid.UUID(character_id))
        row.updated_at = now - timedelta(hours=ago)
    session.flush()

    assert [e["character_name"] for e in listed(troupe)] == ["First", "Third", "Second"]


def test_a_tie_on_the_time_falls_to_the_newest_made(troupe: Troupe) -> None:
    building(troupe, "Older")
    building(troupe, "Newer")

    assert [e["character_name"] for e in listed(troupe)] == ["Newer", "Older"]


def test_staff_read_its_sheet_but_cannot_open_or_change_it(troupe: Troupe) -> None:
    agnes = building(troupe, "Agnes")

    printed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/builds/{agnes}/print")
    assert printed.status_code == 200, printed.text
    assert printed.json()["character_name"] == "Agnes"
    assert "@example.com" not in printed.text

    # Nothing else opens to them: not the sheet, nor the Play View or its taps.
    assert troupe.storyteller.client.get(f"/characters/{agnes}/sheet").status_code == 404
    assert troupe.storyteller.client.get(f"/characters/{agnes}/play").status_code == 404
    tap = troupe.storyteller.client.post(
        f"/characters/{agnes}/play/taps", json={"kind": "blood", "amount": -1}
    )
    assert tap.status_code in (404, 422)
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        got = person.client.get(f"/troupes/{troupe.id}/builds/{agnes}/print")
        assert got.status_code == 403


def test_a_sheet_not_being_built_here_does_not_print(troupe: Troupe) -> None:
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Court of Thorns", "lead_handle": troupe.lead.handle}
    ).json()["id"]
    elsewhere = building(troupe, "Elsewhere", other)

    got = troupe.storyteller.client.get(f"/troupes/{troupe.id}/builds/{elsewhere}/print")

    assert got.status_code == 404
