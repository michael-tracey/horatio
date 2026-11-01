"""Renaming characters: players once every three months, the custodian any time."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Character
from horatio.renames import add_months
from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def rename(person: Person, character_id: str, name: str) -> Any:
    return person.client.patch(f"/characters/{character_id}", json={"name": name})


def renamed(person: Person, character_id: str, name: str) -> dict[str, Any]:
    response = rename(person, character_id, name)
    assert response.status_code == 200, response.text
    return response.json()


def at_home(troupe: Troupe, name: str = "Agnes Moreau", player: Person | None = None) -> str:
    player = player or troupe.player
    character_id = new_character(troupe, player, name)
    request = player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    approved = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    return character_id


def other_troupe(troupe: Troupe, name: str = "Elsewhere") -> str:
    response = troupe.custodian.client.post(
        "/troupes", json={"name": name, "lead_handle": troupe.stranger.handle}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def visit(person: Person, character_id: str, troupe_id: str) -> None:
    response = person.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe_id}
    )
    assert response.status_code == 201, response.text


def renamed_on(troupe: Troupe, character_id: str, day: date) -> None:
    character = troupe.session.get_one(Character, uuid.UUID(character_id))
    character.renamed_at = datetime.combine(day, time(12), UTC)
    troupe.session.flush()


def summaries(person: Person) -> list[str]:
    response = person.client.get("/notifications")
    assert response.status_code == 200, response.text
    return [i["summary"] for i in response.json()["items"] if not i["task"]]


def troupe_log(person: Person, troupe_id: str) -> list[str]:
    return [e["message"] for e in person.client.get(f"/troupes/{troupe_id}/log").json()]


def character_log(person: Person, character_id: str) -> list[str]:
    return [e["message"] for e in person.client.get(f"/characters/{character_id}/log").json()]


def test_three_months_are_calendar_months() -> None:
    assert add_months(date(2026, 10, 19), 3) == date(2027, 1, 19)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2027, 11, 30), 3) == date(2028, 2, 29)
    assert add_months(date(2026, 12, 31), 3) == date(2027, 3, 31)
    assert add_months(date(2027, 1, 19), -3) == date(2026, 10, 19)


def test_a_character_in_no_troupe_is_renamed_at_will(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, "Agnes Moreau")
    # Even a name a troupe already has: no troupe has this character yet.
    at_home(troupe, "Agnes Duval", player=troupe.stranger)

    renamed(troupe.player, character_id, "Agnes Duval")
    character = renamed(troupe.player, character_id, "Agnes Lemaire")

    assert character["name"] == "Agnes Lemaire"
    assert character["next_rename_on"] is None
    assert troupe.session.get_one(Character, uuid.UUID(character_id)).renamed_at is None
    assert summaries(troupe.lead) == []
    assert character_log(troupe.player, character_id)[:2] == [
        "player renamed Agnes Duval to Agnes Lemaire.",
        "player renamed Agnes Moreau to Agnes Duval.",
    ]


def test_a_player_renames_once_every_three_months(troupe: Troupe) -> None:
    character_id = at_home(troupe)

    character = renamed(troupe.player, character_id, "Agnes Duval")

    next_on = add_months(datetime.now(UTC).date(), 3)
    assert character["next_rename_on"] == next_on.isoformat()
    response = rename(troupe.player, character_id, "Agnes Lemaire")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Agnes Duval was renamed less than 3 months ago; you can rename it again on"
        f" {next_on.day} {next_on:%B %Y}."
    )


def test_the_three_months_end_on_the_same_day_three_months_on(troupe: Troupe) -> None:
    character_id = at_home(troupe)
    three_months_ago = add_months(datetime.now(UTC).date(), -3)

    renamed_on(troupe, character_id, three_months_ago + timedelta(days=1))
    assert rename(troupe.player, character_id, "Agnes Duval").status_code == 409

    renamed_on(troupe, character_id, three_months_ago)
    assert troupe.player.client.get(f"/characters/{character_id}").json()["next_rename_on"] is None
    assert renamed(troupe.player, character_id, "Agnes Duval")["name"] == "Agnes Duval"


def test_renames_before_joining_a_troupe_do_not_count(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, "Agnes")
    renamed(troupe.player, character_id, "Agnes Moreau")

    visit(troupe.player, character_id, troupe.id)

    assert renamed(troupe.player, character_id, "Agnes Duval")["next_rename_on"] is not None


def test_the_custodian_renames_any_time_without_starting_the_clock(troupe: Troupe) -> None:
    character_id = at_home(troupe)

    renamed(troupe.custodian, character_id, "Agnes Duval")
    renamed(troupe.custodian, character_id, "Agnes Lemaire")

    assert troupe.session.get_one(Character, uuid.UUID(character_id)).renamed_at is None
    # The player still has their rename.
    renamed(troupe.player, character_id, "Agnes Moreau")
    # And within their three months, the custodian can still rename.
    assert renamed(troupe.custodian, character_id, "Agnes Bisset")["name"] == "Agnes Bisset"
    after = troupe.player.client.get(f"/characters/{character_id}").json()
    assert after["next_rename_on"] == add_months(datetime.now(UTC).date(), 3).isoformat()


def test_names_must_be_free_in_the_home_and_visited_troupes(troupe: Troupe) -> None:
    elsewhere = other_troupe(troupe)
    character_id = at_home(troupe)
    visit(troupe.player, character_id, elsewhere)
    at_home(troupe, "Agnes Duval", player=troupe.stranger)
    visiting = new_character(troupe, troupe.stranger, "Marcel Roux")
    visit(troupe.stranger, visiting, elsewhere)

    home_clash = rename(troupe.player, character_id, "  agnes DUVAL ")
    visit_clash = rename(troupe.player, character_id, "MARCEL ROUX")
    by_custodian = rename(troupe.custodian, character_id, "Agnes Duval")

    assert home_clash.status_code == 409
    assert home_clash.json()["detail"] == (
        "A character in Lords of the Night is already called agnes DUVAL."
    )
    assert visit_clash.json()["detail"] == "A character in Elsewhere is already called MARCEL ROUX."
    assert by_custodian.status_code == 409
    assert "stranger" not in home_clash.text + visit_clash.text
    # Its own name, in other letters, is no clash; the name is kept without the spaces.
    assert renamed(troupe.player, character_id, " agnes moreau ")["name"] == "agnes moreau"


def test_a_player_rename_tells_the_running_staff_of_each_troupe(troupe: Troupe) -> None:
    elsewhere = other_troupe(troupe)
    character_id = at_home(troupe)
    visit(troupe.player, character_id, elsewhere)

    renamed(troupe.player, character_id, "Agnes Duval")

    told = "Agnes Moreau is now called Agnes Duval"
    for person in (troupe.lead, troupe.storyteller, troupe.assistant, troupe.stranger):
        assert summaries(person) == [told]
    for person in (troupe.narrator, troupe.player, troupe.custodian):
        assert told not in summaries(person)


def test_a_custodian_rename_tells_the_player_and_the_staff_of_their_troupes(
    troupe: Troupe,
) -> None:
    elsewhere = other_troupe(troupe)
    character_id = at_home(troupe)
    # The player's other character is in another troupe; its staff hear too.
    other_id = new_character(troupe, troupe.player, "Marcel Roux")
    visit(troupe.player, other_id, elsewhere)

    renamed(troupe.custodian, character_id, "Agnes Duval")

    assert summaries(troupe.player) == ["The custodian renamed Agnes Moreau to Agnes Duval"]
    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert summaries(person) == ["Agnes Moreau is now called Agnes Duval"]
    assert summaries(troupe.stranger) == [
        "player's character Agnes Moreau is now called Agnes Duval"
    ]
    assert summaries(troupe.narrator) == []
    assert summaries(troupe.custodian) == []


def test_a_custodian_rename_outside_any_troupe_tells_no_one(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, "Agnes Moreau")

    renamed(troupe.custodian, character_id, "Agnes Duval")

    assert summaries(troupe.player) == []


def test_renames_are_logged_and_old_entries_keep_the_old_name(troupe: Troupe) -> None:
    elsewhere = other_troupe(troupe)
    character_id = at_home(troupe)
    visit(troupe.player, character_id, elsewhere)

    renamed(troupe.player, character_id, "Agnes Duval")
    renamed(troupe.custodian, character_id, "Agnes Lemaire")

    for person, troupe_id in ((troupe.lead, troupe.id), (troupe.stranger, elsewhere)):
        assert troupe_log(person, troupe_id)[:2] == [
            "custodian renamed Agnes Duval to Agnes Lemaire (player).",
            "player renamed Agnes Moreau to Agnes Duval.",
        ]
    assert "Agnes Moreau (player) started visiting the troupe." in troupe_log(
        troupe.stranger, elsewhere
    )
    # Recorded in both troupes, it reads once in the character's own history.
    assert character_log(troupe.player, character_id)[:3] == [
        "custodian renamed Agnes Duval to Agnes Lemaire (player).",
        "player renamed Agnes Moreau to Agnes Duval.",
        "Agnes Moreau (player) started visiting the troupe.",
    ]
    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    assert [e["character_name"] for e in roster] == ["Agnes Lemaire"]


def test_only_the_player_and_the_custodian_rename_a_character(troupe: Troupe) -> None:
    character_id = at_home(troupe)

    assert rename(troupe.storyteller, character_id, "Agnes Duval").status_code == 403
    assert rename(troupe.stranger, character_id, "Agnes Duval").status_code == 404
    assert rename(troupe.player, character_id, "   ").status_code == 422

    troupe.player.client.post(f"/characters/{character_id}/retire")
    assert rename(troupe.player, character_id, "Agnes Duval").status_code == 409
    assert renamed(troupe.custodian, character_id, "Agnes Duval")["name"] == "Agnes Duval"


def test_staff_rename_their_npcs_without_a_limit(troupe: Troupe) -> None:
    created = troupe.lead.client.post(
        f"/troupes/{troupe.id}/npcs", json={"splat": "vampire", "name": "Prince Vasquez"}
    )
    assert created.status_code == 201, created.text
    npc_id = created.json()["id"]
    at_home(troupe, "Agnes Moreau")

    renamed(troupe.storyteller, npc_id, "Prince Ortega")
    renamed(troupe.assistant, npc_id, "Prince Alvarez")

    assert rename(troupe.lead, npc_id, "agnes moreau").status_code == 409
    assert summaries(troupe.lead) == []
    # The custodian's rename is news to the troupe's staff, and only to them.
    elsewhere = other_troupe(troupe)
    visit(troupe.lead, new_character(troupe, troupe.lead, "Lead's own"), elsewhere)
    renamed(troupe.custodian, npc_id, "Prince Ortega")
    assert summaries(troupe.storyteller) == ["Prince Alvarez is now called Prince Ortega"]
    assert summaries(troupe.stranger) == []
