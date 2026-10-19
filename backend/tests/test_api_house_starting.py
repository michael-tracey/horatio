"""Troupes change what new characters start with: the creation rules for a category."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_creation import creation, pick, pool

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def starting(troupe: Troupe, person: Person | None = None) -> dict[str, dict[str, Any]]:
    response = (person or troupe.storyteller).client.get(f"/troupes/{troupe.id}/creation")
    assert response.status_code == 200, response.text
    return {c["key"]: c for c in response.json()}


def change(
    troupe: Troupe, category: str, rules: list[dict[str, Any]], person: Person | None = None
) -> Any:
    return (person or troupe.storyteller).client.put(
        f"/troupes/{troupe.id}/creation/{category}", json={"rules": rules}
    )


def built_for(troupe: Troupe, clan: str = "Brujah") -> str:
    response = troupe.player.client.post(
        "/characters",
        json={"splat": "vampire", "name": "Agnes", "building_troupe_id": troupe.id},
    )
    character_id = response.json()["id"]
    troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": clan, "rating": None},
    )
    return character_id


def test_the_rule_sets_starting_points_in_plain_words(troupe: Troupe) -> None:
    listed = starting(troupe, troupe.assistant)

    assert listed["skills"]["text"] == "1 at 4, 2 at 3, 3 at 2, 4 at 1"
    assert listed["merits"]["text"] == "7 points"
    assert listed["disciplines"]["text"] == (
        "1 at 2 in-clan (without Thin Blooded); 2 at 1 in-clan"
    )
    assert not listed["skills"]["house"]
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/creation").status_code == 403


def test_a_troupe_changes_a_category_and_its_characters_build_by_it(troupe: Troupe) -> None:
    character_id = built_for(troupe)
    elsewhere = new_character(troupe, troupe.player, "Bram", finished=False)
    rules = [{"rating": 4, "picks": 2}, {"rating": 2, "picks": 3}]

    assert change(troupe, "skills", rules, troupe.assistant).status_code == 403
    changed = change(troupe, "skills", rules)

    assert changed.status_code == 200, changed.text
    assert (changed.json()["text"], changed.json()["house"]) == ("2 at 4, 3 at 2", True)
    assert changed.json()["book_text"] == "1 at 4, 2 at 3, 3 at 2, 4 at 1"
    # A character being built for the troupe sees the new pools at once…
    state = creation(troupe.player, character_id)
    assert pool(state, "skills", 4)["allowed"] == 2
    assert not [p for p in state["pools"] if p["category"] == "skills" and p["rating"] == 3]
    assert pick(troupe.player, character_id, "skills", "Brawl", 4).status_code == 200
    assert pick(troupe.player, character_id, "skills", "Dodge", 4).status_code == 200
    assert pick(troupe.player, character_id, "skills", "Melee", 3).status_code == 422
    # …and one built by the plain rules does not.
    assert pool(creation(troupe.player, elsewhere), "skills", 3)["allowed"] == 2
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller set the troupe's starting Skills: 2 at 4, 3 at 2." in log


def test_a_budget_and_a_condition_copied_from_the_book(troupe: Troupe) -> None:
    character_id = built_for(troupe)
    book = starting(troupe)["disciplines"]["book"]
    # Three discipline dots at 1, of any clan; the book's 2-dot pick, with its
    # condition, stays.
    merged = [r for r in book if r["rating"] == 2] + [{"rating": 1, "picks": 3}]

    assert change(troupe, "disciplines", merged).status_code == 200
    assert change(troupe, "merits", [{"points": 9}]).json()["text"] == "9 points"
    state = creation(troupe.player, character_id)
    assert pool(state, "merits", 0)["allowed"] == 9
    assert pool(state, "disciplines", 1)["allowed"] == 3
    assert pool(state, "disciplines", 2)["allowed"] == 1
    assert starting(troupe)["disciplines"]["rules"][0]["when_text"] == "without Thin Blooded"


def test_rules_that_could_not_be_built_with_are_refused(troupe: Troupe) -> None:
    assert change(troupe, "skills", []).status_code == 422
    assert (
        change(troupe, "skills", [{"rating": 4, "picks": 1}, {"rating": 4, "picks": 2}]).status_code
        == 422
    )
    assert change(troupe, "skills", [{"points": 3}, {"rating": 1, "picks": 1}]).status_code == 422
    assert (
        change(troupe, "skills", [{"rating": 2, "picks": 1, "restriction": "rich"}]).status_code
        == 422
    )
    made_up = [{"rating": 2, "picks": 1, "when": {"clan": ["Tremere"]}}]
    assert change(troupe, "skills", made_up).status_code == 422
    assert change(troupe, "rituals", [{"rating": 1, "picks": 1}]).status_code == 404


def test_going_back_to_the_book(troupe: Troupe) -> None:
    change(troupe, "skills", [{"rating": 5, "picks": 1}])

    reset = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/creation/skills")

    assert reset.status_code == 200, reset.text
    assert (reset.json()["text"], reset.json()["house"]) == (
        "1 at 4, 2 at 3, 3 at 2, 4 at 1",
        False,
    )
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert (
        "storyteller put the starting Skills back to the rule set's: "
        "1 at 4, 2 at 3, 3 at 2, 4 at 1." in log
    )
