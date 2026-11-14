"""Summoned allies on the Play View (issue #827): a power's use calls them up, each
with its own health levels to tap, and they are gone when dismissed or the game ends."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe, new_character
from tests.test_api_play import send, tap, texts, view
from tests.test_api_play_powers import give


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def lasombra(troupe: Troupe, session: Session) -> str:
    """A character with Obtenebration 3: three Arms of the Abyss at once."""
    character_id = new_character(troupe, troupe.player, "Ines")
    give(session, character_id, "disciplines", "Obtenebration", 3)
    return character_id


def arms(state: dict[str, Any]) -> dict[str, Any]:
    return next(s for s in state["summons"] if s["key"] == "Arms of the Abyss")


def test_the_play_view_lists_what_the_powers_can_call_up(troupe: Troupe, lasombra: str) -> None:
    found = arms(view(troupe.player, lasombra))
    assert (found["name"], found["most"], found["page"]) == ("Arm of the Abyss", 3, "pp. 148-149")
    assert [a["name"] for a in found["allies"]] == [
        "Arm of the Abyss 1",
        "Arm of the Abyss 2",
        "Arm of the Abyss 3",
    ]
    assert not any(a["out"] for a in found["allies"])
    assert found["allies"][0]["health"] == {"value": 4, "most": 4, "start": 4}
    # The power's use calls them all up, for its 1 Blood.
    [power] = [
        p
        for d in troupe.player.client.get(f"/characters/{lasombra}/play/reference").json()[
            "disciplines"
        ]
        for p in d["powers"]
        if p["name"] == "Arms of the Abyss"
    ]
    [use] = power["uses"]
    assert (use["summon"], use["summon_all"]) == ("Arms of the Abyss", True)


def test_allies_are_called_up_hurt_dismissed_and_gone_next_game(
    troupe: Troupe, lasombra: str
) -> None:
    state = send(
        troupe.player,
        lasombra,
        tap("blood", -1, at=0, note="Arms of the Abyss"),
        tap("ally:Arms of the Abyss#1", 1, at=1),
        tap("ally:Arms of the Abyss#2", 1, at=2),
        tap("ally:Arms of the Abyss#1/health", -3, at=3),
        tap("ally:Arms of the Abyss#2", -1, at=4),
    )
    found = {a["key"]: a for a in arms(state)["allies"]}
    first = found["ally:Arms of the Abyss#1"]
    assert first["out"] and first["order"] == 1 and first["health"]["value"] == 1
    assert not found["ally:Arms of the Abyss#2"]["out"]
    assert "Called up Arm of the Abyss 1" in texts(state)
    assert "Arm of the Abyss 1: health 4 → 1" in texts(state)
    assert "Dismissed Arm of the Abyss 2" in texts(state)

    reset = troupe.player.client.post(f"/characters/{lasombra}/play/reset", json={})
    assert reset.status_code == 200, reset.text
    fresh = arms(reset.json())
    assert not any(a["out"] for a in fresh["allies"])
    assert fresh["allies"][0]["health"]["value"] == 4
