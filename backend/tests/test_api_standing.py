"""A character's home troupe holds its sheet; other troupes it only visits. Edits are
never reviewed, except discipline dots bought once the character has a home troupe.
Characters in no troupe can be deleted, and troupes keep a log for their storytellers."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character

# Balances here are about settlements and purchases, not banking creation XP.
pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def join(person: Person, character_id: str, troupe_id: str) -> Any:
    response = person.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe_id}
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_home(troupe: Troupe, character_id: str) -> None:
    """Ask for `troupe` as home, and have its lead accept."""
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert request.status_code == 201, request.text
    approved = troupe.lead.client.post(f"/approvals/{request.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text


def second_troupe(troupe: Troupe) -> str:
    """A second troupe, led by the first one's storyteller."""
    response = troupe.custodian.client.post(
        "/troupes", json={"name": "Second City", "lead_email": troupe.storyteller.email}
    )
    return response.json()["id"]


def sheet(person: Person, character_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def buy(person: Person, character_id: str, name: str, rating: int, category: str = "skills") -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )


def balance(person: Person, character_id: str) -> int:
    return sheet(person, character_id)["xp"]["balance"]


def queue(person: Person, troupe_id: str, state: str = "pending") -> Any:
    return person.client.get(f"/troupes/{troupe_id}/approvals", params={"state": state}).json()


def log(person: Person, troupe_id: str) -> list[str]:
    return [e["message"] for e in person.client.get(f"/troupes/{troupe_id}/log").json()]


# --- home troupe and visits ---------------------------------------------------------------------


def test_joining_a_troupe_is_a_visit_until_it_accepts_the_character_as_home(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player)
    join(troupe.player, character_id, troupe.id)

    visiting = sheet(troupe.player, character_id)
    assert visiting["home_troupe_id"] is None
    assert [(t["troupe_name"], t["home"]) for t in visiting["troupes"]] == [
        ("Lords of the Night", False)
    ]

    make_home(troupe, character_id)

    home = sheet(troupe.player, character_id)
    assert home["home_troupe_id"] == troupe.id
    assert [(t["troupe_name"], t["home"]) for t in home["troupes"]] == [
        ("Lords of the Night", True)
    ]
    assert "lead accepted Agnes; this is its home." in log(troupe.lead, troupe.id)


