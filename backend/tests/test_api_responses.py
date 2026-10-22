"""Answering downtimes: assignment, narrators, writing, fill tables and delivery."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe, sign_up
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
    """A troupe with an open cycle and one submitted downtime: two general actions,
    one elite influence action, and a nomination."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.agnes = member_character(troupe, troupe.player, "Agnes", elite=1)
        cycle = new_cycle(troupe)
        cycle = set_questions(
            troupe, cycle, cycle["questions"] + [{"kind": "custom", "prompt": "Nominations?"}]
        )
        self.cycle = open_cycle(troupe, cycle)
        form = my_downtime(troupe.player, self.agnes).json()
        self.general = question_id(form, "Downtime action")
        self.elite = question_id(form, "Elite influence action")
        self.nominations = question_id(form, "Nominations?")
        self.answers = [
            {"question_id": self.general, "slot": 1, "body": "Feed at the docks"},
            {"question_id": self.general, "slot": 2, "body": "Patrol the park"},
            {
                "question_id": self.elite,
                "slot": 1,
                "body": "Lean on the mayor",
                "structured": {"action": "a_friend_in_need"},
            },
            {"question_id": self.nominations, "slot": 1, "body": "Vera, for courtesy"},
        ]
        assert save(troupe.player, self.agnes, self.answers).status_code == 200
        assert (
            troupe.player.client.post(f"/characters/{self.agnes}/downtime/submit").status_code
            == 200
        )

    def responses(self) -> list[dict[str, Any]]:
        response = self.troupe.assistant.client.get(f"/cycles/{self.cycle['id']}/responses")
        assert response.status_code == 200, response.text
        return response.json()

    def response_for(self, answer: str) -> dict[str, Any]:
        return next(r for r in self.responses() if r["answer"] == answer)

    def assign(self, answer: str, **assignment: Any) -> Any:
        return self.troupe.assistant.client.put(
            f"/responses/{self.response_for(answer)['id']}/assignment", json=assignment
        )


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(Troupe(client_for, session))


def test_submitting_gives_every_answer_a_response(scene: Scene) -> None:
    items = scene.responses()

    assert [(i["question"], i["answer"], i["status"]) for i in items] == [
        ("Downtime action", "Feed at the docks", "unassigned"),
        ("Downtime action", "Patrol the park", "unassigned"),
        ("Elite influence action", "Lean on the mayor", "unassigned"),
        ("Nominations?", "Vera, for courtesy", "unassigned"),
    ]
    assert items[2]["structured"] == {"action": "a_friend_in_need"}
    assert items[2]["influence"]["action"] == "1: A Friend in Need"


def test_narrators_see_only_their_work_and_never_the_sheet(scene: Scene) -> None:
    troupe = scene.troupe
    narrator_id = troupe.narrator.id
    scene.assign("Feed at the docks", user_id=narrator_id)
    scene.assign("Patrol the park", any_narrator=True)

    assert troupe.narrator.client.get(f"/cycles/{scene.cycle['id']}/responses").status_code == 403
    mine = troupe.narrator.client.get(f"/cycles/{scene.cycle['id']}/responses/mine").json()

    assert [m["answer"] for m in mine] == ["Feed at the docks", "Patrol the park"]
    assert set(mine[0]) == {
        "id",
        "cycle_id",
        "character_id",
        "character_name",
        "question",
        "action_kind",
        "answer",
        "structured",
        "influence",
        "influence_entry",
        "influence_blocks",
        "status",
        "assigned_to_user_id",
        "assigned_to_any_narrator",
        "body",
    }
    assert troupe.narrator.client.get(f"/characters/{scene.agnes}/sheet").status_code == 404


def test_narrators_write_what_is_assigned_to_them(scene: Scene) -> None:
    troupe = scene.troupe
    scene.assign("Feed at the docks", user_id=troupe.narrator.id)
    assigned = scene.response_for("Feed at the docks")["id"]
    unassigned = scene.response_for("Patrol the park")["id"]

    written = troupe.narrator.client.put(f"/responses/{assigned}", json={"body": "You feed well."})
    assert written.json()["status"] == "written"
    assert (
        troupe.narrator.client.put(f"/responses/{unassigned}", json={"body": "x"}).status_code
        == 403
    )
    # Storytellers and assistants write any response.
    assert (
        troupe.assistant.client.put(
            f"/responses/{unassigned}", json={"body": "Quiet night."}
        ).status_code
        == 200
    )


def test_narrators_accept_from_the_any_narrator_pool(scene: Scene) -> None:
    troupe = scene.troupe
    scene.assign("Patrol the park", any_narrator=True)
    pooled = scene.response_for("Patrol the park")["id"]

    accepted = troupe.narrator.client.post(f"/responses/{pooled}/accept")

    assert accepted.json()["assigned_to_user_id"] == troupe.narrator.id
    assert accepted.json()["assigned_to_any_narrator"] is False
    assert (
        troupe.narrator.client.put(f"/responses/{pooled}", json={"body": "All quiet."}).status_code
        == 200
    )


def test_declining_sends_it_back_to_be_reassigned(scene: Scene) -> None:
    troupe = scene.troupe
    scene.assign("Feed at the docks", user_id=troupe.narrator.id)
    assigned = scene.response_for("Feed at the docks")["id"]

    declined = troupe.narrator.client.post(f"/responses/{assigned}/decline")

    assert declined.json()["status"] == "unassigned"
    assert declined.json()["assigned_to_user_id"] is None
    assert troupe.narrator.client.get(f"/cycles/{scene.cycle['id']}/responses/mine").json() == []


