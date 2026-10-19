"""Awarding a game's XP to the troupe at once (issue #55)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent, XpEntry
from tests.api_helpers import Troupe, new_character, sign_up
from tests.test_api_downtimes import member_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def listed(troupe: Troupe) -> dict[str, Any]:
    response = troupe.assistant.client.get(f"/troupes/{troupe.id}/xp-awards")
    assert response.status_code == 200, response.text
    return response.json()


def award(troupe: Troupe, awards: list[tuple[str, int]], reason: str = "Game, 18 October") -> Any:
    return troupe.assistant.client.post(
        f"/troupes/{troupe.id}/xp-awards",
        json={"reason": reason, "awards": [{"character_id": c, "amount": n} for c, n in awards]},
    )


def awards_for(troupe: Troupe, character_id: str) -> list[tuple[str, int]]:
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    return [(e["reason"], e["amount"]) for e in history if e["reason"].startswith("Game")]


def test_everyone_whose_home_it_is_with_the_usual_amount(
    client_for: Callable[[], TestClient], troupe: Troupe, session: Session
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    other = sign_up(client_for, "other")
    member_character(troupe, other, "Bram")
    new_character(troupe, troupe.player, "Unhomed")
    retired = member_character(troupe, troupe.player, "Cora")
    assert troupe.player.client.post(f"/characters/{retired}/retire").status_code in (200, 204)

    shown = listed(troupe)
    assert shown["session_xp"] == 8
    assert [(c["character_name"], c["player_name"]) for c in shown["characters"]] == [
        ("Agnes", "player"),
        ("Bram", "other"),
    ]
    assert shown["characters"][0]["character_id"] == agnes


def test_award_everyone_at_once(
    client_for: Callable[[], TestClient], troupe: Troupe, session: Session
) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    bram = member_character(troupe, sign_up(client_for, "other"), "Bram")
    cora = member_character(troupe, sign_up(client_for, "third"), "Cora")

    response = award(troupe, [(agnes, 8), (bram, 10), (cora, 0)])
    assert response.status_code == 201, response.text
    assert response.json() == {"characters": 2, "total": 18}
    assert awards_for(troupe, agnes) == [("Game, 18 October", 8)]
    assert (
        session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "xp.award")
        )
        == 2
    )
    # Cora, at 0, got nothing.
    assert (
        session.scalar(
            select(func.count()).select_from(XpEntry).where(XpEntry.reason == "Game, 18 October")
        )
        == 2
    )


def test_all_or_nothing(client_for: Callable[[], TestClient], troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    visitor = new_character(troupe, sign_up(client_for, "visitor"), "Visitor")
    refused = award(troupe, [(agnes, 8), (visitor, 8)])
    assert refused.status_code == 422
    assert awards_for(troupe, agnes) == []
    assert award(troupe, [(agnes, 8), (agnes, 2)]).status_code == 422
    assert award(troupe, [(agnes, 0)]).json()["detail"] == "Nobody would get any XP."
    assert award(troupe, [(agnes, 8)], reason="  ").status_code == 422
    assert award(troupe, [(agnes, -1)]).status_code == 422


def test_only_those_who_award_xp(troupe: Troupe) -> None:
    agnes = member_character(troupe, troupe.player, "Agnes")
    body = {"reason": "Game", "awards": [{"character_id": agnes, "amount": 8}]}
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert person.client.get(f"/troupes/{troupe.id}/xp-awards").status_code == 403
        assert person.client.post(f"/troupes/{troupe.id}/xp-awards", json=body).status_code == 403
    assert (
        troupe.custodian.client.post(f"/troupes/{troupe.id}/xp-awards", json=body).status_code
        == 201
    )
