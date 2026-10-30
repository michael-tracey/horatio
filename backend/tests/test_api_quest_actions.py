"""Quests in downtime (horatio.quest_actions, issue #324): the Quest action joins and
progresses a quest; one result answers every member's action and goes out with the
cycle's delivery; Downtime Only quests take results only through a downtime."""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import delivery
from horatio.connectors import CONNECTORS
from horatio.models import Notification
from horatio.rules.model import ActionKindData, AllowanceRuleData
from horatio.rules.store import add_house_action_kind, add_house_allowance_rule
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_downtimes import member_character, new_cycle, open_cycle, set_questions
from tests.test_delivery_connectors import START, FakeConnector


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def fake() -> Iterator[FakeConnector]:
    connector = FakeConnector()
    real = CONNECTORS.get("discord")
    CONNECTORS["discord"] = connector
    yield connector
    if real is not None:
        CONNECTORS["discord"] = real


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def quests_on(troupe: Troupe) -> None:
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/quest-settings", json={"enabled": True, "requests_per_cycle": 1}
        )
    )


def sent_quest(troupe: Troupe, leader: str, **fields: Any) -> str:
    """A quest under way, led by `leader`, with one requirement and its scenarios'
    success text written ahead."""
    body = {"name": "The Lost Journal", "category": "complex", "difficulty": 2, **fields}
    quest = ok(
        troupe.storyteller.client.post(
            f"/troupes/{troupe.id}/quests",
            json={
                "leader_id": leader,
                "scenarios": [
                    {"success_text": "You find the cellar.", "fail_text": "The cellar floods."},
                    {"success_text": "The journal is yours.", "fail_text": "It burns."},
                ],
                **body,
            },
        ),
        201,
    )
    ok(
        troupe.storyteller.client.post(
            f"/quests/{quest['id']}/requirements",
            json={"options": [{"kind": "text", "text": "Access to Miles' journal"}]},
        ),
        201,
    )
    ok(troupe.storyteller.client.post(f"/quests/{quest['id']}/send"))
    return quest["id"]


def downtime(person: Person, character_id: str) -> Any:
    return ok(person.client.get(f"/characters/{character_id}/downtime"))


def quest_question(found: dict[str, Any]) -> str:
    return next(q["id"] for q in found["questions"] if q["kind"] == "quest")


def take_up(person: Person, character_id: str, quest_id: str, body: str = "") -> Any:
    """Put in a Quest action for the quest, and submit."""
    question = quest_question(downtime(person, character_id))
    ok(
        person.client.put(
            f"/characters/{character_id}/downtime/answers",
            json={
                "answers": [
                    {"question_id": question, "body": body, "structured": {"quest_id": quest_id}}
                ]
            },
        )
    )
    return ok(person.client.post(f"/characters/{character_id}/downtime/submit"))


def quest_items(troupe: Troupe, cycle: dict[str, Any]) -> list[Any]:
    items = ok(troupe.storyteller.client.get(f"/cycles/{cycle['id']}/responses"))
    return [i for i in items if i["quest"] is not None]


def record(person: Person, response_id: str, result: str = "passed", **body: Any) -> Any:
    return person.client.post(
        f"/responses/{response_id}/quest-result", json={"result": result, **body}
    )


@pytest.fixture
def second(troupe: Troupe) -> Person:
    return sign_up(troupe.client_for, "second")


@pytest.fixture
def third(troupe: Troupe) -> Person:
    return sign_up(troupe.client_for, "third")


# --- the form -------------------------------------------------------------------------------


def test_new_forms_have_the_quest_action_while_quests_are_on(troupe: Troupe) -> None:
    first = new_cycle(troupe)
    assert [q for q in first["questions"] if q["kind"] == "quest"] == []
    assert first["quests_enabled"] is False

    quests_on(troupe)
    # The next form is a copy of the last, with the Quest action added.
    later = new_cycle(troupe)

    [quest] = [q for q in later["questions"] if q["kind"] == "quest"]
    assert (quest["prompt"], quest["action_kind"]) == ("Quest", "general")
    assert later["quests_enabled"] is True
    assert later["action_kinds"]["general"] == "Downtime action"
    # It is added once, not again with every cycle.
    again = new_cycle(troupe)
    assert [q["kind"] for q in again["questions"]].count("quest") == 1


