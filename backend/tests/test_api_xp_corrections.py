"""Correcting a mistaken XP award (issue #56): the award stays as written, and a
correction entry makes up the difference."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_sheets import buy, make_home_troupe_member, sheet


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def homed(troupe: Troupe, session: Session) -> str:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)
    return character_id


def award(troupe: Troupe, character_id: str, amount: int, reason: str = "October game") -> str:
    response = troupe.storyteller.client.post(
        f"/characters/{character_id}/xp", json={"amount": amount, "reason": reason}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def correct(person: Person, character_id: str, entry_id: str, amount: int) -> Any:
    return person.client.post(
        f"/characters/{character_id}/xp/{entry_id}/correction",
        json={"amount": amount, "reason": "Typo: meant 3"},
    )


def xp(person: Person, character_id: str) -> dict[str, int]:
    return sheet(person, character_id)["xp"]


def history(person: Person, character_id: str) -> list[dict[str, Any]]:
    return person.client.get(f"/characters/{character_id}/xp").json()


def test_a_correction_leaves_the_award_and_adds_the_difference(
    troupe: Troupe, homed: str, session: Session
) -> None:
    entry = award(troupe, homed, 30)
    assert xp(troupe.player, homed)["balance"] == 60

    response = correct(troupe.assistant, homed, entry, 3)
    assert response.status_code == 201, response.text
    assert response.json()["amount"] == -27
    assert response.json()["kind"] == "correction"

    assert xp(troupe.player, homed) == {"balance": 33, "earned": 33, "spent": 0, "unbanked": 0}
    lines = history(troupe.player, homed)
    original = next(e for e in lines if e["id"] == entry)
    assert (original["amount"], original["corrected_to"]) == (30, 3)
    assert lines[-1]["corrects_id"] == entry
    assert lines[-1]["reason"] == "Typo: meant 3"

    # Corrected again, from what it gives now; 0 cancels it.
    assert correct(troupe.lead, homed, entry, 0).json()["amount"] == -3
    assert xp(troupe.player, homed)["balance"] == 30

    [event] = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "xp.corrected").order_by(AuditEvent.id)
    ).all()[:1]
    assert (event.data["was"], event.data["now"]) == (30, 3)


def test_who_may_correct(troupe: Troupe, homed: str) -> None:
    entry = award(troupe, homed, 5)
    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert correct(person, homed, entry, 3).status_code in (403, 404)
    assert [e["correctable"] for e in history(troupe.player, homed)] == [False, False]
    assert [e["correctable"] for e in history(troupe.storyteller, homed)] == [True, True]
    assert correct(troupe.custodian, homed, entry, 4).status_code == 201


def test_only_awards_and_only_real_changes(troupe: Troupe, homed: str) -> None:
    entry = award(troupe, homed, 5)
    assert correct(troupe.storyteller, homed, entry, 5).status_code == 422
    buy(troupe.player, homed, "skills", "Brawl", 1)
    purchase = history(troupe.player, homed)[-1]
    assert purchase["kind"] == "purchase"
    assert purchase["correctable"] is False
    assert correct(troupe.storyteller, homed, purchase["id"], 0).status_code == 422


def test_spent_xp_cannot_be_taken_back(troupe: Troupe, homed: str) -> None:
    entry = award(troupe, homed, 10)  # 30 starting + 10
    for skill in ("Brawl", "Occult", "Dodge"):
        bought = buy(troupe.player, homed, "skills", skill, 3)  # 1 + 2 + 3 each
        assert bought.status_code == 200, bought.text
    assert xp(troupe.player, homed)["balance"] == 22
    for skill in ("Awareness", "Stealth", "Survival"):
        assert buy(troupe.player, homed, "skills", skill, 3).status_code == 200
    assert xp(troupe.player, homed)["balance"] == 4

    refused = correct(troupe.storyteller, homed, entry, 0)
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Agnes has only 4 XP unspent, so this award can come down by at most 4."
    )
    assert correct(troupe.storyteller, homed, entry, 6).status_code == 201
    assert xp(troupe.player, homed)["balance"] == 0
