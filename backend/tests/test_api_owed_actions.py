"""Learning a discipline or buying a merit takes downtime actions (MET: VTM pp. 111, 236)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe
from tests.test_api_downtimes import member_character, my_downtime, new_cycle, open_cycle

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(person: Person, character_id: str, category: str, name: str, rating: int) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )


def approve_all(troupe: Troupe) -> None:
    for request in troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json():
        troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})


def general(troupe: Troupe, character_id: str) -> int:
    return my_downtime(troupe.player, character_id).json()["allowance"]["general"]


def test_an_approved_discipline_dot_costs_the_next_cycle_an_action(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    take(troupe.player, agnes, "disciplines", "Celerity", 1)
    approve_all(troupe)

    open_cycle(troupe, new_cycle(troupe))

    assert general(troupe, agnes) == 2
    downtime = my_downtime(troupe.player, agnes).json()
    assert "Learning Celerity 1" in [a["reason"] for a in downtime["adjustments"]]


def test_while_a_cycle_is_open_the_action_comes_off_it(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    assert general(troupe, agnes) == 3

    take(troupe.player, agnes, "merits", "Acute Sense", 1)

    assert general(troupe, agnes) == 2


def test_efficient_learner_needs_no_downtime_to_learn(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    take(troupe.player, agnes, "merits", "Efficient Learner", 2)  # costs one action itself
    take(troupe.player, agnes, "disciplines", "Celerity", 1)
    approve_all(troupe)

    open_cycle(troupe, new_cycle(troupe))

    assert general(troupe, agnes) == 2


def test_hunted_characters_spend_two_actions_staying_hidden(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    take(troupe.player, agnes, "flaws", "Hunted", 4)

    open_cycle(troupe, new_cycle(troupe))

    assert general(troupe, agnes) == 1


def test_a_discipline_request_names_its_teacher(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")

    troupe.player.client.put(
        f"/characters/{agnes}/traits",
        json={"category": "disciplines", "name": "Auspex", "rating": 1, "teacher": "Marcus"},
    )

    [request] = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()
    assert request["discipline"]["teacher"] == "Marcus"