def test_the_quest_action_spends_the_kind_the_troupe_chooses(
    troupe: Troupe, session: Session
) -> None:
    """A troupe gives quests an allowance of their own through the allowance rules."""
    add_house_action_kind(
        session, uuid.UUID(troupe.id), "vampire", ActionKindData(key="questing", name="Questing")
    )
    add_house_allowance_rule(
        session,
        uuid.UUID(troupe.id),
        "vampire",
        AllowanceRuleData(action_kind="questing", scheme="fixed", amount=1),
    )
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = new_cycle(troupe)
    questions = [
        {**q, "action_kind": "questing"} if q["kind"] == "quest" else q for q in cycle["questions"]
    ]
    set_questions(troupe, cycle, questions)
    open_cycle(troupe, cycle)
    quest_id = sent_quest(troupe, agnes)

    take_up(troupe.player, agnes, quest_id)

    found = downtime(troupe.player, agnes)
    assert found["allowance"]["questing"] == 1
    assert found["allowance"]["general"] == 3
    # A second quest would be more questing actions than Agnes has.
    other = sent_quest(troupe, agnes, name="The Second Road")
    question = quest_question(found)
    refused = troupe.player.client.put(
        f"/characters/{agnes}/downtime/answers",
        json={
            "answers": [
                {"question_id": question, "slot": 1, "body": "", "structured": a["structured"]}
                for a in found["answers"]
            ]
            + [{"question_id": question, "slot": 2, "body": "", "structured": {"quest_id": other}}]
        },
    )
    assert refused.status_code == 422
    assert "more questing actions than the 1" in refused.json()["detail"]


# --- choosing and joining -------------------------------------------------------------------


def test_a_character_picks_a_quest_shared_with_it_and_joins_it(
    troupe: Troupe, second: Person
) -> None:
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, second, "Bram")
    cycle = new_cycle(troupe)
    open_cycle(troupe, cycle)
    quest_id = sent_quest(troupe, agnes, downtime_only=True)
    ok(
        troupe.player.client.post(
            f"/characters/{agnes}/quests/{quest_id}/share", json={"character_ids": [bram]}
        )
    )

    [choice] = downtime(second, bram)["quests"]
    assert (choice["name"], choice["role"], choice["downtime_only"]) == (
        "The Lost Journal",
        "invited",
        True,
    )
    assert (choice["scenario"], choice["scenario_count"]) == (1, 2)

    submitted = take_up(second, bram, quest_id, "Bram searches the chantry's records.")

    [answer] = submitted["answers"]
    assert answer["structured"] == {"quest_id": quest_id, "scenario": 1}
    assert answer["body"] == "Bram searches the chantry's records."
    # It counts against Bram's general actions.
    assert submitted["allowance"]["general"] == 3
    seen = ok(second.client.get(f"/characters/{bram}/quests/{quest_id}"))
    assert (seen["role"], seen["party"]) == ("joined", ["Agnes", "Bram"])
    assert seen["downtime_only"] is True


def test_a_quest_chosen_with_nothing_said_is_named_in_the_answer(troupe: Troupe) -> None:
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    quest_id = sent_quest(troupe, agnes)

    submitted = take_up(troupe.player, agnes, quest_id)

    assert submitted["answers"][0]["body"] == "The Lost Journal"


def test_a_quest_the_character_cannot_take_part_in_is_refused(
    troupe: Troupe, second: Person
) -> None:
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, second, "Bram")
    open_cycle(troupe, new_cycle(troupe))
    quest_id = sent_quest(troupe, agnes)
    assert downtime(second, bram)["quests"] == []

    question = quest_question(downtime(second, bram))
    refused = second.client.put(
        f"/characters/{bram}/downtime/answers",
        json={
            "answers": [
                {"question_id": question, "body": "x", "structured": {"quest_id": quest_id}}
            ]
        },
    )

    assert refused.status_code == 422
    assert refused.json()["detail"] == "Bram cannot take part in The Lost Journal."


def test_with_quests_off_the_quest_action_is_not_asked(troupe: Troupe) -> None:
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/quest-settings", json={"enabled": False, "requests_per_cycle": 1}
        )
    )

    found = downtime(troupe.player, agnes)

    assert [q for q in found["questions"] if q["kind"] == "quest"] == []
    assert found["quests"] == []


# --- answering, recording and delivering ----------------------------------------------------


