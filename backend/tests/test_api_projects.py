"""Projects that span several downtime cycles (#507), such as a Path change (MET: VTM
p. 306): who starts them, actions counting toward them, the monthly rule and
finishing."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import member_character, my_downtime, new_cycle, open_cycle, save
from tests.test_api_quests import quests_on


class Scene:
    """Agnes, at home in the troupe, and Basil, another player's."""

    def __init__(self, client_for: Callable[[], TestClient], troupe: Troupe) -> None:
        self.troupe = troupe
        self.basil_player = sign_up(client_for, "basil_player")
        self.agnes = member_character(troupe, troupe.player, "Agnes")
        self.basil = member_character(troupe, self.basil_player, "Basil")

    def start(self, person: Person, character_id: str | None = None, **body: Any) -> Any:
        return person.client.post(f"/characters/{character_id or self.agnes}/projects", json=body)

    def started(self, **body: Any) -> dict[str, Any]:
        made = self.start(self.troupe.storyteller, **body)
        assert made.status_code == 201, made.text
        return made.json()

    def projects(self, person: Person | None = None) -> list[dict[str, Any]]:
        found = (person or self.troupe.player).client.get(f"/characters/{self.agnes}/projects")
        assert found.status_code == 200, found.text
        return found.json()["projects"]

    def open(self) -> dict[str, Any]:
        return open_cycle(self.troupe, new_cycle(self.troupe))

    def spend(self, project_ids: list[str | None]) -> None:
        """Agnes's downtime: one general action for each of `project_ids`, toward it,
        or toward none."""
        question = next(
            q["id"]
            for q in my_downtime(self.troupe.player, self.agnes).json()["questions"]
            if q["prompt"] == "Downtime action"
        )
        answers = [
            {
                "question_id": question,
                "slot": slot,
                "body": f"Study, night {slot}",
                "structured": {"project_id": p} if p else {},
            }
            for slot, p in enumerate(project_ids, 1)
        ]
        saved = save(self.troupe.player, self.agnes, answers)
        assert saved.status_code == 200, saved.text
        submitted = self.troupe.player.client.post(f"/characters/{self.agnes}/downtime/submit")
        assert submitted.status_code == 200, submitted.text

    def complete(self, cycle: dict[str, Any]) -> None:
        client = self.troupe.storyteller.client
        assert client.post(f"/cycles/{cycle['id']}/close").status_code == 200
        completed = client.post(f"/cycles/{cycle['id']}/complete")
        assert completed.status_code == 200, completed.text


@pytest.fixture
def scene(client_for: Callable[[], TestClient], session: Session) -> Scene:
    return Scene(client_for, Troupe(client_for, session))


