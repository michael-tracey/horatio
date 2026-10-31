"""Archiving a troupe settles its characters, cycle and games; the custodian lists,
settles and reopens archived troupes (issue #276)."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTitle
from horatio.models import Troupe as TroupeRow
from tests.api_helpers import Person, Troupe, backstory_optional, new_character, sign_up
from tests.test_api_downtimes import member_character, new_cycle, open_cycle
from tests.test_api_play import send, tap


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def summaries(person: Person) -> list[str]:
    return [i["summary"] for i in person.client.get("/notifications").json()["items"]]


def character(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}")
    assert response.status_code == 200, response.text
    return response.json()


class Court:
    """Agnes at home in the troupe, with a game under way and taking part in its open
    cycle; Bertrand, at home in Second City, visiting it; and its NPC, Lucien."""

    def __init__(self, troupe: Troupe) -> None:
        self.troupe = troupe
        self.agnes = member_character(troupe, troupe.player, "Agnes")
        send(troupe.player, self.agnes, tap("blood", -1))
        self.cycle = open_cycle(troupe, new_cycle(troupe))

        self.other = sign_up(troupe.client_for, "other")
        second = troupe.custodian.client.post(
            "/troupes", json={"name": "Second City", "lead_handle": troupe.stranger.handle}
        ).json()["id"]
        backstory_optional(troupe.session, second)
        self.bertrand = new_character(troupe, self.other, "Bertrand")
        asked = self.other.client.post(
            f"/characters/{self.bertrand}/home-troupe", json={"troupe_id": second}
        )
        assert asked.status_code == 201, asked.text
        approved = troupe.stranger.client.post(f"/approvals/{asked.json()['id']}/approve", json={})
        assert approved.status_code == 200, approved.text
        joined = self.other.client.post(
            f"/characters/{self.bertrand}/troupes", json={"troupe_id": troupe.id}
        )
        assert joined.status_code == 201, joined.text

        made = troupe.storyteller.client.post(f"/troupes/{troupe.id}/npcs", json={"name": "Lucien"})
        self.lucien = made.json()["id"]

    def archive(self, by: Person, reason: str = "The chronicle has ended") -> Any:
        return by.client.post(f"/troupes/{self.troupe.id}/archive", json={"reason": reason})


@pytest.fixture
def court(troupe: Troupe) -> Court:
    return Court(troupe)


def test_the_close_down_lists_what_archiving_settles(troupe: Troupe, court: Court) -> None:
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}/closing").status_code == 403

    found = troupe.lead.client.get(f"/troupes/{troupe.id}/closing").json()

    assert [(c["name"], c["player_name"]) for c in found["home"]] == [("Agnes", "player")]
    assert [(c["name"], c["player_name"]) for c in found["visiting"]] == [("Bertrand", "other")]
    assert [(c["name"], c["player_name"]) for c in found["npcs"]] == [("Lucien", "NPC")]
    assert found["cycle"] == "October 2026"
    assert [c["name"] for c in found["games"]] == ["Agnes"]


def test_archiving_settles_characters_cycle_and_games(troupe: Troupe, court: Court) -> None:
    xp_before = troupe.player.client.get(f"/characters/{court.agnes}/sheet").json()["xp"]
    assert court.archive(troupe.storyteller).status_code == 403
    assert court.archive(troupe.lead, reason="  ").status_code == 422

    archived = court.archive(troupe.lead)

    assert archived.status_code == 200, archived.text
    # Agnes has no home troupe now, and keeps her sheet and XP.
    agnes = character(troupe.player, court.agnes)
    assert agnes["home_troupe_id"] is None
    assert agnes["status"] == "active"
    assert troupe.player.client.get(f"/characters/{court.agnes}/troupes").json() == []
    assert troupe.player.client.get(f"/characters/{court.agnes}/sheet").json()["xp"] == xp_before
    # Bertrand's visit has ended; his home is untouched.
    assert [
        t["troupe_name"]
        for t in court.other.client.get(f"/characters/{court.bertrand}/troupes").json()
    ] == ["Second City"]
    # The cycle ended unanswered, and Agnes's game ended and was kept.
    cycle = troupe.custodian.client.get(f"/cycles/{court.cycle['id']}").json()
    assert cycle["status"] == "closed"
    games = troupe.player.client.get(f"/characters/{court.agnes}/play/games").json()
    assert [g["number"] for g in games] == [1]
    # Lucien stays with the troupe.
    assert troupe.custodian.client.get(f"/troupes/{troupe.id}/npcs").status_code == 200
    assert character(troupe.custodian, court.lucien)["owner_troupe_id"] == troupe.id

    # Everyone affected is told, but not whoever archived it.
    assert summaries(troupe.player) == [
        "Lords of the Night is archived (The chronicle has ended): Agnes has no home troupe now,"
        " and can ask another troupe to accept it. Its downtime for October 2026 will not be"
        " answered"
    ]
    assert summaries(court.other) == [
        "Lords of the Night is archived (The chronicle has ended): Bertrand no longer visits it"
    ]
    assert summaries(troupe.narrator) == [
        "lead archived Lords of the Night (The chronicle has ended): 1 character it was home to"
        " has no home troupe now"
    ]
    assert summaries(troupe.lead) == []

    log = [e["message"] for e in troupe.custodian.client.get(f"/troupes/{troupe.id}/log").json()]
    assert log[:4] == [
        "lead archived the troupe (The chronicle has ended).",
        "Bertrand (other)'s visit to Lords of the Night ended as it was archived"
        " (The chronicle has ended).",
        "Agnes (player) left Lords of the Night as it was archived, and has no home troupe now"
        " (The chronicle has ended).",
        "lead ended the downtime cycle October 2026 unanswered, as the troupe was archived.",
    ]
    assert court.archive(troupe.custodian).status_code == 409


def test_the_custodian_lists_archived_troupes_and_reopens_them(
    troupe: Troupe, court: Court
) -> None:
    court.archive(troupe.lead)
    assert troupe.lead.client.get("/troupes/archived").status_code == 403

    [listed] = troupe.custodian.client.get("/troupes/archived").json()

    assert (listed["name"], listed["archived_by_name"], listed["reason"]) == (
        "Lords of the Night",
        "lead",
        "The chronicle has ended",
    )
    assert listed["unsettled"] is False
    assert [(c["name"], c["home"], c["left"]) for c in listed["characters"]] == [
        ("Agnes", True, True),
        ("Bertrand", False, True),
        ("Lucien", True, False),
    ]

    reopen = f"/troupes/{troupe.id}/reopen"
    assert troupe.lead.client.post(reopen, json={"reason": "Back"}).status_code == 403
    assert troupe.custodian.client.post(reopen, json={"reason": ""}).status_code == 422
    reopened = troupe.custodian.client.post(reopen, json={"reason": "Starting again"})

    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["archived"] is False
    assert troupe.custodian.client.get("/troupes/archived").json() == []
    assert [t["name"] for t in troupe.player.client.get("/troupes").json()] == [
        "Lords of the Night",
        "Second City",
    ]
    # Characters do not come back by themselves, but their players are told they can.
    assert character(troupe.player, court.agnes)["home_troupe_id"] is None
    # (In a test, everything happens at once, so the bell's order is not checked.)
    assert (
        "Lords of the Night is open again (Starting again): Agnes can ask it to be its home"
        " troupe once more"
    ) in summaries(troupe.player)
    assert "Lords of the Night is open again (Starting again)" in summaries(troupe.lead)
    assert troupe.custodian.client.post(reopen, json={"reason": "Again"}).status_code == 409


def test_the_custodian_settles_a_troupe_archived_before_archiving_settled_it(
    troupe: Troupe, court: Court, session: Session
) -> None:
    # As troupes archived before #276 were: closed, with nothing settled.
    session.get_one(TroupeRow, uuid.UUID(troupe.id)).archived_at = datetime.now(UTC)
    session.flush()
    [listed] = troupe.custodian.client.get("/troupes/archived").json()
    assert listed["unsettled"] is True
    assert listed["archived_by_name"] is None
    assert [(c["name"], c["home"], c["left"]) for c in listed["characters"]] == [
        ("Agnes", True, False),
        ("Bertrand", False, False),
        ("Lucien", True, False),
    ]

    settle = f"/troupes/{troupe.id}/settle"
    assert troupe.lead.client.post(settle, json={"reason": "Tidy"}).status_code == 403
    settled = troupe.custodian.client.post(settle, json={"reason": "Tidying up"})

    assert settled.status_code == 200, settled.text
    assert character(troupe.player, court.agnes)["home_troupe_id"] is None
    [listed] = troupe.custodian.client.get("/troupes/archived").json()
    assert listed["unsettled"] is False
    assert [(c["name"], c["home"], c["left"]) for c in listed["characters"]] == [
        ("Agnes", True, True),
        ("Bertrand", False, True),
        ("Lucien", True, False),
    ]
    assert any(
        s.startswith("Lords of the Night is archived (Tidying up)")
        for s in summaries(troupe.player)
    )
    assert troupe.custodian.client.post(settle, json={"reason": "Again"}).status_code == 409


def test_titles_end_and_waiting_requests_are_withdrawn(troupe: Troupe, session: Session) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    troupe.assistant.client.post(f"/troupes/{troupe.id}/titles", json={"name": "Gatekeeper"})
    given = troupe.assistant.client.put(
        f"/troupes/{troupe.id}/characters/{agnes}/titles", json={"titles": ["Gatekeeper"]}
    )
    assert given.status_code == 200, given.text
    celeste = new_character(troupe, troupe.player, "Celeste")
    asked = troupe.player.client.post(
        f"/characters/{celeste}/home-troupe", json={"troupe_id": troupe.id}
    )
    assert asked.status_code == 201, asked.text

    troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"})

    assert troupe.player.client.get(f"/characters/{agnes}/sheet").json()["troupes"] == []
    assert session.scalars(select(CharacterTitle.name)).all() == []
    # Celeste's request is withdrawn, so her sheet is no longer held by it.
    assert (
        troupe.player.client.get(f"/characters/{celeste}/sheet").json()["pending_approvals"] == []
    )
    bought = troupe.player.client.put(
        f"/characters/{celeste}/traits", json={"category": "skills", "name": "Brawl", "rating": 1}
    )
    assert bought.status_code == 200, bought.text
