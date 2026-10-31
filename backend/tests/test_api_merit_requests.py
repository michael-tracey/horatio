"""Merits and flaws changed once a home troupe has accepted the character wait on its
staff, who may answer with a quest (horatio.merit_requests, issue #342; MET: VTM
p. 236; Vol. II Issue 1, pp. 104-105)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_downtimes import my_downtime, new_cycle, open_cycle
from tests.test_api_owed_actions import member_with
from tests.test_api_quests import give, ok, quests_on

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def spend(person: Person, character_id: str, *changes: dict[str, Any], dry_run: bool = False):  # noqa: ANN201
    return person.client.post(
        f"/characters/{character_id}/cart", json={"changes": list(changes), "dry_run": dry_run}
    )


def rating(category: str, name: str, to: int, **extra: Any) -> dict[str, Any]:
    return {"kind": "set", "category": category, "name": name, "rating": to, **extra}


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    return ok(person.client.get(f"/characters/{character_id}/sheet"))


def held(person: Person, character_id: str) -> dict[str, int | None]:
    return {t["name"]: t["rating"] for t in sheet(person, character_id)["traits"]}


def balance(person: Person, character_id: str) -> int:
    return sheet(person, character_id)["xp"]["balance"]


def queue(person: Person, troupe: Troupe, state: str = "pending") -> list[dict[str, Any]]:
    return ok(
        person.client.get(
            f"/troupes/{troupe.id}/approvals", params={"state": state, "kind": "merit_flaw"}
        )
    )


def tasks(person: Person) -> list[str]:
    found = ok(person.client.get("/notifications"))
    items = found["items"] if isinstance(found, dict) else found
    return [i["summary"] for i in items if i["task"] and i["kind"] == "approval.merit_flaw"]


def accepted(troupe: Troupe, *traits: tuple[str, str, int]) -> str:
    """Agnes, holding `traits` from creation, accepted home."""
    return member_with(troupe, "Agnes", "Toreador", *traits)


def line(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    [found] = response.json()["lines"]
    return found


def test_a_merit_added_after_acceptance_waits_with_its_xp_held(troupe: Troupe) -> None:
    agnes = accepted(troupe)
    start = balance(troupe.player, agnes)
    injured = held(troupe.player, agnes)["Injured"]

    asked = line(spend(troupe.player, agnes, rating("merits", "Rugged", 3)))

    assert (asked["cost"], asked["refused"], asked["needs_approval"]) == (3, None, True)
    assert asked["because"] == "Asked of the home troupe: 3 XP held until they decide."
    found = sheet(troupe.player, agnes)
    assert "Rugged" not in {t["name"] for t in found["traits"]}
    assert found["xp"]["balance"] == start - 3
    [waiting] = found["pending_disciplines"]
    assert (waiting["kind"], waiting["category"], waiting["name"]) == (
        "merit_flaw",
        "merits",
        "Rugged",
    )
    assert (waiting["from_rating"], waiting["to_rating"], waiting["cost"]) == (0, 3, 3)
    # Storytellers and assistant storytellers see it in the queue and their bell.
    for person in (troupe.storyteller, troupe.assistant):
        [request] = queue(person, troupe)
        assert request["discipline"]["category"] == "merits"
        assert tasks(person) == ["Agnes asks to add Rugged (3 XP)"]
    assert tasks(troupe.player) == []

    ok(troupe.assistant.client.post(f"/approvals/{request['id']}/approve", json={}))

    # On the sheet, with its effects: a health level more in each wound rank.
    now = held(troupe.player, agnes)
    assert now["Rugged"] == 3
    assert now["Injured"] == (injured or 0) + 1
    assert balance(troupe.player, agnes) == start - 3
    assert sheet(troupe.player, agnes)["pending_disciplines"] == []
    assert tasks(troupe.storyteller) == []


def test_an_approved_merit_takes_a_downtime_action(troupe: Troupe) -> None:
    agnes = accepted(troupe)
    spend(troupe.player, agnes, rating("merits", "Acute Sense", 1, detail="Hearing"))
    open_cycle(troupe, new_cycle(troupe))
    assert "Gaining Acute Sense" not in str(my_downtime(troupe.player, agnes).json())

    [request] = queue(troupe.storyteller, troupe)
    ok(troupe.storyteller.client.post(f"/approvals/{request['id']}/approve", json={}))

    downtime = my_downtime(troupe.player, agnes).json()
    assert downtime["allowance"]["general"] == 2
    assert "Gaining Acute Sense" in [a["reason"] for a in downtime["adjustments"]]


def test_declining_refunds_the_xp_and_leaves_the_sheet_as_it_was(troupe: Troupe) -> None:
    agnes = accepted(troupe)
    start = balance(troupe.player, agnes)
    before = held(troupe.player, agnes)
    spend(troupe.player, agnes, rating("merits", "Rugged", 3))
    [request] = queue(troupe.storyteller, troupe)

    ok(
        troupe.storyteller.client.post(
            f"/approvals/{request['id']}/decline", json={"note": "Not this season."}
        )
    )

    assert held(troupe.player, agnes) == before
    assert balance(troupe.player, agnes) == start
    [declined] = queue(troupe.storyteller, troupe, "declined")
    assert declined["staff_note"] == "Not this season."


def test_withdrawing_gives_the_xp_back(troupe: Troupe) -> None:
    agnes = accepted(troupe)
    start = balance(troupe.player, agnes)
    spend(troupe.player, agnes, rating("merits", "Rugged", 3))
    [waiting] = sheet(troupe.player, agnes)["pending_disciplines"]

    response = troupe.player.client.delete(
        f"/characters/{agnes}/disciplines/{waiting['approval_id']}"
    )

    assert response.status_code == 204, response.text
    assert balance(troupe.player, agnes) == start
    assert "Rugged" not in held(troupe.player, agnes)
    assert queue(troupe.storyteller, troupe) == []


def test_a_flaw_bought_off_through_a_complex_quest(troupe: Troupe) -> None:
    agnes = accepted(troupe, ("flaws", "Low Pain Threshold", 3))
    quests_on(troupe)
    start = balance(troupe.player, agnes)
    injured = held(troupe.player, agnes)["Injured"]

    asked = line(spend(troupe.player, agnes, rating("flaws", "Low Pain Threshold", 0)))

    # Twice its 3 points, held (p. 236).
    assert (asked["cost"], asked["needs_approval"]) == (6, True)
    assert "buying it off costs 6 XP, twice what it gave" in asked["because"]
    assert balance(troupe.player, agnes) == start - 6
    assert held(troupe.player, agnes)["Low Pain Threshold"] == 3
    [request] = queue(troupe.storyteller, troupe)
    # The builder suggests a Complex quest at the flaw's points (Vol. II Issue 1, p. 104).
    assert request["quest_suggestion"] == {
        "name": "Buy off Low Pain Threshold",
        "objective": "Agnes buys off Low Pain Threshold.",
        "category": "complex",
        "difficulty": 3,
    }

    quest = ok(
        troupe.storyteller.client.post(
            f"/troupes/{troupe.id}/quests",
            json={
                "name": "Buy off Low Pain Threshold",
                "category": "complex",
                "difficulty": 3,
                "approval_id": request["id"],
            },
        ),
        201,
    )
    assert quest["leader"]["name"] == "Agnes"
    assert [s["number"] for s in quest["scenarios"]] == [1, 2, 3]
    assert quest["answers"] == [
        {
            "approval_id": request["id"],
            "change": "Agnes buys off Low Pain Threshold",
            "status": "pending",
            "cost": 6,
        }
    ]
    # Tied to the quest: no longer a task, nor decided or withdrawn directly.
    [request] = queue(troupe.storyteller, troupe)
    assert request["quest"] == {"id": quest["id"], "name": quest["name"], "status": "draft"}
    assert request["quest_suggestion"] is None
    assert tasks(troupe.storyteller) == []
    refused = troupe.storyteller.client.post(f"/approvals/{request['id']}/approve", json={})
    assert refused.status_code == 409
    assert "waits on the quest Buy off Low Pain Threshold" in refused.json()["detail"]
    withdrawn = troupe.player.client.delete(f"/characters/{agnes}/disciplines/{request['id']}")
    assert withdrawn.status_code == 409

    qid = quest["id"]
    ok(
        troupe.storyteller.client.post(
            f"/quests/{qid}/requirements",
            json={"options": [{"kind": "text", "text": "A sire's blessing"}]},
        ),
        201,
    )
    ok(troupe.storyteller.client.post(f"/quests/{qid}/send"))
    [waiting] = sheet(troupe.player, agnes)["pending_disciplines"]
    assert waiting["quest"] == "Buy off Low Pain Threshold"
    for number in (1, 2, 3):
        ok(
            troupe.storyteller.client.post(
                f"/quests/{qid}/scenarios/{number}/result", json={"result": "passed"}
            )
        )

    # Completed: the flaw is gone, its effects with it, and the 6 XP spent.
    now = held(troupe.player, agnes)
    assert "Low Pain Threshold" not in now
    assert now["Injured"] == (injured or 0) + 1
    assert balance(troupe.player, agnes) == start - 6
    [approved] = queue(troupe.storyteller, troupe, "approved")
    assert approved["id"] == request["id"]
    done = ok(troupe.storyteller.client.get(f"/quests/{qid}"))
    assert done["answers"][0]["status"] == "approved"


def test_a_5_point_flaw_is_an_epic_quest(troupe: Troupe) -> None:
    agnes = accepted(troupe, ("flaws", "Dark Fate", 5))
    quests_on(troupe)
    spend(troupe.player, agnes, rating("flaws", "Dark Fate", 0))

    [request] = queue(troupe.storyteller, troupe)

    suggested = request["quest_suggestion"]
    assert (suggested["category"], suggested["difficulty"]) == ("epic", 2)


def test_a_failed_or_closed_quest_declines_and_refunds(troupe: Troupe) -> None:
    agnes = accepted(troupe, ("flaws", "Low Pain Threshold", 3))
    quests_on(troupe)
    start = balance(troupe.player, agnes)
    spend(troupe.player, agnes, rating("flaws", "Low Pain Threshold", 0))
    [request] = queue(troupe.storyteller, troupe)

    def answer() -> str:
        return ok(
            troupe.storyteller.client.post(
                f"/troupes/{troupe.id}/quests",
                json={"name": "Atone", "category": "simple", "approval_id": request["id"]},
            ),
            201,
        )["id"]

    qid = answer()
    ok(
        troupe.storyteller.client.post(
            f"/quests/{qid}/requirements", json={"options": [{"kind": "text", "text": "Penance"}]}
        ),
        201,
    )
    ok(troupe.storyteller.client.post(f"/quests/{qid}/send"))
    ok(
        troupe.storyteller.client.post(
            f"/quests/{qid}/scenarios/1/result", json={"result": "failed", "ends": True}
        )
    )

    assert held(troupe.player, agnes)["Low Pain Threshold"] == 3
    assert balance(troupe.player, agnes) == start
    [declined] = queue(troupe.storyteller, troupe, "declined")
    assert declined["staff_note"] == "The quest Atone was failed."

    # Asked again, and the quest closed before it is sent.
    spend(troupe.player, agnes, rating("flaws", "Low Pain Threshold", 0))
    [request] = queue(troupe.storyteller, troupe)
    qid = answer()
    ok(troupe.storyteller.client.post(f"/quests/{qid}/close", json={"note": "Not now"}))

    assert balance(troupe.player, agnes) == start
    assert queue(troupe.storyteller, troupe) == []


def test_removing_a_merit_says_there_is_no_refund(troupe: Troupe) -> None:
    agnes = accepted(troupe, ("merits", "Rugged", 3))
    start = balance(troupe.player, agnes)

    priced = line(spend(troupe.player, agnes, rating("merits", "Rugged", 0), dry_run=True))
    assert priced["cost"] == 0
    assert priced["because"] == (
        "Asked of the home troupe: removing a merit gives no XP back (MET: VTM p. 236)."
    )
    line(spend(troupe.player, agnes, rating("merits", "Rugged", 0)))
    assert held(troupe.player, agnes)["Rugged"] == 3
    [request] = queue(troupe.storyteller, troupe)
    assert tasks(troupe.storyteller) == ["Agnes asks to remove Rugged (no XP back)"]

    ok(troupe.storyteller.client.post(f"/approvals/{request['id']}/approve", json={}))

    assert "Rugged" not in held(troupe.player, agnes)
    assert balance(troupe.player, agnes) == start


def test_a_flaw_taken_on_gives_its_xp_once_approved(troupe: Troupe) -> None:
    agnes = accepted(troupe)
    start = balance(troupe.player, agnes)

    asked = line(spend(troupe.player, agnes, rating("flaws", "Archaic", 2)))

    assert asked["because"] == "Asked of the home troupe: it gives 2 XP once they approve."
    assert balance(troupe.player, agnes) == start
    [request] = queue(troupe.storyteller, troupe)
    ok(troupe.storyteller.client.post(f"/approvals/{request['id']}/approve", json={}))

    assert held(troupe.player, agnes)["Archaic"] == 2
    assert balance(troupe.player, agnes) == start + 2


def test_integral_merits_and_flaws_cannot_be_asked_away(troupe: Troupe, session: Session) -> None:
    agnes = accepted(troupe)
    give(session, agnes, "merits", "Inceptor", 2)

    refused = line(spend(troupe.player, agnes, rating("merits", "Inceptor", 0), dry_run=True))

    assert refused["refused"] == (
        "Inceptor is part of the character's history (its Embrace, clan or bloodline), "
        "so it can't be removed (MET: VTM p. 236)."
    )
    # Nor taken on after creation.
    adding = line(
        spend(troupe.player, agnes, rating("merits", "Shadows of the Past", 1), dry_run=True)
    )
    assert adding["refused"] == "Shadows of the Past can only be chosen during character creation."


def test_the_merit_limit_is_judged_when_asked_and_again_when_approved(troupe: Troupe) -> None:
    agnes = accepted(troupe, ("merits", "Rugged", 3))
    spend(troupe.player, agnes, rating("merits", "Unyielding", 4))
    # Waiting requests are not on the sheet, so each is judged without the others.
    spend(troupe.player, agnes, rating("merits", "Efficient Learner", 2))
    twice = line(spend(troupe.player, agnes, rating("merits", "Unyielding", 4), dry_run=True))
    assert "Unyielding is waiting for the home troupe's approval" in (twice["refused"] or "")
    unyielding, learner = queue(troupe.storyteller, troupe)
    ok(troupe.storyteller.client.post(f"/approvals/{unyielding['id']}/approve", json={}))

    refused = troupe.storyteller.client.post(f"/approvals/{learner['id']}/approve", json={})

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "That would bring merits to 9 points; a character can hold at most 7."
    )
    over = line(spend(troupe.player, agnes, rating("merits", "Calm Heart", 1), dry_run=True))
    assert over["refused"] == (
        "That would bring merits to 8 points; a character can hold at most 7."
    )


def test_before_acceptance_merits_change_freely(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player, clan="Toreador")

    asked = line(spend(troupe.player, agnes, rating("merits", "Rugged", 3)))

    assert (asked["cost"], asked["needs_approval"], asked["because"]) == (3, False, None)
    assert held(troupe.player, agnes)["Rugged"] == 3
    assert queue(troupe.storyteller, troupe) == []
