"""Downtime actions aimed at characters (#507): who sees them, a Haven's Location
doubling their cost, and Computer's Cancel and Observe (MET: VTM pp. 93, 102)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import (
    member_character,
    my_downtime,
    new_cycle,
    open_cycle,
    question_id,
    save,
    set_questions,
)


class Scene:
    """Agnes, with the Computer skill; Basil; and Corvin, whose Haven has Location.
    Each has its own player, and an open cycle with a custom question too."""

    def __init__(self, client_for: Callable[[], TestClient], troupe: Troupe) -> None:
        self.troupe = troupe
        self.basil_player = sign_up(client_for, "basil_player")
        self.corvin_player = sign_up(client_for, "corvin_player")
        self.agnes = member_character(troupe, troupe.player, "Agnes")
        self.basil = member_character(troupe, self.basil_player, "Basil")
        self.corvin = member_character(troupe, self.corvin_player, "Corvin")
        self.give(self.agnes, "skills", "Computer", 1)
        self.give(self.corvin, "backgrounds", "Haven", 1)
        haven = troupe.storyteller.client.post(
            f"/troupes/{troupe.id}/locations",
            json={
                "name": "Corvin's townhouse",
                "kind": "haven",
                "rating": 1,
                "haven_of_id": self.corvin,
                "haven_advantages": ["Location"],
            },
        )
        assert haven.status_code == 201, haven.text
        cycle = new_cycle(troupe)
        cycle = set_questions(
            troupe, cycle, cycle["questions"] + [{"kind": "custom", "prompt": "Anything else?"}]
        )
        self.cycle = open_cycle(troupe, cycle)
        form = my_downtime(troupe.player, self.agnes).json()
        self.general = question_id(form, "Downtime action")
        self.custom = question_id(form, "Anything else?")

    def give(self, character_id: str, category: str, name: str, rating: int) -> None:
        given = self.troupe.storyteller.client.post(
            f"/characters/{character_id}/give",
            json={
                "category": category,
                "name": name,
                "detail": "",
                "rating": rating,
                "free": True,
                "reason": "x",
            },
        )
        assert given.status_code == 200, given.text

    def action(self, body: str, slot: int = 1, **structured: Any) -> dict[str, Any]:
        return {
            "question_id": self.general,
            "slot": slot,
            "body": body,
            "structured": structured,
        }

    def submit(self, player: Person, character_id: str, answers: list[dict[str, Any]]) -> None:
        saved = save(player, character_id, answers)
        assert saved.status_code == 200, saved.text
        submitted = player.client.post(f"/characters/{character_id}/downtime/submit")
        assert submitted.status_code == 200, submitted.text

    def aimed(self, person: Person | None = None) -> Any:
        return (person or self.troupe.storyteller).client.get(f"/cycles/{self.cycle['id']}/aimed")

    def response_id(self, answer: str) -> str:
        found = self.troupe.storyteller.client.get(f"/cycles/{self.cycle['id']}/responses").json()
        return next(r["id"] for r in found if r["answer"] == answer)


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(client_for, Troupe(client_for, session))


def test_players_aim_actions_at_the_troupes_characters(scene: Scene) -> None:
    form = my_downtime(scene.troupe.player, scene.agnes).json()
    assert [(t["name"], t["cost"]) for t in form["targets"]] == [("Basil", 1), ("Corvin", 2)]
    assert form["can_counter"] is True
    assert my_downtime(scene.basil_player, scene.basil).json()["can_counter"] is False

    saved = save(
        scene.troupe.player,
        scene.agnes,
        [scene.action("Tail Basil and Corvin", aimed_at=[scene.basil, scene.corvin])],
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["answers"][0]["structured"] == {"aimed_at": [scene.basil, scene.corvin]}

    # Not at itself, nor at someone outside the troupe, and only with an action.
    for bad in (
        [scene.action("Look in the mirror", aimed_at=[scene.agnes])],
        [scene.action("Spy", aimed_at=[scene.troupe.id])],
        [{"question_id": scene.custom, "body": "Hello", "structured": {"aimed_at": [scene.basil]}}],
    ):
        refused = save(scene.troupe.player, scene.agnes, bad)
        assert refused.status_code == 422, refused.text


def test_only_running_staff_see_who_an_action_is_aimed_at(scene: Scene) -> None:
    troupe = scene.troupe
    scene.submit(troupe.player, scene.agnes, [scene.action("Follow Basil", aimed_at=[scene.basil])])
    scene.submit(scene.basil_player, scene.basil, [scene.action("Paint the town")])

    groups = scene.aimed().json()
    assert [(g["character_name"], [a["character_name"] for a in g["actions"]]) for g in groups] == [
        ("Basil", ["Agnes"])
    ]
    action = groups[0]["actions"][0]
    assert (action["question"], action["answer"], action["located"]) == (
        "Downtime action",
        "Follow Basil",
        False,
    )
    assert action["response_id"] == scene.response_id("Follow Basil")
    assert troupe.assistant.client.get(f"/cycles/{scene.cycle['id']}/aimed").status_code == 200
    for outsider in (troupe.narrator, troupe.player, scene.basil_player):
        assert scene.aimed(outsider).status_code == 403

    # A narrator writing it sees the action, never whom it is aimed at.
    response_id = scene.response_id("Follow Basil")
    assigned = troupe.assistant.client.put(
        f"/responses/{response_id}/assignment", json={"user_id": troupe.narrator.id}
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["aim"]["targets"] == ["Basil"]
    mine = troupe.narrator.client.get(f"/cycles/{scene.cycle['id']}/responses/mine").json()
    assert [(r["answer"], r["structured"], r["aim"]) for r in mine] == [("Follow Basil", {}, None)]

    # Basil's player learns nothing of it: not on their form, nor in Basil's log.
    basil_form = my_downtime(scene.basil_player, scene.basil).json()
    assert "Agnes" not in str(basil_form["answers"])
    basil_log = scene.basil_player.client.get(f"/characters/{scene.basil}/log").json()
    assert not any("aimed" in e["message"] for e in basil_log)
    # The troupe's log, for its staff, notes it.
    log = troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()
    assert "Agnes's action “Downtime action” is aimed at Basil." in [e["message"] for e in log]


def test_a_havens_location_doubles_the_cost_unless_staff_say_it_isnt_against_them(
    scene: Scene,
) -> None:
    troupe = scene.troupe
    visit = scene.action("Call on Corvin", aimed_at=[scene.corvin])
    # Four general actions, with Computer's (#506): the one aimed at Corvin costs two.
    three = [visit, scene.action("Feed", 2), scene.action("Read", 3)]
    assert save(troupe.player, scene.agnes, three).status_code == 200
    over = save(troupe.player, scene.agnes, [*three, scene.action("Hunt", 4)])
    assert over.status_code == 422
    assert over.json()["detail"] == (
        "That is more general actions than the 4 this character has, and 1 that costs 2 actions."
    )
    scene.submit(troupe.player, scene.agnes, [visit, scene.action("Feed", 2)])
    visit_id = scene.response_id("Call on Corvin")
    assert scene.aimed().json()[0]["actions"][0]["located"] is True

    # A friendly visit: staff say it isn't against Corvin, and it costs one.
    waived = troupe.assistant.client.put(
        f"/responses/{visit_id}/not-against", json={"not_against": True}
    )
    assert waived.status_code == 200, waived.text
    assert waived.json()["aim"] == {
        "targets": ["Corvin"],
        "counter": None,
        "located": True,
        "not_against": True,
        "paired": None,
    }
    assert (
        troupe.narrator.client.put(
            f"/responses/{visit_id}/not-against", json={"not_against": False}
        ).status_code
        == 403
    )
    three = save(
        troupe.player, scene.agnes, [visit, scene.action("Feed", 2), scene.action("Hunt", 3)]
    )
    assert three.status_code == 200, three.text
    assert three.json()["answers"][0]["not_against"] is True

    # Aimed anew, it is judged anew.
    at_both = scene.action("Call on Corvin", aimed_at=[scene.corvin, scene.basil])
    again = save(troupe.player, scene.agnes, [at_both, scene.action("Feed", 2)])
    assert again.status_code == 200, again.text
    assert again.json()["answers"][0]["not_against"] is False
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "Agnes's action “Downtime action” is aimed at Corvin, Basil." in log


def test_computer_cancels_or_observes_one_action_paired_by_staff(scene: Scene) -> None:
    troupe = scene.troupe
    watch = scene.action("Watch Basil's email", aimed_at=[scene.basil], counter="observe")
    for bad in (
        # Basil has no Computer skill.
        (
            scene.basil_player,
            scene.basil,
            [scene.action("x", aimed_at=[scene.agnes], counter="cancel")],
        ),
        # A Cancel or Observe is aimed at one character, once a cycle.
        (
            troupe.player,
            scene.agnes,
            [scene.action("x", aimed_at=[scene.basil, scene.corvin], counter="cancel")],
        ),
        (
            troupe.player,
            scene.agnes,
            [watch, scene.action("y", 2, aimed_at=[scene.basil], counter="cancel")],
        ),
        (troupe.player, scene.agnes, [scene.action("x", aimed_at=[scene.basil], counter="steal")]),
    ):
        player, character, answers = bad
        refused = save(player, character, answers)
        assert refused.status_code == 422, refused.text

    scene.submit(troupe.player, scene.agnes, [watch, scene.action("Feed", 2)])
    scene.submit(
        scene.basil_player,
        scene.basil,
        [scene.action("Buy the newspaper"), scene.action("Visit the Prince", 2)],
    )
    scene.submit(scene.corvin_player, scene.corvin, [scene.action("Read")])
    group = scene.aimed().json()[0]
    assert group["character_name"] == "Basil"
    assert [o["answer"] for o in group["own"]] == ["Buy the newspaper", "Visit the Prince"]
    watch_id = group["actions"][0]["response_id"]
    prince_id = scene.response_id("Visit the Prince")

    # Only with an action of the one it is aimed at, and only a Cancel or Observe.
    for wrong, code in (
        ((watch_id, scene.response_id("Read")), 422),
        ((scene.response_id("Feed"), prince_id), 409),
    ):
        pairing = troupe.storyteller.client.put(
            f"/responses/{wrong[0]}/pairing", json={"response_id": wrong[1]}
        )
        assert pairing.status_code == code, pairing.text
    paired = troupe.storyteller.client.put(
        f"/responses/{watch_id}/pairing", json={"response_id": prince_id}
    )
    assert paired.status_code == 200, paired.text
    assert paired.json()["aim"]["paired"]["answer"] == "Visit the Prince"

    # Staff see the pair together, from either side.
    assert scene.aimed().json()[0]["actions"][0]["paired"]["character_name"] == "Basil"
    prince = troupe.storyteller.client.get(f"/responses/{prince_id}").json()
    assert [(p["character_name"], p["counter"]) for p in prince["countered_by"]] == [
        ("Agnes", "observe")
    ]
    unpaired = troupe.storyteller.client.put(
        f"/responses/{watch_id}/pairing", json={"response_id": None}
    )
    assert unpaired.json()["aim"]["paired"] is None
