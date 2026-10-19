"""XP for completing a downtime, set per cycle from the troupe's usual amount
(issue #57), and the troupe's usual XP for a session."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent
from tests.api_helpers import Troupe
from tests.test_api_downtimes import NOW, member_character, my_downtime, new_cycle, open_cycle


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def xp_lines(troupe: Troupe, character_id: str) -> list[tuple[str, int]]:
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    return [(e["reason"], e["amount"]) for e in history if e["reason"].startswith("Completed")]


def submit(troupe: Troupe, character_id: str) -> Any:
    response = troupe.player.client.post(f"/characters/{character_id}/downtime/submit")
    assert response.status_code == 200, response.text
    return response.json()


def test_troupes_start_with_8_and_2_and_storytellers_change_them(troupe: Troupe) -> None:
    shown = troupe.player.client.get(f"/troupes/{troupe.id}").json()
    assert (shown["session_xp"], shown["downtime_xp"]) == (8, 2)
    assert (
        troupe.assistant.client.patch(f"/troupes/{troupe.id}", json={"downtime_xp": 3}).status_code
        == 403
    )
    changed = troupe.storyteller.client.patch(
        f"/troupes/{troupe.id}", json={"session_xp": 6, "downtime_xp": 3}
    )
    assert changed.status_code == 200, changed.text
    assert (changed.json()["session_xp"], changed.json()["downtime_xp"]) == (6, 3)
    assert (
        troupe.lead.client.patch(f"/troupes/{troupe.id}", json={"session_xp": -1}).status_code
        == 422
    )


def test_a_cycle_takes_the_troupes_amount_unless_given_one(troupe: Troupe) -> None:
    assert new_cycle(troupe)["completion_xp"] == 2
    troupe.storyteller.client.patch(f"/troupes/{troupe.id}", json={"downtime_xp": 4})
    assert new_cycle(troupe)["completion_xp"] == 4
    given = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/cycles",
        json={
            "name": "Special",
            "closes_at": NOW.isoformat(),
            "grace_ends_at": NOW.isoformat(),
            "completion_xp": 0,
        },
    )
    assert given.json()["completion_xp"] == 0


def test_submitting_earns_it_once(troupe: Troupe, session: Session) -> None:
    character_id = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    before = my_downtime(troupe.player, character_id).json()
    assert (before["completion_xp"], before["completion_xp_awarded"]) == (2, None)

    after = submit(troupe, character_id)
    assert after["completion_xp_awarded"] == 2
    submit(troupe, character_id)  # submitted again while open: no second award
    assert xp_lines(troupe, character_id) == [("Completed downtime: October 2026", 2)]

    [participant] = troupe.storyteller.client.get(f"/cycles/{cycle['id']}/participants").json()
    assert participant["completion_xp_awarded"] == 2
    assert session.scalars(
        select(AuditEvent.action).where(AuditEvent.action == "xp.downtime_completed")
    ).all() == ["xp.downtime_completed"]


def test_changing_it_until_the_cycle_closes(troupe: Troupe) -> None:
    character_id = member_character(troupe, troupe.player, "Agnes")
    cycle = open_cycle(troupe, new_cycle(troupe))
    narrator = troupe.narrator.client.patch(f"/cycles/{cycle['id']}", json={"completion_xp": 5})
    assert narrator.status_code == 403
    changed = troupe.assistant.client.patch(f"/cycles/{cycle['id']}", json={"completion_xp": 5})
    assert changed.json()["completion_xp"] == 5
    submit(troupe, character_id)
    assert xp_lines(troupe, character_id) == [("Completed downtime: October 2026", 5)]

    troupe.storyteller.client.post(f"/cycles/{cycle['id']}/close")
    closed = troupe.storyteller.client.patch(f"/cycles/{cycle['id']}", json={"completion_xp": 1})
    assert closed.status_code == 409


def test_none_when_the_cycle_gives_none(troupe: Troupe) -> None:
    character_id = member_character(troupe, troupe.player, "Agnes")
    cycle = new_cycle(troupe)
    troupe.storyteller.client.patch(f"/cycles/{cycle['id']}", json={"completion_xp": 0})
    open_cycle(troupe, cycle)
    assert submit(troupe, character_id)["completion_xp_awarded"] is None
    assert xp_lines(troupe, character_id) == []
