"""What is waiting on a troupe's staff (issue #149): the counts, and who sees which."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import DowntimeCycle
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_downtimes import member_character, new_cycle, open_cycle, question_id, save
from tests.test_api_responses import Scene

NOW = datetime.now(UTC)


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def waiting(troupe: Troupe, person: Person) -> dict[str, dict[str, Any]]:
    response = person.client.get(f"/troupes/{troupe.id}/waiting")
    assert response.status_code == 200, response.text
    return {line["kind"]: line for line in response.json()}


def counts(troupe: Troupe, person: Person) -> dict[str, int]:
    return {kind: line["count"] for kind, line in waiting(troupe, person).items()}


def test_nothing_waiting_is_no_lines(troupe: Troupe) -> None:
    assert counts(troupe, troupe.lead) == {}


def test_only_staff_see_what_is_waiting(troupe: Troupe) -> None:
    for person in (troupe.player, troupe.stranger):
        assert person.client.get(f"/troupes/{troupe.id}/waiting").status_code == 403


def test_approvals_count_every_pending_approval_and_link_to_the_tab(troupe: Troupe) -> None:
    for name in ("Agnes", "Bea"):
        character_id = new_character(troupe, troupe.player, name)
        asked = troupe.player.client.post(
            f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
        )
        assert asked.status_code == 201, asked.text

    line = waiting(troupe, troupe.assistant)["approvals"]
    pending = troupe.assistant.client.get(
        f"/troupes/{troupe.id}/approvals", params={"state": "pending"}
    ).json()
    assert line["count"] == len(pending) == 2
    assert line["link"] == f"/troupes/{troupe.id}/approvals"
    # Narrators approve nothing, so they are not shown it.
    assert "approvals" not in waiting(troupe, troupe.narrator)


def test_the_cycle_under_way_shows_submitted_unassigned_and_unwritten(troupe: Troupe) -> None:
    scene = Scene(troupe)
    cycle_id = scene.cycle["id"]

    lines = waiting(troupe, troupe.storyteller)
    assert {k: v["count"] for k, v in lines.items()} == {
        "cycle_submitted": 1,
        "cycle_unassigned": 4,
        "cycle_unwritten": 4,
    }
    assert lines["cycle_submitted"]["label"] == "October 2026: downtimes submitted, of 1"
    assert lines["cycle_submitted"]["link"] == f"/cycles/{cycle_id}/participants"
    assert lines["cycle_unwritten"]["link"] == f"/cycles/{cycle_id}/responses"
    # The same figures as the cycle's progress.
    progress = troupe.storyteller.client.get(f"/cycles/{cycle_id}/progress").json()
    assert progress["unassigned"] == 4
    assert progress["responses"] - progress["written"] == 4

    # Assigned to the storyteller and written: one fewer of each.
    assert scene.assign("Feed at the docks", user_id=troupe.storyteller.id).status_code == 200
    response = scene.response_for("Feed at the docks")
    written = troupe.storyteller.client.put(
        f"/responses/{response['id']}", json={"body": "You feed well."}
    )
    assert written.status_code == 200, written.text
    after = counts(troupe, troupe.storyteller)
    assert (after["cycle_unassigned"], after["cycle_unwritten"]) == (3, 3)
    # A narrator sees none of the cycle's own lines.
    assert counts(troupe, troupe.narrator) == {}


def test_staff_see_responses_for_them_to_write(troupe: Troupe) -> None:
    scene = Scene(troupe)
    scene.assign("Feed at the docks", user_id=troupe.narrator.id)
    scene.assign("Patrol the park", any_narrator=True)
    scene.assign("Lean on the mayor", user_id=troupe.storyteller.id)

    line = waiting(troupe, troupe.narrator)["my_responses"]
    # Their own, and the any-narrator pool.
    assert line["count"] == 2
    assert line["link"] == f"/troupes/{troupe.id}/work/{scene.cycle['id']}"
    assert counts(troupe, troupe.storyteller)["my_responses"] == 1
    assert "my_responses" not in counts(troupe, troupe.assistant)

    mine = scene.response_for("Feed at the docks")
    troupe.narrator.client.put(f"/responses/{mine['id']}", json={"body": "Done."})
    assert counts(troupe, troupe.narrator)["my_responses"] == 1


def test_late_downtimes_wait_to_be_accepted_after_the_grace_period(
    troupe: Troupe, session: Session
) -> None:
    member_character(troupe, troupe.player, "Agnes")
    bea = member_character(troupe, troupe.player, "Bea")
    cycle = open_cycle(troupe, new_cycle(troupe))
    form = troupe.player.client.get(f"/characters/{bea}/downtime").json()
    general = question_id(form, "Downtime action")
    assert save(troupe.player, bea, [{"question_id": general, "slot": 1, "body": "Hunt"}])
    assert "cycle_late" not in counts(troupe, troupe.storyteller)

    # The grace period ends with Bea's downtime still a draft.
    row = session.get_one(DowntimeCycle, uuid.UUID(cycle["id"]))
    row.closes_at, row.grace_ends_at = NOW - timedelta(days=2), NOW - timedelta(days=1)
    session.flush()
    assert counts(troupe, troupe.storyteller)["cycle_late"] == 1

    participants = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/participants").json()
    for p in participants:
        troupe.storyteller.client.post(f"/cycles/{cycle['id']}/participants/{p['id']}/accept-late")
    assert "cycle_late" not in counts(troupe, troupe.storyteller)


def test_results_ready_to_deliver_once_the_cycle_is_closed(troupe: Troupe) -> None:
    scene = Scene(troupe)
    cycle_id = scene.cycle["id"]
    scene.assign("Feed at the docks", user_id=troupe.storyteller.id)
    response = scene.response_for("Feed at the docks")
    troupe.storyteller.client.put(f"/responses/{response['id']}", json={"body": "You feed."})
    assert "deliveries" not in counts(troupe, troupe.storyteller)

    assert troupe.storyteller.client.post(f"/cycles/{cycle_id}/close").status_code == 200
    line = waiting(troupe, troupe.assistant)["deliveries"]
    assert line["count"] == 1
    assert line["link"] == f"/cycles/{cycle_id}/delivery"
    assert "deliveries" not in counts(troupe, troupe.narrator)

    assert troupe.storyteller.client.post(f"/cycles/{cycle_id}/deliver").status_code == 200
    assert "deliveries" not in counts(troupe, troupe.storyteller)


def test_allowance_shortfalls_in_the_open_cycle(troupe: Troupe) -> None:
    member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    participant = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/participants").json()[0]
    kind, amount = next(iter(participant["allowance"].items()))
    adjusted = troupe.storyteller.client.post(
        f"/cycles/{cycle['id']}/participants/{participant['id']}/adjustments",
        json={"action_kind": kind, "delta": -amount - 1, "reason": "Spent at the game"},
    )
    assert adjusted.status_code == 201, adjusted.text

    line = waiting(troupe, troupe.assistant)["shortfalls"]
    assert line["count"] == 1
    assert line["link"] == f"/cycles/{cycle['id']}/participants"


def test_influence_entries_that_need_details_and_effects_ending_this_week(
    troupe: Troupe,
) -> None:
    log = f"/troupes/{troupe.id}/influence-log"
    logged = troupe.storyteller.client.post(
        log,
        json={
            "type": "elite",
            "happened_at": NOW.isoformat(),
            "name": "Prince Vasquez",
            "needs_details": True,
        },
    )
    assert logged.status_code == 201, logged.text
    for activity, lasts in (("Buying the docks", 2), ("Owning the press", 40)):
        recorded = troupe.storyteller.client.post(
            f"/troupes/{troupe.id}/influence-blocks",
            json={
                "type": "elite",
                "activity": activity,
                "strength": 2,
                "starts_at": (NOW - timedelta(hours=1)).isoformat(),
                "ends_at": (NOW + timedelta(days=lasts)).isoformat(),
            },
        )
        assert recorded.status_code == 201, recorded.text

    lines = waiting(troupe, troupe.assistant)
    assert lines["influence_details"]["count"] == 1
    assert lines["influence_details"]["link"] == f"/troupes/{troupe.id}/influence?needs=details"
    assert lines["effects_ending"]["count"] == 1
    assert lines["effects_ending"]["link"] == f"/troupes/{troupe.id}/influence/effects"
    # Narrators never see the influence log.
    assert counts(troupe, troupe.narrator) == {}
