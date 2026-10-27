"""The custodian's search of the audit log, across every troupe."""

import csv
import io
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from horatio.api.audit import GROUPS
from horatio.api.roster import MESSAGES
from horatio.models import AuditEvent
from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def search(custodian: Person, **filters: Any) -> dict[str, Any]:
    response = custodian.client.get("/audit", params=filters)
    assert response.status_code == 200, response.text
    return response.json()


def messages(custodian: Person, **filters: Any) -> list[str]:
    return [e["message"] for e in search(custodian, **filters)["entries"]]


def second_troupe(troupe: Troupe, name: str = "Court of Ash") -> str:
    """Another troupe with the same lead."""
    response = troupe.custodian.client.post(
        "/troupes", json={"name": name, "lead_handle": troupe.lead.handle}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def rename(person: Person, troupe_id: str, name: str) -> None:
    response = person.client.patch(f"/troupes/{troupe_id}", json={"name": name})
    assert response.status_code == 200, response.text


def dated(session: Session, action: str, at: datetime) -> None:
    """Move the events of `action` to `at`: every event in a test is made at once."""
    session.execute(update(AuditEvent).where(AuditEvent.action == action).values(created_at=at))
    session.flush()


def test_only_the_custodian_searches(troupe: Troupe) -> None:
    for person in (troupe.lead, troupe.storyteller, troupe.player, troupe.stranger):
        for url in ("/audit", "/audit/export", "/audit/filters", "/audit/characters"):
            assert person.client.get(url).status_code == 403, url
    assert troupe.custodian.client.get("/audit").status_code == 200


def test_one_persons_changes_across_two_troupes_in_a_date_range(
    troupe: Troupe, session: Session
) -> None:
    other = second_troupe(troupe)
    rename(troupe.lead, troupe.id, "Lords of the Long Night")
    rename(troupe.lead, other, "Court of Cinders")
    troupe.lead.client.put(
        f"/troupes/{other}/staff", json={"handle": troupe.player.handle, "role": "narrator"}
    )
    rename(troupe.custodian, troupe.id, "Lords of the Night Again")
    now = datetime.now(UTC)
    dated(session, "staff.assigned", now - timedelta(days=40))

    found = search(
        troupe.custodian,
        person=troupe.lead.handle,
        since=(now - timedelta(days=1)).isoformat(),
        until=(now + timedelta(days=1)).isoformat(),
    )
    assert [(e["troupe_name"], e["message"]) for e in found["entries"]] == [
        ("Court of Cinders", "lead renamed the troupe to Court of Cinders."),
        ("Lords of the Night Again", "lead renamed the troupe to Lords of the Long Night."),
    ]
    assert {e["troupe_id"] for e in found["entries"]} == {troupe.id, other}
    assert found["next"] is None

    # Without the range, the staff change of 40 days ago too; the handle as typed.
    assert "lead made player narrator." in messages(
        troupe.custodian, person=f"@{troupe.lead.handle.upper()}"
    )
    response = troupe.custodian.client.get("/audit", params={"person": "nobody_at_all"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Nobody has the handle nobody_at_all."


def test_every_event_for_one_character(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)
    bertha = new_character(troupe, troupe.player, "Bertha")
    for character in (agnes, bertha):
        troupe.player.client.post(f"/characters/{character}/troupes", json={"troupe_id": troupe.id})
    troupe.player.client.put(
        f"/characters/{agnes}/traits", json={"category": "skills", "name": "Brawl", "rating": 1}
    )
    other = second_troupe(troupe)
    troupe.player.client.post(f"/characters/{agnes}/troupes", json={"troupe_id": other})

    found = search(troupe.custodian, character_id=agnes)["entries"]
    assert [(e["troupe_name"], e["message"]) for e in found] == [
        ("Court of Ash", "Agnes (player) joined the troupe."),
        (None, "player bought Brawl 1 for Agnes (1 XP)."),
        ("Lords of the Night", "Agnes (player) joined the troupe."),
    ]
    assert {e["character_id"] for e in found} == {agnes}
    assert len(messages(troupe.custodian, character_id=agnes, troupe_id=other)) == 1


def test_groups_and_words(troupe: Troupe) -> None:
    agnes = new_character(troupe, troupe.player)
    troupe.player.client.post(f"/characters/{agnes}/troupes", json={"troupe_id": troupe.id})
    troupe.player.client.put(
        f"/characters/{agnes}/traits", json={"category": "skills", "name": "Brawl", "rating": 2}
    )
    rename(troupe.lead, troupe.id, "Lords of 100% Night")

    assert messages(troupe.custodian, group="sheets") == ["player bought Brawl 2 for Agnes (3 XP)."]
    assert messages(troupe.custodian, group="troupes") == [
        "lead renamed the troupe to Lords of 100% Night.",
        "Agnes (player) joined the troupe.",
    ]
    assert messages(troupe.custodian, group="titles") == []
    assert troupe.custodian.client.get("/audit", params={"group": "nonsense"}).status_code == 422

    # Words of the wording, of what was filled in, and of who: all must be there.
    assert messages(troupe.custodian, q="bought brawl") == [
        "player bought Brawl 2 for Agnes (3 XP)."
    ]
    assert len(messages(troupe.custodian, q="AGNES")) == 2
    assert messages(troupe.custodian, q="renamed lead") == [
        "lead renamed the troupe to Lords of 100% Night."
    ]
    assert messages(troupe.custodian, q="100%") == [
        "lead renamed the troupe to Lords of 100% Night."
    ]
    assert messages(troupe.custodian, q="joined player") == ["Agnes (player) joined the troupe."]
    assert messages(troupe.custodian, q="bought Potence") == []
    assert messages(troupe.custodian, q="%") == ["lead renamed the troupe to Lords of 100% Night."]


def test_pages_newest_first(troupe: Troupe) -> None:
    for name in ("One", "Two", "Three", "Four", "Five"):
        rename(troupe.lead, troupe.id, name)

    pages: list[list[str]] = []
    page: dict[str, Any] = {"person": troupe.lead.handle, "group": "troupes", "limit": 2}
    while True:
        found = search(troupe.custodian, **page)
        pages.append([e["message"].split()[-1] for e in found["entries"]])
        if found["next"] is None:
            break
        page["before"] = found["next"]
    assert pages == [["Five.", "Four."], ["Three.", "Two."], ["One."]]
    response = troupe.custodian.client.get("/audit", params={"before": "not a page"})
    assert response.status_code == 422


def test_export_is_a_csv_of_what_the_filters_find(troupe: Troupe, session: Session) -> None:
    other = second_troupe(troupe)
    rename(troupe.lead, troupe.id, "Lords of the Long Night")
    rename(troupe.lead, other, "Court of Cinders")
    rename(troupe.custodian, troupe.id, "=1+1")

    response = troupe.custodian.client.get(
        "/audit/export", params={"person": troupe.lead.handle, "group": "troupes"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text.removeprefix("\ufeff"))))
    assert rows[0] == ["When (UTC)", "Who", "Troupe", "Character", "Player", "Action", "What"]
    assert [r[1:] for r in rows[1:]] == [
        [
            "lead",
            "Court of Cinders",
            "",
            "",
            "troupe.renamed",
            "lead renamed the troupe to Court of Cinders.",
        ],
        # A troupe named like a formula is not one in a spreadsheet.
        [
            "lead",
            "'=1+1",
            "",
            "",
            "troupe.renamed",
            "lead renamed the troupe to Lords of the Long Night.",
        ],
    ]
    assert datetime.fromisoformat(rows[1][0]).tzinfo is not None

    # The export is logged; searching leaves the log as it was.
    assert messages(troupe.custodian, group="system") == [
        "custodian exported 2 events from the audit log."
    ]
    events = session.scalar(select(func.count()).select_from(AuditEvent))
    troupe.custodian.client.get("/audit", params={"q": "renamed"})
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == events


def test_filters_and_characters_to_pick(troupe: Troupe) -> None:
    other = second_troupe(troupe, "Court of Ash")
    assert troupe.lead.client.delete(f"/troupes/{other}").status_code == 204
    agnes = new_character(troupe, troupe.player)
    troupe.player.client.post(f"/characters/{agnes}/home-troupe", json={"troupe_id": troupe.id})
    new_character(troupe, troupe.stranger, "Agatha")

    choices = troupe.custodian.client.get("/audit/filters").json()
    assert choices["groups"][0] == {"key": "approvals", "label": "Approvals"}
    assert {(t["name"], t["archived"]) for t in choices["troupes"]} == {
        ("Lords of the Night", False),
        ("Court of Ash", True),
    }

    found = troupe.custodian.client.get("/audit/characters", params={"q": "ag"}).json()
    assert [(c["name"], c["player_name"]) for c in found] == [
        ("Agatha", "stranger"),
        ("Agnes", "player"),
    ]
    one = troupe.custodian.client.get("/audit/characters", params={"character_id": agnes}).json()
    assert [c["id"] for c in one] == [agnes]
    assert uuid.UUID(one[0]["id"])


def test_every_action_with_wording_is_in_a_group() -> None:
    for action in [*MESSAGES, "sheet.purchase"]:
        assert any(action.startswith(start) for _, starts in GROUPS.values() for start in starts), (
            action
        )
