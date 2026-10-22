"""Skills bought once per field: Crafts, Performance and Science (MET: VTM p. 92,
issue #58). The field is chosen when adding one, so they are never greyed out for
lacking it."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.rules.files import DATA_DIR, load_rule_set
from tests.api_helpers import Troupe, new_character, without_starting_traits

FIELDED = ("Crafts", "Performance", "Science")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def unavailable(troupe: Troupe, character_id: str, **params: str) -> dict[str, str]:
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


def needs(troupe: Troupe, character_id: str) -> list[dict[str, str]]:
    response = troupe.player.client.get(f"/characters/{character_id}/creation")
    assert response.status_code == 200, response.text
    return response.json()["needs"]


def test_the_skills_step_needs_a_field_before_moving_on(troupe: Troupe) -> None:
    building = new_character(troupe, troupe.player, "Bertha", finished=False)
    url = f"/characters/{building}/creation/categories/skills"
    saved = troupe.player.client.put(url, json={"picks": [{"name": "Science", "rating": 2}]})
    assert saved.status_code == 200, saved.text
    assert [n for n in needs(troupe, building) if n["step"] == "skills"] == [
        {
            "step": "skills",
            "message": "Crafts, Performance and Science need a field,"
            " such as Performance: Singing. (p. 92)",
        }
    ]
    saved = troupe.player.client.put(
        url, json={"picks": [{"name": "Science", "rating": 2, "detail": "Chemistry"}]}
    )
    assert saved.status_code == 200, saved.text
    assert [n for n in needs(troupe, building) if n["step"] == "skills"] == []


def test_the_wizard_takes_two_fields_of_one_skill(troupe: Troupe) -> None:
    building = new_character(troupe, troupe.player, "Bertha", finished=False)
    saved = troupe.player.client.put(
        f"/characters/{building}/creation/categories/skills",
        json={
            "picks": [
                {"name": "Performance", "rating": 2, "detail": "Singing"},
                {"name": "Performance", "rating": 1, "detail": "Dance"},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    picks = sorted(
        (t["name"], t["detail"], t["pick"])
        for pool in saved.json()["pools"]
        if pool["category"] == "skills"
        for t in pool["traits"]
    )
    assert picks == [("Performance", "Dance", 1), ("Performance", "Singing", 2)]


def test_a_missing_field_can_be_given_to_a_pick(troupe: Troupe) -> None:
    """The Review step fills in a field without going back to Skills."""
    building = new_character(troupe, troupe.player, "Bertha", finished=False)
    saved = troupe.player.client.put(
        f"/characters/{building}/creation/categories/skills",
        json={"picks": [{"name": "Crafts", "rating": 3}]},
    )
    assert saved.status_code == 200, saved.text
    given = troupe.player.client.put(
        f"/characters/{building}/traits/detail",
        json={"category": "skills", "name": "Crafts", "detail": "Woodwork"},
    )
    assert given.status_code == 200, given.text
    assert [n for n in needs(troupe, building) if n["step"] == "skills"] == []
    picks = [
        (t["name"], t["detail"], t["pick"])
        for pool in troupe.player.client.get(f"/characters/{building}/creation").json()["pools"]
        if pool["category"] == "skills"
        for t in pool["traits"]
    ]
    assert picks == [("Crafts", "Woodwork", 3)]


def test_the_rules_say_which_skills_need_a_field(troupe: Troupe) -> None:
    catalogue = troupe.player.client.get("/rules/vampire").json()
    marked = sorted(t["name"] for t in catalogue["traits"] if t["needs_field"])
    assert marked == sorted(FIELDED)


def test_the_field_check_names_the_skills_the_catalogue_marks() -> None:
    """The traits' `requires_specialization` is the one list; the check must agree."""
    rules = load_rule_set(DATA_DIR / "bns_met_vampire.toml")
    marked = {
        name
        for (category, name), t in rules.traits.items()
        if category == "skills" and t.properties.get("requirement") == "requires_specialization"
    }
    [check] = [c for c in rules.checks if "need a field" in c.message]
    assert check.step == "skills"
    assert check.requires is not None
    named = next(set(c["not"]["self"]["names"]) for c in check.requires["any_of"] if "not" in c)
    assert named == marked
