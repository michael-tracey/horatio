"""Each troupe decides whether a character is a draft or approved there; characters
in no troupe can be deleted; and troupes keep a log for their storytellers."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def join(person: Person, character_id: str, troupe_id: str) -> Any:
    response = person.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe_id}
    )
    assert response.status_code == 201, response.text
    return response.json()


def standings(person: Person, character_id: str) -> dict[str, str]:
    sheet = person.client.get(f"/characters/{character_id}/sheet").json()
    return {s["troupe_name"]: s["standing"] for s in sheet["standings"]}


def second_troupe(troupe: Troupe) -> str:
    """A second troupe, led by the first one's storyteller."""
    response = troupe.custodian.client.post(
        "/troupes", json={"name": "Second City", "lead_email": troupe.storyteller.email}
    )
    return response.json()["id"]


def ask(person: Person, character_id: str) -> list[dict[str, Any]]:
    response = person.client.post(f"/characters/{character_id}/approval", json={})
    assert response.status_code == 201, response.text
    return response.json()


def buy(person: Person, character_id: str, name: str, rating: int) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "skills", "name": name, "rating": rating},
    )


def log(person: Person, troupe_id: str) -> list[str]:
    return [e["message"] for e in person.client.get(f"/troupes/{troupe_id}/log").json()]


# --- standing ----------------------------------------------------------------------------------


