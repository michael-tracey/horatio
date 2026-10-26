"""The Play View of a Stock NPC (issue #215; MET: VTM p. 490): its kind's resource
in Blood's place and its health levels, tapped, logged, undone and reset like
anyone's, with no Willpower, Morality or Beast traits."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe
from tests.test_api_play import send, tap, texts, view


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def stock_npc(troupe: Troupe, kind: str, rating: int, **extra: Any) -> str:
    response = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs",
        json={
            "name": "Bites-the-Hand",
            "npc_kind": kind,
            "npc_form": "stock",
            "stock": {"rating": rating},
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_a_stock_werewolf_has_rage_and_twice_its_rating_in_health(troupe: Troupe) -> None:
    wolf = stock_npc(troupe, "werewolf", 3)
    state = view(troupe.storyteller, wolf)

    assert state["npc_form"] == "stock"
    assert state["blood_name"] == "Rage"
    assert state["blood"] == {"value": 10, "most": 10, "start": 10}
    # Up to 3 a turn (p. 494).
    assert state["blood_per_turn"] == 3
    assert [(h["name"], h["boxes"]) for h in state["health"]["levels"]] == [("Health levels", 6)]
    assert state["willpower"]["most"] == 0
    assert state["morality"] is None
    # The stat block comes with it, for the Stock Play View.
    assert state["stock"]["stats"]["pool"] == 6
    assert state["stock"]["kind"]["name"] == "Werewolf"
    assert state["stock"]["troupe_id"] == troupe.id


def test_a_stock_npc_spends_its_resource_and_takes_damage_logged_with_undo(troupe: Troupe) -> None:
    wolf = stock_npc(troupe, "werewolf", 3)
    rage = tap("blood", -3, at=1)
    send(troupe.storyteller, wolf, rage, tap("health", 2, at=2, damage="aggravated"))
    state = send(
        troupe.storyteller,
        wolf,
        {
            "id": str(uuid.uuid4()),
            "happened_at": tap(at=3)["happened_at"],
            "kind": "undo",
            "undoes": rage["id"],
        },
    )

    assert state["blood"]["value"] == 10
    assert state["health"]["marks"] == ["aggravated", "aggravated"]
    assert texts(state) == [
        "Undid: Rage 10 → 7",
        "Health: took 2 aggravated (0 → 2 marked)",
        "Rage 10 → 7",
    ]
    # No more damage than its health levels.
    assert send(troupe.storyteller, wolf, tap("health", 9, at=4, damage="normal"))["health"][
        "marks"
    ] == [
        "aggravated",
        "aggravated",
        "normal",
        "normal",
        "normal",
        "normal",
    ]


def test_a_stock_npc_has_no_willpower_or_beast_traits_to_tap(troupe: Troupe) -> None:
    hunter = stock_npc(troupe, "mortal", 2)
    state = send(troupe.storyteller, hunter, tap("willpower", -1), tap("beast", 1, at=1))

    assert state["willpower"]["value"] == 0
    assert state["beast"]["value"] == 0
    assert texts(state) == [
        "Beast traits +1 (not on the sheet now)",
        "Willpower −1 (not on the sheet now)",
    ]
    # A mortal's Blood: 5, and none to spend in a turn (p. 490).
    assert (state["blood_name"], state["blood"]["most"], state["blood_per_turn"]) == ("Blood", 5, 0)


def test_a_reset_puts_a_stock_npc_back_for_the_next_game(troupe: Troupe) -> None:
    wolf = stock_npc(troupe, "werewolf", 2)
    send(troupe.storyteller, wolf, tap("blood", -2), tap("health", 1, at=1, damage="normal"))
    response = troupe.storyteller.client.post(f"/characters/{wolf}/play/reset", json={})
    assert response.status_code == 200, response.text
    state = response.json()

    assert state["blood"]["value"] == 10
    assert state["health"]["marks"] == []
    assert state["game"]["number"] == 2
    games = troupe.storyteller.client.get(f"/characters/{wolf}/play/games").json()
    assert [g["taps"] for g in games] == [2]


def test_a_stock_npc_follows_its_rating_and_a_custom_kind(troupe: Troupe) -> None:
    angel = stock_npc(
        troupe,
        "custom",
        4,
        custom_kind={
            "name": "Angel",
            "nature": "supernatural",
            "resource": {"name": "Grace", "size": 7, "per_turn": 2},
        },
    )
    send(troupe.storyteller, angel, tap("blood", -2))
    state = view(troupe.storyteller, angel)

    assert (state["blood_name"], state["blood"], state["blood_per_turn"]) == (
        "Grace",
        {"value": 5, "most": 7, "start": 7},
        2,
    )
    assert state["health"]["levels"] == [{"name": "Health levels", "boxes": 4}]
    assert texts(state) == ["Grace 7 → 5"]


def test_a_sheeted_character_still_has_blood(troupe: Troupe) -> None:
    response = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": "Odile", "wizard": False}
    )
    state = view(troupe.storyteller, response.json()["id"])

    assert (state["npc_form"], state["stock"], state["blood_name"]) == ("sheeted", None, "Blood")
