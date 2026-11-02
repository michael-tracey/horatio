"""Leaving a character's home troupe (issue #459): what it ends, said first; the
troupe's running staff told and the log; visits and a request elsewhere left alone;
and being accepted again takes no XP and brings no free changes back."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio.models import Notification, XpEntry
from tests.api_helpers import Person, Troupe, backstory_optional, new_character
from tests.test_api_free_changes import set_free_changes
from tests.test_api_merit_requests import rating, spend
from tests.test_api_quests import ok


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def accepted(troupe: Troupe, troupe_id: str | None = None) -> str:
    """Agnes, a Camarilla Toreador, accepted home in `troupe_id` (the troupe's own)."""
    agnes = new_character(troupe, troupe.player, "Agnes", clan="Toreador")
    ok(
        troupe.player.client.put(
            f"/characters/{agnes}/traits",
            json={"category": "sect", "name": "Camarilla", "rating": None},
        )
    )
    accept(troupe, agnes, troupe_id or troupe.id, troupe.lead)
    return agnes


def accept(troupe: Troupe, character_id: str, troupe_id: str, staff: Person) -> None:
    asked = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe_id}
    )
    assert asked.status_code == 201, asked.text
    ok(staff.client.post(f"/approvals/{asked.json()['id']}/approve", json={}))


def award(troupe: Troupe, character_id: str, amount: int) -> None:
    given = troupe.lead.client.post(
        f"/characters/{character_id}/xp", json={"amount": amount, "reason": "Games played"}
    )
    assert given.status_code == 201, given.text


def other_troupe(troupe: Troupe, name: str) -> str:
    """Another troupe, its lead the storyteller."""
    made = troupe.custodian.client.post(
        "/troupes", json={"name": name, "lead_handle": troupe.storyteller.handle}
    )
    assert made.status_code == 201, made.text
    backstory_optional(troupe.session, made.json()["id"])
    return made.json()["id"]