def test_one_result_answers_every_members_action_and_goes_out_with_the_delivery(
    troupe: Troupe, second: Person, third: Person, session: Session, fake: FakeConnector
) -> None:
    quests_on(troupe)
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/connectors/discord",
            json={"enabled": True, "mode": "full", "settings": {"test_target": "#st-test"}},
        )
    )
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, second, "Bram")
    cara = member_character(troupe, third, "Cara")
    cycle = new_cycle(troupe)
    open_cycle(troupe, cycle)
    quest_id = sent_quest(troupe, agnes)
    ok(
        troupe.storyteller.client.post(
            f"/quests/{quest_id}/members", json={"character_ids": [cara], "joined": True}
        )
    )
    ok(
        troupe.player.client.post(
            f"/characters/{agnes}/quests/{quest_id}/share", json={"character_ids": [bram]}
        )
    )

    # The requirements went out when the quest was sent.
    delivery.send_due(session, START)
    fake.sent.clear()

    # Agnes and Bram put in Quest actions for scenario 1; Cara, in the party, does not.
    take_up(troupe.player, agnes, quest_id, "Agnes asks the Nosferatu.")
    take_up(second, bram, quest_id, "Bram searches the records.")
    ok(troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close"))

    items = quest_items(troupe, cycle)
    assert [i["character_name"] for i in items] == ["Agnes", "Bram"]
    first = items[0]["quest"]
    assert (first["name"], first["scenario"], first["scenario_count"]) == (
        "The Lost Journal",
        1,
        2,
    )
    assert first["success_text"] == "You find the cellar."
    assert first["requirements"] == [
        {"label": "Access to Miles' journal", "met": False, "met_by_name": ""}
    ]
    assert first["acted"] == ["Bram"]
    # Nothing's Simple: Cara has not spent the action scenario 1 needs.
    assert first["not_spent"] == ["Cara"]
    staff_view = ok(troupe.storyteller.client.get(f"/quests/{quest_id}"))
    assert staff_view["downtime"] == {
        "cycle_id": cycle["id"],
        "cycle_name": "October 2026",
        "acted": ["Agnes", "Bram"],
        "not_spent": ["Cara"],
    }

    # Staff record one success, and both responses show it.
    recorded = ok(record(troupe.storyteller, items[0]["id"], text="You find the cellar at last."))
    assert recorded["quest"]["result"] == "passed"
    assert recorded["quest"]["awaiting_delivery"] is True
    items = quest_items(troupe, cycle)
    assert [i["status"] for i in items] == ["written", "written"]
    assert {i["body"] for i in items} == {
        "The Lost Journal, scenario 1: passed.\n\nYou find the cellar at last."
    }
    # Only once: scenario 1 is passed.
    assert record(troupe.storyteller, items[1]["id"]).status_code == 409

    # Not out yet: the party sees no result, and nothing is queued.
    seen = ok(troupe.player.client.get(f"/characters/{agnes}/quests/{quest_id}"))
    assert seen["results"] == []
    assert delivery.send_due(session, START) == 0
    staff_view = ok(troupe.storyteller.client.get(f"/quests/{quest_id}"))
    one = staff_view["scenarios"][0]
    assert (one["result"], one["awaiting_delivery"], one["cycle_name"]) == (
        "passed",
        True,
        "October 2026",
    )

    # It goes out with the cycle's delivery: in Agnes's and Bram's downtime results,
    # and as the quest's news to Cara.
    ok(troupe.assistant.client.post(f"/cycles/{cycle['id']}/deliver"))
    assert delivery.send_due(session, START) == 3
    sent = {target: message for target, message in fake.sent}
    assert sorted(sent) == ["#agnes", "#bram", "#cara"]
    assert "You find the cellar at last." in sent["#agnes"].text
    assert "downtime results" in sent["#agnes"].subject
    assert sent["#cara"].subject.endswith("Quest: The Lost Journal, scenario 1 (Cara)")
    results = ok(troupe.player.client.get(f"/characters/{agnes}/downtime/results"))
    assert "You find the cellar at last." in results[0]["message"]
    seen = ok(third.client.get(f"/characters/{cara}/quests/{quest_id}"))
    assert [(r["number"], r["result"]) for r in seen["results"]] == [(1, "passed")]
    summaries = [
        n.summary
        for n in session.scalars(
            select(Notification).where(Notification.user_id == uuid.UUID(third.id))
        )
    ]
    assert "Cara's quest The Lost Journal: scenario 1 passed" in summaries

    # The quest moves on to scenario 2.
    staff_view = ok(troupe.storyteller.client.get(f"/quests/{quest_id}"))
    assert staff_view["status"] == "active"
    assert staff_view["scenarios"][0]["awaiting_delivery"] is False
    assert [s["result"] for s in staff_view["scenarios"]] == ["passed", None]
    # Delivering again sends nothing twice.
    ok(troupe.assistant.client.post(f"/cycles/{cycle['id']}/deliver"))
    assert delivery.send_due(session, START) == 0


def test_the_last_result_shows_the_quest_ended_only_once_delivered(troupe: Troupe) -> None:
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = new_cycle(troupe)
    open_cycle(troupe, cycle)
    quest_id = sent_quest(
        troupe, agnes, category="simple", difficulty=1, scenarios=[{"success_text": "Found."}]
    )
    take_up(troupe.player, agnes, quest_id)
    [item] = quest_items(troupe, cycle)
    assert item["quest"]["not_spent"] == []

    ok(record(troupe.storyteller, item["id"]))

    assert ok(troupe.storyteller.client.get(f"/quests/{quest_id}"))["status"] == "completed"
    seen = ok(troupe.player.client.get(f"/characters/{agnes}/quests/{quest_id}"))
    assert (seen["status"], seen["results"], seen["can_write_tale"]) == ("active", [], False)
    ok(troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close"))
    ok(troupe.storyteller.client.post(f"/cycles/{cycle['id']}/deliver"))
    seen = ok(troupe.player.client.get(f"/characters/{agnes}/quests/{quest_id}"))
    assert (seen["status"], seen["can_write_tale"]) == ("completed", True)
    assert seen["finished_by"] == ["Agnes"]


def test_narrators_record_the_result_of_a_quest_action_assigned_to_them(troupe: Troupe) -> None:
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = new_cycle(troupe)
    open_cycle(troupe, cycle)
    quest_id = sent_quest(troupe, agnes)
    take_up(troupe.player, agnes, quest_id)
    [item] = quest_items(troupe, cycle)

    assert record(troupe.narrator, item["id"]).status_code == 403
    ok(
        troupe.storyteller.client.put(
            f"/responses/{item['id']}/assignment", json={"user_id": troupe.narrator.id}
        )
    )
    [mine] = ok(troupe.narrator.client.get(f"/cycles/{cycle['id']}/responses/mine"))
    assert mine["quest"]["fail_text"] == "The cellar floods."

    failed = ok(record(troupe.narrator, item["id"], "failed"))

    assert failed["status"] == "written"
    assert failed["body"] == "The Lost Journal, scenario 1: failed.\n\nThe cellar floods."
    # Failed and not ended: the party tries scenario 1 again.
    quest = ok(troupe.storyteller.client.get(f"/quests/{quest_id}"))
    assert (quest["status"], quest["scenarios"][0]["result"]) == ("active", "failed")


# --- Downtime Only --------------------------------------------------------------------------


def test_a_downtime_only_quest_refuses_a_result_recorded_outside_a_cycle(troupe: Troupe) -> None:
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = new_cycle(troupe)
    open_cycle(troupe, cycle)
    quest_id = sent_quest(troupe, agnes, downtime_only=True)

    refused = troupe.storyteller.client.post(
        f"/quests/{quest_id}/scenarios/1/result", json={"result": "passed"}
    )

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "This quest is downtime only: its results are recorded from a Quest action "
        "in a downtime cycle."
    )
    # Through a Quest action, it is recorded.
    take_up(troupe.player, agnes, quest_id)
    [item] = quest_items(troupe, cycle)
    assert item["quest"]["downtime_only"] is True
    ok(record(troupe.storyteller, item["id"]))
    quest = ok(troupe.storyteller.client.get(f"/quests/{quest_id}"))
    assert quest["scenarios"][0]["result"] == "passed"


def test_a_result_recorded_at_a_game_still_goes_out_at_once(
    troupe: Troupe, session: Session, fake: FakeConnector
) -> None:
    quests_on(troupe)
    ok(
        troupe.storyteller.client.put(
            f"/troupes/{troupe.id}/connectors/discord",
            json={"enabled": True, "mode": "full", "settings": {"test_target": "#st-test"}},
        )
    )
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    quest_id = sent_quest(troupe, agnes)
    delivery.send_due(session, START)
    fake.sent.clear()

    ok(
        troupe.storyteller.client.post(
            f"/quests/{quest_id}/scenarios/1/result", json={"result": "passed"}
        )
    )

    assert delivery.send_due(session, START) == 1
    seen = ok(troupe.player.client.get(f"/characters/{agnes}/quests/{quest_id}"))
    assert [r["number"] for r in seen["results"]] == [1]


def test_an_action_waiting_in_a_draft_moves_on_when_its_scenario_passes_at_a_game(
    troupe: Troupe,
) -> None:
    quests_on(troupe)
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    quest_id = sent_quest(troupe, agnes)
    question = quest_question(downtime(troupe.player, agnes))
    url = f"/characters/{agnes}/downtime/answers"
    answer = {"question_id": question, "body": "x", "structured": {"quest_id": quest_id}}
    saved = ok(troupe.player.client.put(url, json={"answers": [answer]}))
    assert saved["answers"][0]["structured"]["scenario"] == 1

    ok(
        troupe.storyteller.client.post(
            f"/quests/{quest_id}/scenarios/1/result", json={"result": "passed"}
        )
    )
    again = ok(
        troupe.player.client.put(
            url, json={"answers": [{**answer, "structured": saved["answers"][0]["structured"]}]}
        )
    )

    assert again["answers"][0]["structured"] == {"quest_id": quest_id, "scenario": 2}
