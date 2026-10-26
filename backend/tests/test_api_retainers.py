"""A character's Retainers: saving, the dots they add up to, who may link an NPC,
and the log."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def accepted(troupe: Troupe) -> str:
    character_id = new_character(troupe, troupe.player)
    request = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    ).json()
    troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    return character_id


def give_retainers(troupe: Troupe, character_id: str, rating: int) -> None:
    response = troupe.storyteller.client.post(
        f"/characters/{character_id}/give",
        json={
            "category": "backgrounds",
            "name": "Retainers",
            "rating": rating,
            "free": True,
            "reason": "test",
        },
    )
    assert response.status_code == 200, response.text


def put(person: Person, character_id: str, rows: list[dict[str, Any]]) -> Any:
    return person.client.put(f"/characters/{character_id}/retainers", json={"retainers": rows})


MARTA = {"name": "Marta, the driver", "dots": 3, "description": "Drives."}
PIKE = {"name": "Pike", "dots": 1}


def make_npc(troupe: Troupe, name: str = "Marta") -> str:
    response = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": name})
    assert response.status_code == 201, response.text
    npc_id: str = response.json()["id"]
    return npc_id


def test_a_player_lists_retainers_and_the_dots_add_up(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    give_retainers(troupe, character_id, 4)

    saved = put(troupe.player, character_id, [MARTA, PIKE])

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (body["rating"], body["total"]) == (4, 4)
    assert [r["name"] for r in body["retainers"]] == ["Marta, the driver", "Pike"]
    assert body["can_edit"] and not body["can_link"]
    # A dot bought and not yet given to a Retainer shows as a difference.
    body = put(troupe.player, character_id, [MARTA]).json()
    assert (body["rating"], body["total"]) == (4, 3)


def test_each_retainer_has_one_to_five_dots_and_a_name(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    for row in ({**PIKE, "dots": 6}, {**PIKE, "dots": 0}, {**PIKE, "name": "  "}):
        assert put(troupe.player, character_id, [row]).status_code == 422


def test_a_retainer_from_a_merit_is_not_counted(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    give_retainers(troupe, character_id, 3)
    ghost = {"name": "A wraith", "dots": 5, "from_merit": "Ghostly Retainer"}
    # Only a merit the character has.
    assert put(troupe.player, character_id, [ghost]).status_code == 409
    gave = troupe.storyteller.client.post(
        f"/characters/{character_id}/give",
        json={
            "category": "merits",
            "name": "Ghostly Retainer",
            "rating": 3,
            "free": True,
            "despite": True,
            "reason": "test",
        },
    )
    assert gave.status_code == 200, gave.text

    body = put(troupe.player, character_id, [MARTA, ghost]).json()

    assert body["total"] == 3
    assert body["retainers"][1]["from_merit"] == "Ghostly Retainer"


def test_a_lost_retainer_stays_listed_with_its_date(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    row = {**PIKE, "lost": "killed", "lost_on": "2026-10-20"}

    body = put(troupe.player, character_id, [row]).json()

    assert body["retainers"][0]["lost"] == "killed"
    assert body["retainers"][0]["lost_on"] == "2026-10-20"
    assert body["total"] == 1


def test_only_staff_link_a_retainer_to_an_npc(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    npc_id = make_npc(troupe)
    listed = put(troupe.player, character_id, [MARTA]).json()["retainers"][0]

    # The player's attempt to link is ignored.
    body = put(troupe.player, character_id, [{**listed, "npc_id": npc_id}]).json()
    assert body["retainers"][0]["npc_id"] is None

    body = put(troupe.storyteller, character_id, [{**listed, "npc_id": npc_id}]).json()
    assert body["can_link"]
    assert body["retainers"][0]["npc_id"] == npc_id
    assert body["retainers"][0]["npc_name"] == "Marta"
    # The player edits on, and the link stays; they cannot see the NPC.
    body = put(troupe.player, character_id, [{**listed, "npc_id": None, "dots": 2}]).json()
    assert body["retainers"][0]["dots"] == 2
    assert body["retainers"][0]["npc_id"] is None
    again = troupe.storyteller.client.get(f"/characters/{character_id}/retainers").json()
    assert again["retainers"][0]["npc_id"] == npc_id


def test_a_link_must_be_an_npc_of_the_home_troupe(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    other = new_character(troupe, troupe.player, "Beatrice")
    listed = put(troupe.player, character_id, [MARTA]).json()["retainers"][0]

    refused = put(troupe.storyteller, character_id, [{**listed, "npc_id": other}])

    assert refused.status_code == 409


def test_others_cannot_change_or_see_the_list(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    assert put(troupe.stranger, character_id, [PIKE]).status_code == 404
    assert put(troupe.narrator, character_id, [PIKE]).status_code == 404
    assert put(troupe.assistant, character_id, [PIKE]).status_code == 200


def test_changes_are_on_the_characters_log(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    listed = put(troupe.player, character_id, [MARTA, PIKE]).json()["retainers"]
    put(troupe.player, character_id, [{**listed[0], "dots": 2, "lost": "released"}])

    log = troupe.player.client.get(f"/characters/{character_id}/log").json()
    actions = [e["action"] for e in log]

    assert actions.count("retainer.added") == 2
    assert "retainer.changed" in actions
    assert "retainer.lost" in actions
    assert "retainer.removed" in actions


def test_the_printed_sheet_and_play_reference_list_them(troupe: Troupe) -> None:
    character_id = accepted(troupe)
    put(troupe.player, character_id, [MARTA, PIKE])

    printed = troupe.player.client.get(f"/characters/{character_id}/print").json()
    reference = troupe.player.client.get(f"/characters/{character_id}/play/reference").json()

    assert [r["name"] for r in printed["retainers"]] == ["Marta, the driver", "Pike"]
    assert [r["dots"] for r in reference["retainers"]] == [3, 1]
