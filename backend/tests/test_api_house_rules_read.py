"""Players read what their troupe plays differently from the book: only the house
rules, each beside the rule set's it replaces, and nothing only staff see."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def house_rules(troupe: Troupe, person: Person) -> dict[str, Any]:
    response = person.client.get(f"/troupes/{troupe.id}/house-rules")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_troupe_as_written_has_nothing_to_list(troupe: Troupe) -> None:
    read = house_rules(troupe, troupe.player)

    assert [(s["splat"], s["costs"], s["starting"], s["actions"]) for s in read["splats"]] == [
        ("vampire", [], [], [])
    ]
    assert (read["checks"], read["house_traits"], read["other"]) == ([], [], [])
    assert read["backstory_mode"] == "free"


def test_players_read_each_house_rule_beside_the_books(troupe: Troupe) -> None:
    st = troupe.storyteller.client
    added = st.post(
        f"/troupes/{troupe.id}/costs",
        json={
            "category": "skills",
            "condition": {"generation": 1},
            "scheme": "per_dot",
            "rate": 1,
            "text": "Skills come easily here",
        },
    )
    assert added.status_code == 201, added.text
    st.post(
        f"/troupes/{troupe.id}/costs",
        json={"category": "attributes", "scheme": "per_dot", "rate": 4},
    )
    st.put(f"/troupes/{troupe.id}/creation/merits", json={"rules": [{"points": 5}]})
    st.post(f"/troupes/{troupe.id}/allowances", json={"action_kind": "general", "amount": 4})
    st.put(f"/troupes/{troupe.id}/checks/merits/Calm Heart/1", json={"strength": "note"})
    st.put(f"/troupes/{troupe.id}/starting-blood", json={"blood": 5})
    st.put(f"/troupes/{troupe.id}/golconda", json={"on": True})
    made = st.post(
        f"/troupes/{troupe.id}/house-traits",
        json={
            "category": "merits",
            "name": "Child of the Crossroads",
            "points": 2,
            "availability": "building",
            "description": "Knows every back road out of town.",
        },
    )
    assert made.status_code == 201, made.text
    archived = st.post(
        f"/troupes/{troupe.id}/house-traits",
        json={"category": "flaws", "name": "Old Debt", "points": 1, "availability": "staff"},
    ).json()
    st.put(f"/troupes/{troupe.id}/house-traits/{archived['id']}/archived", json={"archived": True})

    read = house_rules(troupe, troupe.stranger)

    vampire = read["splats"][0]
    costs = {c["subject"]: c for c in vampire["costs"]}
    assert costs["All Attributes"] | {"page": None} == {
        "category": "Attributes",
        "subject": "All Attributes",
        "price_text": "4 XP per dot",
        "book_text": "3 XP per dot",
        "text": None,
        "page": None,
    }
    skills = costs["All Skills, Generation background 1"]
    assert (skills["price_text"], skills["book_text"], skills["text"]) == (
        "1 XP per dot",
        "1 XP × the new rating",
        "Skills come easily here",
    )
    assert vampire["starting"] == [
        {"category": "Merits", "text": "5 points", "book_text": "7 points"}
    ]
    assert vampire["actions"] == [
        {"who": "Everyone", "amount_text": "4 downtime actions", "book_text": "3 downtime actions"}
    ]
    [check] = read["checks"]
    assert (check["strength"], check["house"]) == ("refuse", "note")
    assert "Calm Heart" in check["rule"]
    # Only merits and flaws still offered; never how many hold one.
    [merit] = read["house_traits"]
    assert (merit["name"], merit["availability"]) == ("Child of the Crossroads", "building")
    assert "holders" not in merit
    other = {s["name"]: (s["text"], s["book_text"]) for s in read["other"]}
    assert other["Blood at the start of a game"] == ("5 Blood", "Full")
    assert "Golconda and Enlightened" in other


def test_an_archived_troupe_is_not_found(troupe: Troupe) -> None:
    troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"})

    assert troupe.player.client.get(f"/troupes/{troupe.id}/house-rules").status_code == 404
    assert troupe.custodian.client.get(f"/troupes/{troupe.id}/house-rules").status_code == 200
