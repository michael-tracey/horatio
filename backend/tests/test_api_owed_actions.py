"""Learning a discipline or buying a merit takes downtime actions (MET: VTM pp. 111, 236)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, finish, new_character
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
    approve_all(troupe)  # once accepted, a merit is asked of staff

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
    approve_all(troupe)

    open_cycle(troupe, new_cycle(troupe))

    assert general(troupe, agnes) == 1


def test_hunted_says_what_its_actions_are_for_and_when_the_allowance_falls_short(
    troupe: Troupe,
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    take(troupe.player, agnes, "flaws", "Hunted", 4)
    take(troupe.player, agnes, "merits", "Acute Sense", 1)  # one action, owed
    take(troupe.player, agnes, "merits", "Efficient Learner", 2)  # and another
    approve_all(troupe)

    open_cycle(troupe, new_cycle(troupe))

    downtime = my_downtime(troupe.player, agnes).json()
    hunted = next(b for b in downtime["breakdown"] if b["source"] == "Hunted")
    assert hunted["amount"] == -2
    assert "Healthy track full of aggravated damage" in hunted["note"]
    # 3, less Hunted's 2 and the two merits': one short.
    assert (downtime["allowance"]["general"], downtime["short"]) == (0, {"general": 1})


def member_with(troupe: Troupe, name: str, clan: str, *traits: tuple[str, str, int]) -> str:
    """A character of `clan` holding `traits` from creation, accepted home."""
    character_id = new_character(troupe, troupe.player, name, clan=clan, finished=False)
    # Taken on the Merits & flaws step: some, such as Black Sheep, are creation-only.
    for category in {category for category, _, _ in traits}:
        picks = [{"name": trait} for c, trait, _ in traits if c == category]
        placed = troupe.player.client.put(
            f"/characters/{character_id}/creation/categories/{category}", json={"picks": picks}
        )
        assert placed.status_code == 200, placed.text
    finish(troupe, character_id)
    asked = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text
    approved = troupe.lead.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    return character_id


def test_a_black_sheep_has_one_action_fewer_and_is_told_why(troupe: Troupe) -> None:
    agnes = member_with(troupe, "Agnes", "Brujah", ("flaws", "Black Sheep", 2))

    open_cycle(troupe, new_cycle(troupe))

    downtime = my_downtime(troupe.player, agnes).json()
    assert downtime["allowance"]["general"] == 2
    sheep = next(b for b in downtime["breakdown"] if b["source"] == "Black Sheep")
    assert sheep["amount"] == -1
    assert "p. 487" in sheep["note"]


def test_a_discipline_illiterate_caitiff_takes_two_actions_for_an_out_of_clan_dot(
    troupe: Troupe,
) -> None:
    agnes = member_with(troupe, "Agnes", "Caitiff", ("flaws", "Caitiff: Discipline Illiterate", 1))
    take(troupe.player, agnes, "disciplines", "Celerity", 1)
    approve_all(troupe)

    open_cycle(troupe, new_cycle(troupe))

    downtime = my_downtime(troupe.player, agnes).json()
    assert downtime["allowance"]["general"] == 1
    assert [(a["delta"], a["reason"]) for a in downtime["adjustments"]] == [
        (-2, "Learning Celerity 1 (Caitiff: Discipline Illiterate: 1 more a dot)")
    ]


def test_discipline_illiterate_takes_away_efficient_learners_help(troupe: Troupe) -> None:
    agnes = member_with(
        troupe,
        "Agnes",
        "Caitiff",
        ("flaws", "Caitiff: Discipline Illiterate", 1),
        ("merits", "Efficient Learner", 2),
    )
    take(troupe.player, agnes, "disciplines", "Celerity", 1)
    approve_all(troupe)

    open_cycle(troupe, new_cycle(troupe))

    [learning] = my_downtime(troupe.player, agnes).json()["adjustments"]
    assert learning["delta"] == -2
    assert (
        "Efficient Learner does not help, under Caitiff: Discipline Illiterate"
        in (learning["reason"])
    )


def test_a_discipline_request_names_its_teacher(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")

    troupe.player.client.put(
        f"/characters/{agnes}/traits",
        json={"category": "disciplines", "name": "Auspex", "rating": 1, "teacher": "Marcus"},
    )

    [request] = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json()
    assert request["discipline"]["teacher"] == "Marcus"