def test_staff_start_projects_and_confirm_those_players_propose(scene: Scene) -> None:
    troupe = scene.troupe
    research = scene.started(kind="research", name="The Book of Nod", target=4)
    assert (research["status"], research["target"], research["monthly_minimum"]) == (
        "active",
        4,
        None,
    )

    proposed = scene.start(troupe.player, kind="path_change", path="Night")
    assert proposed.status_code == 201, proposed.text
    path = proposed.json()
    # The book's numbers: 18 actions without a teacher, at least 1 a month.
    assert (path["status"], path["name"], path["target"], path["monthly_minimum"]) == (
        "proposed",
        "Path change: Night",
        18,
        1,
    )
    with_teacher = scene.start(troupe.player, kind="path_change", path="Night", with_teacher=True)
    assert with_teacher.json()["target"] == 9
    bell = troupe.storyteller.client.get("/notifications").json()["items"]
    assert any("proposes a project: Path change: Night" in n["summary"] for n in bell)

    assert troupe.player.client.post(f"/projects/{path['id']}/confirm").status_code == 403
    confirmed = troupe.assistant.client.post(f"/projects/{path['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "active"
    # Its player withdraws a proposal; only staff stop one under way.
    assert troupe.player.client.post(f"/projects/{path['id']}/drop").status_code == 409
    withdrawn = troupe.player.client.post(f"/projects/{with_teacher.json()['id']}/drop")
    assert withdrawn.json()["status"] == "dropped"

    listed = scene.projects()
    assert [(p["name"], p["status"]) for p in listed][:2] == [
        ("Path change: Night", "active"),
        ("The Book of Nod", "active"),
    ]
    assert (
        "Night"
        in scene.basil_player.client.get(f"/characters/{scene.basil}/projects").json()["paths"]
    )
    # Not another player's, nor a narrator's to see.
    for outsider in (scene.basil_player, troupe.narrator, troupe.stranger):
        assert outsider.client.get(f"/characters/{scene.agnes}/projects").status_code in (
            403,
            404,
        )
        assert scene.start(outsider, kind="other", name="Meddle", target=1).status_code in (
            403,
            404,
        )
    for bad in (
        {"kind": "path_change"},
        {"kind": "research", "name": "", "target": 3},
        {"kind": "other", "name": "Plan", "target": 2, "monthly_minimum": 3},
    ):
        assert scene.start(troupe.storyteller, **bad).status_code == 422


def test_actions_count_toward_a_project_across_cycles_until_it_finishes(scene: Scene) -> None:
    troupe = scene.troupe
    path = scene.started(kind="path_change", path="Night", with_teacher=True)
    research = scene.started(kind="research", name="The Book of Nod", target=2)
    proposed = scene.start(troupe.player, kind="other", name="A gallery", target=3).json()

    first = scene.open()
    # Only toward the character's own projects under way.
    question = my_downtime(troupe.player, scene.agnes).json()["questions"][0]["id"]
    for project_id in (proposed["id"], "not-an-id"):
        refused = save(
            troupe.player,
            scene.agnes,
            [{"question_id": question, "body": "x", "structured": {"project_id": project_id}}],
        )
        assert refused.status_code == 422, refused.text
    scene.spend([path["id"], path["id"], research["id"]])
    standing = troupe.storyteller.client.get(f"/cycles/{first['id']}/projects").json()
    assert [(p["name"], p["this_cycle"], p["starts_over"]) for p in standing] == [
        ("A gallery", None, False),
        ("The Book of Nod", 1, False),
        ("Path change: Night", 2, False),
    ]
    scene.complete(first)
    by_name = {p["name"]: p for p in scene.projects()}
    assert by_name["Path change: Night"]["progress"] == 2
    assert by_name["Path change: Night"]["history"] == [
        {"cycle_name": "October 2026", "spent": 2, "started_over": False, "progress": 2}
    ]

    second = scene.open()
    scene.spend([path["id"], path["id"], research["id"]])
    scene.complete(second)
    by_name = {p["name"]: p for p in scene.projects()}
    assert (by_name["The Book of Nod"]["progress"], by_name["The Book of Nod"]["status"]) == (
        2,
        "finished",
    )
    assert by_name["Path change: Night"]["progress"] == 4

    # Nine with a teacher: the fifth cycle finishes it, and staff are asked to put it
    # on the sheet.
    for _ in range(2):
        cycle = scene.open()
        scene.spend([path["id"], path["id"]])
        scene.complete(cycle)
    last = scene.open()
    scene.spend([path["id"]])
    scene.complete(last)
    done = next(p for p in scene.projects() if p["id"] == path["id"])
    assert (done["progress"], done["status"], done["sheet_change_due"]) == (9, "finished", True)
    bell = troupe.storyteller.client.get("/notifications").json()["items"]
    assert any(
        n["summary"]
        == "Agnes has finished changing Path to Night: change their Morality on the sheet."
        for n in bell
    )
    assert troupe.player.client.post(f"/projects/{path['id']}/sheet-changed").status_code == 403
    changed = troupe.storyteller.client.post(f"/projects/{path['id']}/sheet-changed")
    assert changed.json()["sheet_change_due"] is False


def test_a_month_without_an_action_starts_a_path_change_over(scene: Scene) -> None:
    troupe = scene.troupe
    path = scene.started(kind="path_change", path="Night")
    first = scene.open()
    scene.spend([path["id"], path["id"]])
    scene.complete(first)

    second = scene.open()
    scene.spend([None])
    # Staff are warned before it happens.
    standing = troupe.storyteller.client.get(f"/cycles/{second['id']}/projects").json()
    assert [(p["this_cycle"], p["starts_over"]) for p in standing] == [(0, True)]
    scene.complete(second)
    over = scene.projects()[0]
    assert (over["progress"], over["restarts"], over["status"]) == (0, 1, "active")
    assert [(h["spent"], h["started_over"]) for h in over["history"]] == [(2, False), (0, True)]
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert (
        "Agnes (player)'s project Path change: Night started over: too few actions on it in"
        " October 2026." in log
    )

    # Not taking part in a cycle neither spends on it nor loses it.
    third = scene.open()
    participants = troupe.storyteller.client.get(f"/cycles/{third['id']}/participants").json()
    agnes = next(p for p in participants if p["character_id"] == scene.agnes)
    removed = troupe.storyteller.client.delete(f"/cycles/{third['id']}/participants/{agnes['id']}")
    assert removed.status_code in (200, 204), removed.text
    scene.complete(third)
    assert scene.projects()[0]["history"][-1]["cycle_name"] == "October 2026"
    assert len(scene.projects()[0]["history"]) == 2


def test_staff_make_a_proposed_project_a_quest_request_while_the_troupe_runs_quests(
    scene: Scene,
) -> None:
    troupe = scene.troupe
    found = troupe.player.client.get(f"/characters/{scene.agnes}/projects").json()
    assert (found["quests"], found["troupe_id"]) == (False, str(troupe.id))
    research = scene.start(troupe.player, kind="research", name="Locate Karsh", target=6).json()
    # Not while quests are off.
    refused = troupe.storyteller.client.post(f"/projects/{research['id']}/quest-request")
    assert refused.status_code == 409
    assert "does not run quests" in refused.json()["detail"]

    quests_on(troupe)
    assert troupe.player.client.get(f"/characters/{scene.agnes}/projects").json()["quests"]
    # Only staff, and only a proposed Research or Other project.
    assert troupe.player.client.post(f"/projects/{research['id']}/quest-request").status_code == 403
    path = scene.start(troupe.player, kind="path_change", path="Night").json()
    stays = troupe.storyteller.client.post(f"/projects/{path['id']}/quest-request")
    assert stays.status_code == 409
    assert stays.json()["detail"] == "A Path change stays a project."
    under_way = scene.started(kind="other", name="A gallery", target=3)
    assert (
        troupe.storyteller.client.post(f"/projects/{under_way['id']}/quest-request").status_code
        == 409
    )

    made = troupe.assistant.client.post(f"/projects/{research['id']}/quest-request")
    assert made.status_code == 200, made.text
    assert made.json()["status"] == "dropped"
    mine = troupe.player.client.get(f"/characters/{scene.agnes}/quests").json()
    assert [(r["objective"], r["status"]) for r in mine["requests"]] == [
        ("Locate Karsh", "waiting")
    ]
    # It is the player's request, counted toward their limit.
    assert mine["used"] == 1
    queued = troupe.storyteller.client.get(f"/troupes/{troupe.id}/quest-requests").json()
    assert [(r["objective"], r["player_name"]) for r in queued] == [("Locate Karsh", "player")]
    bell = troupe.player.client.get("/notifications").json()["items"]
    assert any(n["summary"] == "Agnes's project Locate Karsh is now a quest request." for n in bell)
    log = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert any("proposed project Locate Karsh a quest request." in m for m in log)

    # Past the troupe's limit, it is refused and the project stays proposed.
    other = scene.start(troupe.player, kind="other", name="Find the Prince's haven", target=2)
    again = troupe.storyteller.client.post(f"/projects/{other.json()['id']}/quest-request")
    assert again.status_code == 409
    assert "has made 1 of 1 quest request" in again.json()["detail"]
    still = next(p for p in scene.projects() if p["name"] == "Find the Prince's haven")
    assert still["status"] == "proposed"
