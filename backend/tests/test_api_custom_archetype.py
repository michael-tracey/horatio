"""A custom archetype (p. 86): "Other…", named by the player, with a note on what it means."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def choose(person: Person, character_id: str, name: str, **body: Any) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "archetype", "name": name, "rating": None, **body},
    )


def archetype(person: Person, character_id: str) -> dict[str, Any]:
    sheet = person.client.get(f"/characters/{character_id}/sheet").json()
    return next(t for t in sheet["traits"] if t["category"] == "archetype")


def test_a_custom_archetype_keeps_its_name_and_description(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = choose(
        troupe.player,
        character_id,
        "Other…",
        detail="The Penitent Thief",
        note="Steals only what he means to give back.",
    )

    assert response.status_code == 200
    held = archetype(troupe.player, character_id)
    assert held["name"] == "Other…"
    assert held["detail"] == "The Penitent Thief"
    assert held["note"] == "Steals only what he means to give back."


def test_a_custom_archetype_needs_a_name(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert choose(troupe.player, character_id, "Other…", detail="  ").status_code == 422


def test_choosing_a_listed_archetype_drops_the_custom_one(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    choose(troupe.player, character_id, "Other…", detail="The Penitent Thief", note="Gives back.")

    choose(troupe.player, character_id, "Fighter")

    held = archetype(troupe.player, character_id)
    assert (held["name"], held["detail"], held["note"]) == ("Fighter", "", "")


def test_the_description_is_kept_short(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = choose(troupe.player, character_id, "Other…", detail="X", note="y" * 1001)

    assert response.status_code == 422
