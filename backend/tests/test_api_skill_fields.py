"""Skills bought once per field: Crafts, Performance and Science (MET: VTM p. 92,
issue #58). The field is chosen when adding one, so they are never greyed out for
lacking it."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe, new_character, without_starting_traits

FIELDED = ("Crafts", "Performance", "Science")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def unavailable(troupe: Troupe, character_id: str, **params: object) -> dict[str, str]:
    response = troupe.player.client.get(
        f"/characters/{character_id}/unavailable", params={"category": "skills", **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_skills_with_fields_can_be_chosen(troupe: Troupe) -> None:
    finished = new_character(troupe, troupe.player)
    building = new_character(troupe, troupe.player, "Bertha", finished=False)
    for character_id, params in (
        (finished, {}),
        (building, {"as_if": "picks", "picks": []}),
        (building, {"as_if": "empty"}),
    ):
        refused = unavailable(troupe, character_id, **params)
        assert not set(FIELDED) & set(refused), refused


def test_each_field_is_its_own_skill_with_its_own_specialization(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    for field in ("Singing", "Dancing"):
        bought = troupe.player.client.put(
            f"/characters/{character_id}/traits",
            json={"category": "skills", "name": "Performance", "detail": field, "rating": 1},
        )
        assert bought.status_code == 200, bought.text
    skills = [
        (t["name"], t["detail"])
        for t in without_starting_traits(bought.json()["sheet"]["traits"])
        if t["category"] == "skills"
    ]
    assert skills == [("Performance", "Dancing"), ("Performance", "Singing")]
    # A third field is still on offer.
    assert "Performance" not in unavailable(troupe, character_id)
    sheet = troupe.player.client.get(f"/characters/{character_id}/sheet").json()
    assert not [p for p in sheet["problems"] if "need a field" in p["message"]]


def test_the_wizard_takes_one_with_its_field(troupe: Troupe) -> None:
    building = new_character(troupe, troupe.player, "Bertha", finished=False)
    saved = troupe.player.client.put(
        f"/characters/{building}/creation/categories/skills",
        json={"picks": [{"name": "Performance", "rating": 3, "detail": "Singing"}]},
    )
    assert saved.status_code == 200, saved.text
    picks = [
        (t["name"], t["detail"], t["pick"])
        for pool in saved.json()["pools"]
        if pool["category"] == "skills"
        for t in pool["traits"]
    ]
    assert picks == [("Performance", "Singing", 3)]
