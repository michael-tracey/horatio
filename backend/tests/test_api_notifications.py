"""The bell: tasks waiting on staff, and messages for players."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_responses import Scene


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def bell(person: Person) -> dict[str, Any]:
    response = person.client.get("/notifications")
    assert response.status_code == 200, response.text
    return response.json()


def summaries(person: Person) -> list[str]:
    return [i["summary"] for i in bell(person)["items"]]


def at_home(troupe: Troupe, name: str = "Agnes") -> str:
    character_id = new_character(troupe, troupe.player, name)
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    return character_id


def test_waiting_approvals_are_tasks_for_whoever_can_decide_them(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )

    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        found = bell(person)
        assert found["count"] == 1
        [item] = found["items"]
        assert (item["kind"], item["task"], item["troupe_name"], item["link"]) == (
            "approval.home_troupe_change",
            True,
            "Lords of the Night",
            f"/troupes/{troupe.id}/approvals",
        )
        assert item["summary"] == "Agnes asks to make Lords of the Night its home"
    # Narrators cannot approve; players and the custodian (on staff nowhere) are not asked.
    for person in (troupe.narrator, troupe.player, troupe.custodian, troupe.stranger):
        assert bell(person) == {"items": [], "count": 0}


def test_a_task_goes_when_the_work_is_done(troupe: Troupe) -> None:
    character_id = at_home(troupe)
    troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "disciplines", "name": "Celerity", "rating": 1},
    )
    [item] = bell(troupe.assistant)["items"]
    assert item["summary"].startswith("Agnes bought Celerity 0 → 1 (")
    assert item["kind"] == "approval.discipline"

    # Marking read does nothing to a task; deciding it does.
    troupe.assistant.client.post("/notifications/read", json={})
    assert bell(troupe.assistant)["count"] == 1
    troupe.lead.client.post(f"/approvals/{item['id'].split(':')[1]}/approve", json={})

    assert bell(troupe.assistant)["count"] == 0


def test_tasks_come_from_every_troupe_the_person_runs(troupe: Troupe) -> None:
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Second City", "lead_handle": troupe.assistant.handle}
    ).json()["id"]
    first = new_character(troupe, troupe.player, "Agnes")
    second = new_character(troupe, troupe.player, "Bertrand")
    for character_id, troupe_id in ((first, troupe.id), (second, other)):
        troupe.player.client.post(
            f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe_id}
        )

    assert sorted(summaries(troupe.assistant)) == [
        "Agnes asks to make Lords of the Night its home",
        "Bertrand asks to make Second City its home",
    ]
    assert summaries(troupe.storyteller) == ["Agnes asks to make Lords of the Night its home"]


def test_archived_troupes_ask_nothing(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )

    troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Wound up"})

    assert bell(troupe.lead)["count"] == 0


def test_players_hear_when_downtime_results_arrive(troupe: Troupe) -> None:
    scene = Scene(troupe)
    feed = scene.response_for("Feed at the docks")["id"]
    troupe.assistant.client.put(f"/responses/{feed}", json={"body": "You feed well."})
    troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/close")
    troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/deliver", json={"partial": True})

    found = bell(troupe.player)
    assert found["count"] == 1
    [item] = found["items"]
    assert (item["kind"], item["task"], item["read"], item["link"]) == (
        "downtime.delivered",
        False,
        False,
        f"/characters/{scene.agnes}/results",
    )
    assert item["summary"] == "Downtime results for Agnes (October 2026) are ready."

    assert (
        troupe.player.client.post("/notifications/read", json={"ids": [item["id"]]}).status_code
        == 204
    )

    after = bell(troupe.player)
    assert after["count"] == 0
    assert [i["read"] for i in after["items"]] == [True]


def test_people_only_mark_their_own_messages_read(troupe: Troupe) -> None:
    scene = Scene(troupe)
    feed = scene.response_for("Feed at the docks")["id"]
    troupe.assistant.client.put(f"/responses/{feed}", json={"body": "You feed well."})
    troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/close")
    troupe.assistant.client.post(f"/cycles/{scene.cycle['id']}/deliver", json={"partial": True})
    message = bell(troupe.player)["items"][0]["id"]

    troupe.stranger.client.post("/notifications/read", json={"ids": [message]})

    assert bell(troupe.player)["count"] == 1