def leaving(person: Person, character_id: str, troupe_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/troupes/{troupe_id}/leaving")


def leave(person: Person, character_id: str, troupe_id: str) -> None:
    left = person.client.delete(f"/characters/{character_id}/troupes/{troupe_id}")
    assert left.status_code == 204, left.text


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    return ok(person.client.get(f"/characters/{character_id}/sheet"))


def told(troupe: Troupe, person: Person) -> list[str]:
    return list(
        troupe.session.scalars(
            select(Notification.summary).where(
                Notification.user_id == uuid.UUID(person.id),
                Notification.kind == "troupe.left_home",
            )
        )
    )


def log(person: Person, troupe_id: str) -> list[str]:
    return [e["message"] for e in ok(person.client.get(f"/troupes/{troupe_id}/log"))]


def test_leaving_says_first_what_ends_then_ends_it_and_tells_the_running_staff(
    troupe: Troupe,
) -> None:
    agnes = accepted(troupe)
    ok(
        troupe.assistant.client.put(
            f"/troupes/{troupe.id}/characters/{agnes}/titles", json={"titles": ["Prince"]}
        )
    )
    award(troupe, agnes, 10)
    start = sheet(troupe.player, agnes)["xp"]["balance"]
    ok(spend(troupe.player, agnes, rating("disciplines", "Celerity", 1)))
    ok(spend(troupe.player, agnes, rating("merits", "Rugged", 3)))
    held = {p["name"]: p["cost"] for p in sheet(troupe.player, agnes)["pending_disciplines"]}

    found = ok(leaving(troupe.player, agnes, troupe.id))

    assert found == {
        "home": True,
        "titles": ["Prince"],
        "requests": [
            {"what": "Celerity 0 → 1", "refund": held["Celerity"]},
            {"what": "Add Rugged", "refund": 3},
        ],
        "free_changes_open": False,
    }
    # Only its player asks.
    assert leaving(troupe.lead, agnes, troupe.id).status_code == 403

    leave(troupe.player, agnes, troupe.id)

    after = sheet(troupe.player, agnes)
    assert after["xp"]["balance"] == start
    assert after["pending_disciplines"] == []
    assert after["xp"]["unbanked"] == 0
    assert ok(troupe.player.client.get(f"/characters/{agnes}"))["home_troupe_id"] is None
    roster = ok(troupe.lead.client.get(f"/troupes/{troupe.id}/characters"))
    assert agnes not in {c["id"] for c in roster}
    # Its running staff are told; its narrator and its player are not.
    for person in (troupe.lead, troupe.storyteller, troupe.assistant):
        assert told(troupe, person) == ["Agnes left Lords of the Night as its home troupe"]
    assert told(troupe, troupe.narrator) == told(troupe, troupe.player) == []
    assert log(troupe.lead, troupe.id)[0] == (
        "Agnes (player) left Lords of the Night as its home troupe, and has no home troupe now."
    )
    # Not in the troupe any more, there is nothing to leave.
    assert leaving(troupe.player, agnes, troupe.id).status_code == 409


def test_visits_and_a_request_to_make_another_troupe_home_stay(troupe: Troupe) -> None:
    agnes = accepted(troupe)
    visited = other_troupe(troupe, "Second City")
    wanted = other_troupe(troupe, "Third Ward")
    ok(
        troupe.player.client.post(f"/characters/{agnes}/troupes", json={"troupe_id": visited}),
        201,
    )
    asked = troupe.player.client.post(
        f"/characters/{agnes}/home-troupe", json={"troupe_id": wanted}
    )
    assert asked.status_code == 201, asked.text

    assert ok(leaving(troupe.player, agnes, troupe.id))["requests"] == []
    leave(troupe.player, agnes, troupe.id)

    memberships = ok(troupe.player.client.get(f"/characters/{agnes}/troupes"))
    assert {(m["troupe_name"], m["home"]) for m in memberships} >= {("Second City", False)}
    assert "Lords of the Night" not in {m["troupe_name"] for m in memberships}
    [waiting] = sheet(troupe.player, agnes)["pending_approvals"]
    assert (waiting["kind"], waiting["troupe_id"]) == ("home_troupe_change", wanted)
    # The request still goes through, into a home with no creation XP lost.
    lost = select(func.count()).select_from(XpEntry).where(XpEntry.kind == "lost")
    before = troupe.session.scalar(lost)
    ok(troupe.storyteller.client.post(f"/approvals/{waiting['id']}/approve", json={}))
    assert ok(troupe.player.client.get(f"/characters/{agnes}"))["home_troupe_id"] == wanted
    assert troupe.session.scalar(lost) == before


def test_leaving_a_visit_reads_as_a_visit_and_tells_no_one(troupe: Troupe) -> None:
    agnes = accepted(troupe)
    visited = other_troupe(troupe, "Second City")
    ok(
        troupe.player.client.post(f"/characters/{agnes}/troupes", json={"troupe_id": visited}),
        201,
    )

    assert ok(leaving(troupe.player, agnes, visited))["home"] is False
    leave(troupe.player, agnes, visited)

    assert log(troupe.storyteller, visited)[0] == "Agnes (player) stopped visiting Second City."
    assert told(troupe, troupe.storyteller) == []
    assert ok(troupe.player.client.get(f"/characters/{agnes}"))["home_troupe_id"] == troupe.id


def test_accepted_again_it_loses_no_xp_and_its_free_changes_stay_ended(troupe: Troupe) -> None:
    ok(set_free_changes(troupe, "date", days=30))
    agnes = accepted(troupe)
    award(troupe, agnes, 20)
    assert sheet(troupe.player, agnes)["free_changes"] is not None
    assert ok(leaving(troupe.player, agnes, troupe.id))["free_changes_open"] is True
    balance = sheet(troupe.player, agnes)["xp"]["balance"]

    leave(troupe.player, agnes, troupe.id)

    # Its XP was given, not left over from creation: none of it would be lost.
    assert sheet(troupe.player, agnes)["xp"]["unbanked"] == 0
    accept(troupe, agnes, troupe.id, troupe.lead)
    after = sheet(troupe.player, agnes)
    assert after["xp"]["balance"] == balance
    assert after["free_changes"] is None
    # The player ended them by leaving; the log says so, the bell does not.
    ended = "Agnes (player)'s free changes as a new character ended: it left Lords of the Night."
    assert ended in log(troupe.lead, troupe.id)
    assert not troupe.session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.kind == "character.free_changes_ended")
    )