def test_joining_makes_a_character_a_draft_in_that_troupe(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert join(troupe.player, character_id, troupe.id)["standing"] == "draft"
    assert standings(troupe.player, character_id) == {"Lords of the Night": "draft"}


def test_each_troupe_approves_for_itself(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    other = second_troupe(troupe)
    join(troupe.player, character_id, troupe.id)
    join(troupe.player, character_id, other)

    requests = ask(troupe.player, character_id)
    assert sorted(r["troupe_id"] for r in requests) == sorted([troupe.id, other])

    first = next(r for r in requests if r["troupe_id"] == troupe.id)
    troupe.assistant.client.post(f"/approvals/{first['id']}/approve", json={})

    assert standings(troupe.player, character_id) == {
        "Lords of the Night": "approved",
        "Second City": "draft",
    }
    # Still locked: Second City has not decided.
    assert buy(troupe.player, character_id, "Brawl", 1).status_code == 409


def test_a_change_goes_to_every_troupe_and_each_keeps_its_own_approved_sheet(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player)
    other = second_troupe(troupe)
    join(troupe.player, character_id, troupe.id)
    join(troupe.player, character_id, other)
    for request in ask(troupe.player, character_id):
        approver = troupe.assistant if request["troupe_id"] == troupe.id else troupe.storyteller
        approver.client.post(f"/approvals/{request['id']}/approve", json={})

    buy(troupe.player, character_id, "Brawl", 2)
    requests = ask(troupe.player, character_id)
    first = next(r for r in requests if r["troupe_id"] == troupe.id)
    troupe.assistant.client.post(f"/approvals/{first['id']}/approve", json={})

    def brawl_as_seen_by(troupe_id: str) -> Any:
        sheet = troupe.player.client.get(
            f"/characters/{character_id}/sheet", params={"troupe_id": troupe_id}
        ).json()
        return next(t["approved_rating"] for t in sheet["traits"] if t["name"] == "Brawl")

    assert brawl_as_seen_by(troupe.id) == 2
    assert brawl_as_seen_by(other) is None
    # Second City still sees the change as waiting.
    queue = troupe.storyteller.client.get(f"/troupes/{other}/approvals").json()
    assert [(c["name"], c["rating"]) for c in queue[0]["changes"]] == [("Brawl", 2)]


def test_dots_approved_anywhere_cannot_be_taken_back(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    other = second_troupe(troupe)
    join(troupe.player, character_id, troupe.id)
    join(troupe.player, character_id, other)
    buy(troupe.player, character_id, "Brawl", 2)
    for request in ask(troupe.player, character_id):
        if request["troupe_id"] == troupe.id:
            troupe.assistant.client.post(f"/approvals/{request['id']}/approve", json={})
        else:
            troupe.storyteller.client.post(f"/approvals/{request['id']}/decline", json={})

    assert buy(troupe.player, character_id, "Brawl", 1).status_code == 409


def test_staff_send_a_character_back_to_draft_with_a_reason(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    join(troupe.player, character_id, troupe.id)
    request = ask(troupe.player, character_id)[0]
    troupe.assistant.client.post(f"/approvals/{request['id']}/approve", json={})
    path = f"/troupes/{troupe.id}/characters/{character_id}/return-to-draft"

    assert troupe.narrator.client.post(path, json={"reason": "x"}).status_code == 403
    response = troupe.assistant.client.post(path, json={"reason": "New clan rules"})

    assert response.json()["standing"] == "draft"
    sheet = troupe.player.client.get(f"/characters/{character_id}/sheet").json()
    assert sheet["standings"][0]["note"] == "New clan rules"
    assert "assistant sent Agnes back to draft: New clan rules" in log(troupe.lead, troupe.id)


def test_only_characters_approved_in_their_home_troupe_take_part_in_downtimes(
    troupe: Troupe,
) -> None:
    approved = new_character(troupe, troupe.player, "Approved")
    sent_back = new_character(troupe, troupe.player, "Sent Back")
    for character_id in (approved, sent_back):
        request = troupe.player.client.post(
            f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
        ).json()
        troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    troupe.lead.client.post(
        f"/troupes/{troupe.id}/characters/{sent_back}/return-to-draft", json={"reason": "Redo"}
    )
    now = datetime.now(UTC)
    cycle = troupe.lead.client.post(
        f"/troupes/{troupe.id}/cycles",
        json={
            "name": "November",
            "closes_at": (now + timedelta(days=7)).isoformat(),
            "grace_ends_at": (now + timedelta(days=9)).isoformat(),
        },
    ).json()

    troupe.lead.client.post(f"/cycles/{cycle['id']}/open")

    participants = troupe.lead.client.get(f"/cycles/{cycle['id']}/participants").json()
    assert [p["character_name"] for p in participants] == ["Approved"]


def test_the_roster_lists_drafts_first(troupe: Troupe) -> None:
    approved = new_character(troupe, troupe.player, "Agnes")
    new_character(troupe, troupe.player, "Bertrand")
    for character_id in (approved,):
        join(troupe.player, character_id, troupe.id)
        request = ask(troupe.player, character_id)[0]
        troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    draft = troupe.player.client.get("/characters").json()
    bertrand = next(c["id"] for c in draft if c["name"] == "Bertrand")
    join(troupe.player, bertrand, troupe.id)

    roster = troupe.assistant.client.get(f"/troupes/{troupe.id}/characters").json()

    assert [(r["character_name"], r["standing"], r["player_name"]) for r in roster] == [
        ("Bertrand", "draft", "player"),
        ("Agnes", "approved", "player"),
    ]
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/characters").status_code == 403


# --- deleting ----------------------------------------------------------------------------------


def test_a_character_in_a_troupe_cannot_be_deleted(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    join(troupe.player, character_id, troupe.id)

    response = troupe.player.client.delete(f"/characters/{character_id}")

    assert response.status_code == 409
    assert "every troupe" in response.json()["detail"]


def test_deleting_a_character_after_it_leaves_every_troupe(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    join(troupe.player, character_id, troupe.id)
    request = ask(troupe.player, character_id)[0]
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    troupe.player.client.delete(f"/characters/{character_id}/troupes/{troupe.id}")

    assert troupe.stranger.client.delete(f"/characters/{character_id}").status_code == 404
    assert troupe.player.client.delete(f"/characters/{character_id}").status_code == 204

    assert troupe.player.client.get(f"/characters/{character_id}").status_code == 404
    assert troupe.player.client.get("/characters").json() == []
    # The storytellers can see what happened, by name.
    messages = log(troupe.lead, troupe.id)
    assert messages[0] == "Agnes was deleted by its player."
    assert "Agnes left the troupe." in messages


def test_a_character_never_in_a_troupe_is_deleted_quietly(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert troupe.player.client.delete(f"/characters/{character_id}").status_code == 204
    assert log(troupe.lead, troupe.id)[0] != "Agnes was deleted by its player."


# --- the log -------------------------------------------------------------------------------------


def test_the_log_is_for_storytellers_and_assistants(troupe: Troupe) -> None:
    assert troupe.assistant.client.get(f"/troupes/{troupe.id}/log").status_code == 200
    for person in (troupe.narrator, troupe.player):
        assert person.client.get(f"/troupes/{troupe.id}/log").status_code == 403


def test_the_log_reads_newest_first(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    join(troupe.player, character_id, troupe.id)
    ask(troupe.player, character_id)

    messages = log(troupe.lead, troupe.id)

    assert messages[:2] == [
        "player asked for Agnes to be approved.",
        "Agnes joined the troupe as a draft.",
    ]
    # Staff changes from setting the troupe up are there too.
    assert "lead made narrator narrator." in messages


# --- printing ----------------------------------------------------------------------------------


def test_printing_shows_the_troupes_approved_sheet(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    join(troupe.player, character_id, troupe.id)
    buy(troupe.player, character_id, "Brawl", 2)
    request = ask(troupe.player, character_id)[0]
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    buy(troupe.player, character_id, "Dodge", 1)  # not approved yet

    printed = troupe.player.client.get(f"/characters/{character_id}/print").json()
    current = troupe.player.client.get(
        f"/characters/{character_id}/print", params={"current": True}
    ).json()

    assert (printed["approved"], printed["version"], printed["troupe_name"]) == (
        True,
        1,
        "Lords of the Night",
    )
    assert printed["approved_by"] == "lead"
    names = [t["name"] for t in printed["traits"]]
    assert "Brawl" in names and "Dodge" not in names
    assert next(t for t in printed["traits"] if t["name"] == "Brawl")["attribute"] == "Physical"
    assert current["approved"] is False
    assert "Dodge" in [t["name"] for t in current["traits"]]


def test_a_vault_character_prints_as_not_approved(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    printed = troupe.player.client.get(f"/characters/{character_id}/print").json()

    assert (printed["approved"], printed["troupe_name"]) == (False, None)
    assert troupe.narrator.client.get(f"/characters/{character_id}/print").status_code == 404