def test_only_running_staff_assign_and_only_to_staff(scene: Scene) -> None:
    troupe = scene.troupe
    target = scene.response_for("Feed at the docks")["id"]

    assert (
        troupe.narrator.client.put(
            f"/responses/{target}/assignment", json={"user_id": troupe.narrator.id}
        ).status_code
        == 403
    )
    assert scene.assign("Feed at the docks", user_id=troupe.player.id).status_code == 422
    assert scene.assign("Feed at the docks", user_id=troupe.lead.id).status_code == 200


def test_answers_with_written_responses_are_locked(scene: Scene) -> None:
    troupe = scene.troupe
    feed = scene.response_for("Feed at the docks")["id"]
    troupe.assistant.client.put(f"/responses/{feed}", json={"body": "You feed well."})

    changed = [dict(a) for a in scene.answers]
    changed[0]["body"] = "Feed somewhere else"
    assert save(troupe.player, scene.agnes, changed).status_code == 409

    # Other answers can still change; a new one gets a response.
    changed = [dict(a) for a in scene.answers]
    changed[1]["body"] = "Patrol the river"
    changed.append({"question_id": scene.general, "slot": 3, "body": "Visit the library"})
    assert save(troupe.player, scene.agnes, changed).status_code == 200
    assert [r["answer"] for r in scene.responses()][:3] == [
        "Feed at the docks",
        "Patrol the river",
        "Visit the library",
    ]


def test_progress(scene: Scene) -> None:
    troupe = scene.troupe
    scene.assign("Feed at the docks", user_id=troupe.narrator.id)
    scene.assign("Patrol the park", any_narrator=True)
    feed = scene.response_for("Feed at the docks")["id"]
    troupe.narrator.client.put(f"/responses/{feed}", json={"body": "Done."})

    progress = troupe.assistant.client.get(f"/cycles/{scene.cycle['id']}/progress").json()

    assert progress["participants"] == 1
    assert progress["submitted"] == 1
    assert (
        progress["responses"],
        progress["unassigned"],
        progress["assigned"],
        progress["written"],
    ) == (4, 2, 1, 1)
    assert progress["by_assignee"] == {
        "narrator": {"written": 1, "total": 1},
        "Any narrator": {"written": 0, "total": 1},
        "Unassigned": {"written": 0, "total": 2},
    }
    assert progress["by_action_kind"]["general"] == {"written": 1, "total": 2}


def test_delivering_results_to_the_player(scene: Scene) -> None:
    troupe = scene.troupe
    cycle_id = scene.cycle["id"]
    feed = scene.response_for("Feed at the docks")["id"]
    troupe.assistant.client.put(f"/responses/{feed}", json={"body": "You feed well."})

    assert troupe.assistant.client.post(f"/cycles/{cycle_id}/deliver").status_code == 409
    troupe.assistant.client.post(f"/cycles/{cycle_id}/close")
    assert troupe.narrator.client.post(f"/cycles/{cycle_id}/deliver").status_code == 403
    assert troupe.assistant.client.post(f"/cycles/{cycle_id}/deliver").json() == {
        "delivered": 1,
        "queued": 0,
    }

    results = troupe.player.client.get(f"/characters/{scene.agnes}/downtime/results").json()
    assert len(results) == 1
    assert results[0]["message"] == (
        "**Downtime results for Agnes (October 2026)**\n\n"
        "**Downtime action**\n*Your action:* Feed at the docks\n*Result:* You feed well."
    )
    # Never twice, and nothing changes after delivery.
    assert troupe.assistant.client.post(f"/cycles/{cycle_id}/deliver").json() == {
        "delivered": 0,
        "queued": 0,
    }
    assert (
        troupe.assistant.client.put(f"/responses/{feed}", json={"body": "Changed"}).status_code
        == 409
    )
    assert troupe.assistant.client.post(f"/cycles/{cycle_id}/complete").status_code == 200


def test_fill_tables(scene: Scene) -> None:
    troupe = scene.troupe
    base = f"/troupes/{troupe.id}/random-tables"
    assert (
        troupe.narrator.client.put(base, json={"name": "Feed", "entries": ["x"]}).status_code == 403
    )
    troupe.assistant.client.put(
        base, json={"name": "Feed", "entries": ["You hunt near [Location]."]}
    )
    troupe.assistant.client.put(base, json={"name": "Location", "entries": ["the docks"]})

    rolled = troupe.narrator.client.post(f"{base}/feed/roll")

    assert rolled.json() == {"text": "You hunt near the docks."}
    assert [t["name"] for t in troupe.narrator.client.get(base).json()] == ["Feed", "Location"]
    assert troupe.player.client.post(f"{base}/feed/roll").status_code == 403


def test_staff_from_other_troupes_see_nothing(scene: Scene) -> None:
    outsider = sign_up(scene.troupe.client_for, "outsider")
    target = scene.response_for("Feed at the docks")["id"]

    assert outsider.client.get(f"/cycles/{scene.cycle['id']}/responses/mine").status_code == 403
    assert outsider.client.get(f"/responses/{target}").status_code == 403


def test_narrators_find_the_cycles_they_work_on(scene: Scene) -> None:
    troupe = scene.troupe
    new_cycle(troupe)  # a draft, which nobody works on yet

    cycles = troupe.narrator.client.get(f"/troupes/{troupe.id}/work-cycles").json()

    assert [(c["name"], c["status"]) for c in cycles] == [("October 2026", "open")]
    assert troupe.player.client.get(f"/troupes/{troupe.id}/work-cycles").status_code == 403
