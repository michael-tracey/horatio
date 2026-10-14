"""Downtime cycles, forms, participants and submissions."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.rules.model import ActionKindData, AllowanceRuleData
from horatio.rules.store import add_house_action_kind, add_house_allowance_rule
from tests.api_helpers import Person, Troupe, sign_up

NOW = datetime.now(UTC)


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def member_character(troupe: Troupe, player: Person, name: str, elite: int = 0) -> str:
    """An approved character whose home troupe is `troupe`."""
    response = player.client.post("/characters", json={"splat": "vampire", "name": name})
    character_id = response.json()["id"]
    if elite:
        bought = player.client.put(
            f"/characters/{character_id}/traits",
            json={"category": "backgrounds", "name": "Influences: The Elite", "rating": elite},
        )
        assert bought.status_code == 200, bought.text
    requested = player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert requested.status_code == 201, requested.text
    approved = troupe.lead.client.post(f"/approvals/{requested.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    return character_id


def new_cycle(
    troupe: Troupe, closes_in: timedelta = timedelta(days=7), grace: timedelta = timedelta(days=7)
) -> dict[str, Any]:
    response = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/cycles",
        json={
            "name": "October 2026",
            "closes_at": (NOW + closes_in).isoformat(),
            "grace_ends_at": (NOW + closes_in + grace).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def open_cycle(troupe: Troupe, cycle: dict[str, Any]) -> dict[str, Any]:
    response = troupe.storyteller.client.post(f"/cycles/{cycle['id']}/open")
    assert response.status_code == 200, response.text
    return response.json()


def set_questions(
    troupe: Troupe, cycle: dict[str, Any], questions: list[dict[str, Any]]
) -> dict[str, Any]:
    response = troupe.storyteller.client.put(f"/cycles/{cycle['id']}/questions", json=questions)
    assert response.status_code == 200, response.text
    return response.json()


def my_downtime(player: Person, character_id: str) -> Any:
    return player.client.get(f"/characters/{character_id}/downtime")


def save(player: Person, character_id: str, answers: list[dict[str, Any]]) -> Any:
    return player.client.put(
        f"/characters/{character_id}/downtime/answers", json={"answers": answers}
    )


def question_id(downtime: dict[str, Any], prompt: str) -> str:
    return next(q["id"] for q in downtime["questions"] if q["prompt"] == prompt)


# --- cycles and forms --------------------------------------------------------------------


def test_a_first_cycle_starts_with_one_question_per_action_kind(troupe: Troupe) -> None:
    cycle = new_cycle(troupe)

    assert cycle["status"] == "draft"
    assert [(q["kind"], q["action_kind"]) for q in cycle["questions"]] == [
        ("action", "general"),
        ("action", "influence_elite"),
        ("action", "influence_underworld"),
        ("action", "resources"),
    ]


def test_running_staff_manage_cycles_and_narrators_do_not(troupe: Troupe) -> None:
    body = {"name": "x", "closes_at": NOW.isoformat(), "grace_ends_at": NOW.isoformat()}
    for person in (troupe.narrator, troupe.player):
        assert person.client.post(f"/troupes/{troupe.id}/cycles", json=body).status_code == 403
    assert (
        troupe.assistant.client.post(f"/troupes/{troupe.id}/cycles", json=body).status_code == 201
    )


def test_storytellers_add_custom_questions(troupe: Troupe) -> None:
    cycle = new_cycle(troupe)
    questions = cycle["questions"] + [
        {"kind": "custom", "prompt": "Nominations?", "answer_type": "long_text"},
        {
            "kind": "custom",
            "prompt": "Attending?",
            "answer_type": "choice",
            "options": ["Yes", "No"],
            "required": True,
        },
    ]

    updated = set_questions(troupe, cycle, questions)

    assert [q["prompt"] for q in updated["questions"]][-2:] == ["Nominations?", "Attending?"]
    # Existing questions kept their ids.
    assert [q["id"] for q in updated["questions"]][:4] == [q["id"] for q in cycle["questions"]]


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "custom", "prompt": "Pick", "answer_type": "choice"},
        {"kind": "action", "action_kind": "flying", "prompt": "Fly"},
        {"kind": "custom", "action_kind": "general", "prompt": "Hmm"},
    ],
)
def test_bad_questions_are_refused(troupe: Troupe, bad: dict[str, Any]) -> None:
    cycle = new_cycle(troupe)

    response = troupe.storyteller.client.put(f"/cycles/{cycle['id']}/questions", json=[bad])

    assert response.status_code == 422


def test_the_next_cycle_copies_the_last_form(troupe: Troupe) -> None:
    first = new_cycle(troupe)
    set_questions(troupe, first, [{"kind": "custom", "prompt": "Nominations?"}])

    second = new_cycle(troupe)

    assert [q["prompt"] for q in second["questions"]] == ["Nominations?"]
    assert second["questions"][0]["id"] != first["questions"][0]["id"]


# --- opening, participants and allowances ---------------------------------------------------


def test_opening_fixes_participants_and_their_allowances(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes", elite=2)
    draft = troupe.stranger.client.post("/characters", json={"splat": "vampire", "name": "Draft"})
    cycle = new_cycle(troupe)

    open_cycle(troupe, cycle)

    participants = troupe.assistant.client.get(f"/cycles/{cycle['id']}/participants").json()
    assert [p["character_name"] for p in participants] == ["Agnes"]
    assert draft.json()["id"] not in [p["character_id"] for p in participants]
    assert participants[0]["allowance"] == {
        "general": 3,
        "influence_elite": 2,
        "influence_underworld": 0,
        "resources": 0,
    }
    assert participants[0]["breakdown"] == [
        {"action_kind": "general", "source": "Everyone", "amount": 3},
        {"action_kind": "influence_elite", "source": "Influences: The Elite 2", "amount": 2},
    ]
    # Fixed at opening: a later sheet change does not alter it.
    troupe.player.client.put(
        f"/characters/{agnes}/traits",
        json={"category": "backgrounds", "name": "Influences: The Elite", "rating": 3},
    )
    assert my_downtime(troupe.player, agnes).json()["allowance"]["influence_elite"] == 2


def test_house_rules_change_allowances(troupe: Troupe, session: Session) -> None:
    add_house_allowance_rule(
        session,
        uuid.UUID(troupe.id),
        "vampire",
        AllowanceRuleData(action_kind="general", scheme="fixed", amount=2),
    )
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))

    # The troupe's base of 2 replaced the generic 3.
    assert my_downtime(troupe.player, agnes).json()["allowance"]["general"] == 2


def test_troupes_add_their_own_action_kinds(troupe: Troupe, session: Session) -> None:
    add_house_action_kind(
        session, uuid.UUID(troupe.id), "vampire", ActionKindData(key="hunt", name="Hunting")
    )
    add_house_allowance_rule(
        session,
        uuid.UUID(troupe.id),
        "vampire",
        AllowanceRuleData(action_kind="hunt", scheme="fixed", amount=1),
    )
    agnes = member_character(troupe, troupe.player, "Agnes")

    cycle = new_cycle(troupe)
    open_cycle(troupe, cycle)

    assert "hunt" in [q["action_kind"] for q in cycle["questions"]]
    assert my_downtime(troupe.player, agnes).json()["allowance"]["hunt"] == 1


def test_only_one_open_cycle_per_troupe(troupe: Troupe) -> None:
    open_cycle(troupe, new_cycle(troupe))
    second = new_cycle(troupe)

    assert troupe.storyteller.client.post(f"/cycles/{second['id']}/open").status_code == 409


def test_staff_add_and_remove_participants(troupe: Troupe) -> None:
    cycle = open_cycle(troupe, new_cycle(troupe))
    late_joiner = member_character(troupe, troupe.player, "Late Joiner")
    outsider = troupe.stranger.client.post(
        "/characters", json={"splat": "vampire", "name": "Outsider"}
    ).json()["id"]

    assert (
        troupe.assistant.client.post(
            f"/cycles/{cycle['id']}/participants", json={"character_id": outsider}
        ).status_code
        == 409
    )
    added = troupe.assistant.client.post(
        f"/cycles/{cycle['id']}/participants", json={"character_id": late_joiner}
    )
    assert added.status_code == 201
    assert my_downtime(troupe.player, late_joiner).status_code == 200

    removed = troupe.assistant.client.delete(
        f"/cycles/{cycle['id']}/participants/{added.json()['id']}"
    )
    assert removed.status_code == 204
    assert my_downtime(troupe.player, late_joiner).status_code == 404
    listed = troupe.assistant.client.get(f"/cycles/{cycle['id']}/participants").json()
    assert listed[0]["removed"] is True


def test_adjusting_an_allowance(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    participant = troupe.assistant.client.get(f"/cycles/{cycle['id']}/participants").json()[0]
    body = {"action_kind": "general", "delta": 1, "reason": "Won the city's favour"}

    assert (
        troupe.narrator.client.post(
            f"/cycles/{cycle['id']}/participants/{participant['id']}/adjustments", json=body
        ).status_code
        == 403
    )
    adjusted = troupe.assistant.client.post(
        f"/cycles/{cycle['id']}/participants/{participant['id']}/adjustments", json=body
    )

    assert adjusted.json()["allowance"]["general"] == 4
    assert my_downtime(troupe.player, agnes).json()["adjustments"] == [body]


# --- filling in and submitting ----------------------------------------------------------------


def test_players_see_only_questions_they_have_actions_for(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes", elite=1)
    open_cycle(troupe, new_cycle(troupe))

    prompts = [q["prompt"] for q in my_downtime(troupe.player, agnes).json()["questions"]]

    assert prompts == ["Downtime action", "Elite influence action"]


def test_answering_within_the_allowance(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    action = question_id(my_downtime(troupe.player, agnes).json(), "Downtime action")

    four = [{"question_id": action, "slot": n, "body": f"Action {n}"} for n in range(1, 5)]
    assert save(troupe.player, agnes, four).status_code == 422

    saved = save(troupe.player, agnes, four[:3])
    assert saved.status_code == 200, saved.text
    assert [a["body"] for a in saved.json()["answers"]] == ["Action 1", "Action 2", "Action 3"]
    assert saved.json()["status"] == "draft"


def test_required_questions_must_be_answered_before_submitting(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = new_cycle(troupe)
    set_questions(
        troupe,
        cycle,
        cycle["questions"]
        + [
            {
                "kind": "custom",
                "prompt": "Attending?",
                "answer_type": "choice",
                "options": ["Yes", "No"],
                "required": True,
            }
        ],
    )
    open_cycle(troupe, cycle)
    attending = question_id(my_downtime(troupe.player, agnes).json(), "Attending?")

    assert troupe.player.client.post(f"/characters/{agnes}/downtime/submit").status_code == 422
    assert (
        save(troupe.player, agnes, [{"question_id": attending, "body": "Maybe"}]).status_code == 422
    )
    save(troupe.player, agnes, [{"question_id": attending, "body": "Yes"}])

    submitted = troupe.player.client.post(f"/characters/{agnes}/downtime/submit")
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["late"] is False
    participants = troupe.assistant.client.get(f"/cycles/{cycle['id']}/participants").json()
    assert participants[0]["submission_status"] == "submitted"


def test_submissions_after_the_close_are_late_and_after_the_grace_period_refused(
    troupe: Troupe,
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    late_cycle = open_cycle(troupe, new_cycle(troupe, closes_in=timedelta(days=-1)))
    submitted = troupe.player.client.post(f"/characters/{agnes}/downtime/submit")
    assert submitted.json()["late"] is True
    troupe.storyteller.client.post(f"/cycles/{late_cycle['id']}/close")

    over = open_cycle(
        troupe, new_cycle(troupe, closes_in=timedelta(days=-2), grace=timedelta(days=1))
    )
    assert troupe.player.client.post(f"/characters/{agnes}/downtime/submit").status_code == 409
    participant = troupe.assistant.client.get(f"/cycles/{over['id']}/participants").json()[0]
    troupe.assistant.client.post(
        f"/cycles/{over['id']}/participants/{participant['id']}/accept-late"
    )
    assert troupe.player.client.post(f"/characters/{agnes}/downtime/submit").status_code == 200


def test_a_closed_cycle_takes_no_more_answers(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    action = question_id(my_downtime(troupe.player, agnes).json(), "Downtime action")

    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")

    assert my_downtime(troupe.player, agnes).status_code == 404
    assert save(troupe.player, agnes, [{"question_id": action, "body": "x"}]).status_code == 404


def test_answered_questions_cannot_be_removed_from_the_form(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    action = question_id(my_downtime(troupe.player, agnes).json(), "Downtime action")
    save(troupe.player, agnes, [{"question_id": action, "body": "Feed"}])

    response = troupe.storyteller.client.put(f"/cycles/{cycle['id']}/questions", json=[])

    assert response.status_code == 409


def test_only_the_player_fills_in_their_downtime(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    open_cycle(troupe, new_cycle(troupe))
    other = sign_up(troupe.client_for, "other")

    assert my_downtime(other, agnes).status_code == 404
    assert my_downtime(troupe.storyteller, agnes).status_code == 403