def test_there_is_no_asking_for_a_sheet_to_be_approved(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    join(troupe.player, character_id, troupe.id)

    asked = troupe.player.client.post(f"/characters/{character_id}/approval", json={})

    assert asked.status_code in (404, 405)


def test_edits_go_through_at_once_in_or_out_of_a_troupe(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    assert buy(troupe.player, character_id, "Brawl", 1).status_code == 200
    make_home(troupe, character_id)

    assert buy(troupe.player, character_id, "Dodge", 1).status_code == 200
    assert buy(troupe.player, character_id, "Dodge", 2).status_code == 200

    assert queue(troupe.lead, troupe.id) == []
    assert sheet(troupe.player, character_id)["pending_approvals"] == []


def test_dots_the_home_troupe_accepted_cannot_be_taken_back(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "Brawl", 2)
    make_home(troupe, character_id)
    buy(troupe.player, character_id, "Dodge", 1)

    refused = buy(troupe.player, character_id, "Brawl", 1)
    assert refused.status_code == 409
    assert "accepted at 2" in refused.json()["detail"]
    # Bought since: the player can still undo it.
    assert buy(troupe.player, character_id, "Dodge", 0).status_code == 200
    brawl = next(t for t in sheet(troupe.player, character_id)["traits"] if t["name"] == "Brawl")
    assert brawl["min_rating"] == 2


def test_only_the_home_troupe_awards_xp(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    visited = troupe.custodian.client.post(
        "/troupes", json={"name": "Visited", "lead_email": troupe.stranger.email}
    ).json()["id"]
    join(troupe.player, character_id, visited)
    make_home(troupe, character_id)
    award = {"amount": 2, "reason": "Game"}
    path = f"/characters/{character_id}/xp"

    # The visited troupe's lead sees the sheet, but awards nothing.
    assert troupe.stranger.client.get(f"/characters/{character_id}/sheet").status_code == 200
    assert troupe.stranger.client.post(path, json=award).status_code == 403
    assert troupe.assistant.client.post(path, json=award).status_code == 201


# --- disciplines --------------------------------------------------------------------------------


def test_discipline_dots_wait_on_the_home_troupe_with_the_xp_held(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home(troupe, character_id)
    before = balance(troupe.player, character_id)

    bought = buy(troupe.player, character_id, "Celerity", 1, "disciplines")

    assert bought.status_code == 200, bought.text
    cost = bought.json()["cost"]
    assert balance(troupe.player, character_id) == before - cost
    held = sheet(troupe.player, character_id)
    celerity = next(t for t in held["traits"] if t["name"] == "Celerity")
    assert (celerity["rating"], celerity["pending_from"]) == (1, 0)
    assert [(d["name"], d["to_rating"], d["cost"]) for d in held["pending_disciplines"]] == [
        ("Celerity", 1, cost)
    ]
    waiting = queue(troupe.assistant, troupe.id)
    assert [
        (a["kind"], a["discipline"]["name"], a["discipline"]["to_rating"]) for a in waiting
    ] == [("discipline", "Celerity", 1)]

    troupe.assistant.client.post(f"/approvals/{waiting[0]['id']}/approve", json={})

    approved = sheet(troupe.player, character_id)
    celerity = next(t for t in approved["traits"] if t["name"] == "Celerity")
    assert (celerity["pending_from"], celerity["min_rating"]) == (None, 1)
    assert approved["pending_disciplines"] == []
    assert balance(troupe.player, character_id) == before - cost
    assert "assistant approved Agnes's Celerity 1." in log(troupe.lead, troupe.id)


def test_declining_a_discipline_takes_the_dots_back_and_refunds(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home(troupe, character_id)
    before = balance(troupe.player, character_id)
    buy(troupe.player, character_id, "Celerity", 1, "disciplines")
    request = queue(troupe.lead, troupe.id)[0]

    troupe.lead.client.post(f"/approvals/{request['id']}/decline", json={"note": "No teacher"})

    after = sheet(troupe.player, character_id)
    assert "Celerity" not in [t["name"] for t in after["traits"]]
    assert after["xp"]["balance"] == before
    assert "lead declined Agnes's Celerity 1; refunded." in log(troupe.lead, troupe.id)


def test_the_player_can_withdraw_a_waiting_discipline(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home(troupe, character_id)
    before = balance(troupe.player, character_id)
    buy(troupe.player, character_id, "Celerity", 1, "disciplines")
    waiting = sheet(troupe.player, character_id)["pending_disciplines"][0]["approval_id"]

    path = f"/characters/{character_id}/disciplines/{waiting}"
    assert troupe.lead.client.delete(path).status_code == 403
    assert troupe.player.client.delete(path).status_code == 204

    assert balance(troupe.player, character_id) == before
    assert queue(troupe.lead, troupe.id) == []


def test_a_waiting_discipline_cannot_change_and_blocks_a_move(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    other = second_troupe(troupe)
    make_home(troupe, character_id)
    buy(troupe.player, character_id, "Celerity", 1, "disciplines")

    assert buy(troupe.player, character_id, "Celerity", 2, "disciplines").status_code == 409
    assert buy(troupe.player, character_id, "Celerity", 0, "disciplines").status_code == 409
    moving = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": other}
    )
    assert moving.status_code == 409
    # Other disciplines can still be bought, each waiting on its own.
    assert buy(troupe.player, character_id, "Fortitude", 1, "disciplines").status_code == 200
    assert len(queue(troupe.lead, troupe.id)) == 2


def test_disciplines_before_a_home_troupe_need_no_approval(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    buy(troupe.player, character_id, "Celerity", 1, "disciplines")

    assert sheet(troupe.player, character_id)["pending_disciplines"] == []


def test_leaving_the_home_troupe_refunds_waiting_disciplines(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home(troupe, character_id)
    before = balance(troupe.player, character_id)
    buy(troupe.player, character_id, "Celerity", 1, "disciplines")

    troupe.player.client.delete(f"/characters/{character_id}/troupes/{troupe.id}")

    assert balance(troupe.player, character_id) == before
    assert sheet(troupe.player, character_id)["pending_disciplines"] == []


# --- downtimes and the roster -----------------------------------------------------------------


def test_characters_whose_home_this_is_take_part_in_downtimes(troupe: Troupe) -> None:
    home = new_character(troupe, troupe.player, "At Home")
    visitor = new_character(troupe, troupe.player, "Visitor")
    make_home(troupe, home)
    join(troupe.player, visitor, troupe.id)
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
    assert [p["character_name"] for p in participants] == ["At Home"]


def test_the_roster_lists_home_characters_first(troupe: Troupe) -> None:
    home = new_character(troupe, troupe.player, "Bertrand")
    visitor = new_character(troupe, troupe.player, "Agnes")
    make_home(troupe, home)
    join(troupe.player, visitor, troupe.id)
    buy(troupe.player, home, "Celerity", 1, "disciplines")

    roster = troupe.assistant.client.get(f"/troupes/{troupe.id}/characters").json()

    assert [(r["character_name"], r["home"], r["disciplines_waiting"]) for r in roster] == [
        ("Bertrand", True, 1),
        ("Agnes", False, 0),
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
    make_home(troupe, character_id)
    buy(troupe.player, character_id, "Celerity", 1, "disciplines")
    request = queue(troupe.lead, troupe.id)[0]
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
    troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )

    messages = log(troupe.lead, troupe.id)

    assert messages[:2] == [
        "player asked to make this Agnes's home.",
        "Agnes joined the troupe.",
    ]
    # Staff changes from setting the troupe up are there too.
    assert "lead made narrator narrator." in messages


# --- printing ----------------------------------------------------------------------------------


def test_printing_shows_the_sheet_as_it_stands_with_waiting_disciplines_marked(
    troupe: Troupe,
) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "Brawl", 2)
    make_home(troupe, character_id)
    buy(troupe.player, character_id, "Dodge", 1)
    buy(troupe.player, character_id, "Celerity", 1, "disciplines")

    printed = troupe.player.client.get(f"/characters/{character_id}/print").json()

    assert (printed["home"], printed["troupe_name"], printed["accepted_by"]) == (
        True,
        "Lords of the Night",
        "lead",
    )
    traits = {t["name"]: t for t in printed["traits"]}
    assert {"Brawl", "Dodge", "Celerity"} <= traits.keys()
    assert traits["Brawl"]["attribute"] == "Physical"
    assert (traits["Celerity"]["pending_from"], traits["Dodge"]["pending_from"]) == (0, None)


def test_a_vault_character_prints_with_no_troupe(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    printed = troupe.player.client.get(f"/characters/{character_id}/print").json()

    assert (printed["home"], printed["troupe_name"]) == (False, None)
    assert troupe.narrator.client.get(f"/characters/{character_id}/print").status_code == 404
