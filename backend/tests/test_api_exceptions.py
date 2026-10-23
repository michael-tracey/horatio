"""Exceptions: a player asks staff for a trait the rules refuse, at cost or free;
staff give one free or despite the rules; the sheet stops flagging the rule an
exception covers, and only that one."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitDefinition, TraitException, XpEntry
from tests.api_helpers import Person, Troupe
from tests.test_api_house_checks import accepted_brujah, house

pytestmark = pytest.mark.usefixtures("without_bank")

REFUSED = "Brujah cannot take Calm Heart (True Brujah can). (p. 249)"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def calm_heart(reason: str = "Raised among the True Brujah", free: bool = False) -> dict[str, Any]:
    return {
        "kind": "set",
        "category": "merits",
        "name": "Calm Heart",
        "rating": 1,
        "from_rating": 0,
        "exception": {"reason": reason, "free": free},
    }


def spend(person: Person, character_id: str, *changes: dict[str, Any], dry_run: bool = False):  # noqa: ANN201
    return person.client.post(
        f"/characters/{character_id}/cart", json={"changes": list(changes), "dry_run": dry_run}
    )


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def waiting(troupe: Troupe, **query: str) -> list[dict[str, Any]]:
    response = troupe.lead.client.get(f"/troupes/{troupe.id}/approvals", params=query)
    assert response.status_code == 200, response.text
    return response.json()


def give(person: Person, character_id: str, **body: Any):  # noqa: ANN201
    return person.client.post(
        f"/characters/{character_id}/give",
        json={"category": "merits", "name": "Calm Heart", "rating": 1, **body},
    )


def history(person: Person, character_id: str) -> list[dict[str, Any]]:
    return person.client.get(f"/characters/{character_id}/xp").json()


def test_a_refused_trait_is_asked_for_and_approved(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]
    # Without asking, the rules refuse it.
    plain = {k: v for k, v in calm_heart().items() if k != "exception"}
    assert spend(troupe.player, character_id, plain).json()["lines"][0]["refused"] == REFUSED

    priced = spend(troupe.player, character_id, calm_heart(), dry_run=True).json()
    [line] = priced["lines"]
    assert (line["refused"], line["needs_approval"], line["breaks"]) == (None, True, [REFUSED])
    cost = line["cost"]
    assert cost > 0

    spent = spend(troupe.player, character_id, calm_heart())

    assert spent.json()["applied"] is True, spent.text
    after = sheet(troupe.player, character_id)
    held = next(t for t in after["traits"] if t["name"] == "Calm Heart")
    assert held["pending_from"] == 0
    assert after["xp"]["balance"] == before - cost
    assert REFUSED not in [p["message"] for p in after["problems"]]
    [exception] = after["exceptions"]
    assert (exception["status"], exception["breaks"], exception["free"]) == (
        "waiting",
        [REFUSED],
        False,
    )

    [request] = waiting(troupe, kind="exception")
    assert waiting(troupe, kind="discipline") == []
    assert request["exception"] == {
        "breaks": [REFUSED],
        "reason": "Raised among the True Brujah",
        "free": False,
        "normal_cost": cost,
    }
    approved = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    assert approved.status_code == 200, approved.text

    after = sheet(troupe.player, character_id)
    [exception] = after["exceptions"]
    assert (exception["status"], exception["by"]) == ("approved", "lead")
    assert exception["at"] is not None
    assert REFUSED not in [p["message"] for p in after["problems"]]
    assert after["xp"]["balance"] == before - cost


def test_a_free_ask_costs_nothing_and_approving_at_normal_cost_charges_it(
    troupe: Troupe,
) -> None:
    character_id = accepted_brujah(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    spent = spend(troupe.player, character_id, calm_heart("A plot reward", free=True))

    assert spent.json()["lines"][0]["cost"] == 0, spent.text
    after = sheet(troupe.player, character_id)
    assert after["xp"]["balance"] == before
    held = next(t for t in after["traits"] if t["name"] == "Calm Heart")
    assert (held["rating"], held["free_rating"]) == (1, 1)
    line = history(troupe.player, character_id)[-1]
    assert (line["amount"], line["reason"]) == (
        0,
        "Calm Heart 0 → 1, free by exception: A plot reward",
    )

    [request] = waiting(troupe)
    assert request["exception"]["free"] is True
    normal = request["exception"]["normal_cost"]
    assert normal > 0
    approved = troupe.lead.client.post(
        f"/approvals/{request['id']}/approve", json={"at_cost": True}
    )
    assert approved.status_code == 200, approved.text

    after = sheet(troupe.player, character_id)
    assert after["xp"]["balance"] == before - normal
    held = next(t for t in after["traits"] if t["name"] == "Calm Heart")
    assert held["free_rating"] == 0
    assert after["exceptions"][0]["free"] is False


def test_approving_at_normal_cost_is_refused_without_the_xp(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    spend(troupe.player, character_id, calm_heart("A plot reward", free=True))
    balance = sheet(troupe.player, character_id)["xp"]["balance"]
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="fee",
            amount=-balance,
            reason="Spent elsewhere",
            entered_by=uuid.UUID(troupe.player.id),
        )
    )
    troupe.session.flush()
    [request] = waiting(troupe)

    refused = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={"at_cost": True})

    assert refused.status_code == 409
    assert "and Agnes has 0" in refused.json()["detail"]
    # Approving it free still can.
    approved = troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    assert approved.status_code == 200, approved.text


def test_declining_takes_it_back_and_refunds(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]
    spend(troupe.player, character_id, calm_heart())
    [request] = waiting(troupe)

    troupe.lead.client.post(f"/approvals/{request['id']}/decline", json={})

    after = sheet(troupe.player, character_id)
    assert "Calm Heart" not in [t["name"] for t in after["traits"]]
    assert after["xp"]["balance"] == before
    assert after["exceptions"] == []
    assert troupe.session.scalars(select(TraitException)).all() == []


def test_storytellers_give_a_trait_free_and_despite_the_rules(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    before = sheet(troupe.player, character_id)["xp"]["balance"]
    for person in (troupe.player, troupe.narrator):
        assert give(person, character_id, free=True, reason="Plot").status_code in (403, 404)

    trial = give(troupe.storyteller, character_id, free=True, reason="Plot", trial=True).json()
    assert (trial["given"], trial["cost"], trial["breaks"]) == (False, 0, [REFUSED])
    assert trial["refused"] == REFUSED
    # Not despite the rules, it is refused.
    assert give(troupe.storyteller, character_id, free=True, reason="Plot").status_code == 409

    given = give(
        troupe.assistant,
        character_id,
        free=True,
        despite=True,
        reason="A gift from the Prince",
    )

    assert given.status_code == 200, given.text
    assert (given.json()["given"], given.json()["breaks"]) == (True, [REFUSED])
    after = sheet(troupe.player, character_id)
    assert after["xp"]["balance"] == before
    assert REFUSED not in [p["message"] for p in after["problems"]]
    [exception] = after["exceptions"]
    assert (exception["status"], exception["by"], exception["free"]) == ("given", "assistant", True)
    assert exception["reason"] == "A gift from the Prince"
    # No approval waits, a 0 XP line says why, and the player is told.
    assert waiting(troupe) == []
    line = history(troupe.player, character_id)[-1]
    assert (line["amount"], line["reason"]) == (
        0,
        "Calm Heart 0 → 1, free by exception: A gift from the Prince",
    )
    told = troupe.player.client.get("/notifications").json()["items"]
    assert any(
        n["summary"] == "assistant gave Agnes Calm Heart 1, free: A gift from the Prince"
        for n in told
    )
    # The player cannot take it away again for XP.
    removed = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "merits", "name": "Calm Heart", "rating": 0},
    )
    assert removed.status_code in (409, 422)


def test_an_excepted_rule_is_not_flagged_while_another_is(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    give(troupe.storyteller, character_id, despite=True, reason="Ruling")
    checks = troupe.lead.client.get(f"/troupes/{troupe.id}/checks").json()
    ritual_master = next(c["key"] for c in checks if c["message"].startswith("Ritual Master is"))
    house(troupe, troupe.storyteller, ritual_master, "note")
    bought = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "merits", "name": "Ritual Master", "rating": 1},
    )
    assert bought.status_code == 200, bought.text

    problems = [p["name"] for p in sheet(troupe.player, character_id)["problems"]]

    assert "Ritual Master" in problems
    assert "Calm Heart" not in problems


def test_the_exception_goes_with_the_trait(troupe: Troupe) -> None:
    character_id = accepted_brujah(troupe)
    give(troupe.storyteller, character_id, despite=True, reason="Ruling")
    definition = troupe.session.scalars(
        select(TraitDefinition).where(TraitDefinition.name == "Calm Heart")
    ).first()
    assert definition is not None
    trait = troupe.session.scalars(
        select(CharacterTrait).where(
            CharacterTrait.character_id == uuid.UUID(character_id),
            CharacterTrait.trait_definition_id == definition.id,
        )
    ).one()

    troupe.session.delete(trait)
    troupe.session.flush()
    troupe.session.expire_all()

    assert troupe.session.scalars(select(TraitException)).all() == []
    # Taken again, the rule refuses it as before.
    again = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "merits", "name": "Calm Heart", "rating": 1},
    )
    assert again.status_code == 409


def test_an_exception_covers_only_up_to_the_rating_given(troupe: Troupe) -> None:
    """Raising a trait above the rating it was given at is judged as normal."""
    character_id = accepted_brujah(troupe)
    give(troupe.storyteller, character_id, despite=True, reason="Ruling")
    exception = troupe.session.scalars(select(TraitException)).one()
    assert REFUSED not in [p["message"] for p in sheet(troupe.player, character_id)["problems"]]

    exception.rating = 0
    troupe.session.flush()

    assert REFUSED in [p["message"] for p in sheet(troupe.player, character_id)["problems"]]
