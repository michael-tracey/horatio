"""Joining troupes and moving to a home troupe, with reconciliation."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent
from horatio.rules.model import CostRuleData
from horatio.rules.store import add_house_rule
from tests.api_helpers import (
    Person,
    Troupe,
    backstory_optional,
    new_character,
    sign_up,
    without_starting_traits,
)

# Balances here are about settlements and purchases, not banking creation XP.
pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def buy(person: Person, character_id: str, category: str, name: str, rating: int | None) -> Any:
    response = person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )
    assert response.status_code == 200, response.text
    return response.json()


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def request_home(
    person: Person,
    character_id: str,
    troupe_id: str,
    settlements: list[dict[str, str]] | None = None,
) -> Any:
    return person.client.post(
        f"/characters/{character_id}/home-troupe",
        json={"troupe_id": troupe_id, "settlements": settlements or [], "note": "Moving to town"},
    )


def queue(person: Person, troupe_id: str) -> list[dict[str, Any]]:
    response = person.client.get(f"/troupes/{troupe_id}/approvals")
    assert response.status_code == 200, response.text
    return response.json()


# Without a Generation background a character counts as Generation 1, whose skills
# the rule set prices on their own; a troupe re-prices them by that same condition.
GEN_1_SKILLS_AT_3 = CostRuleData("skills", "per_dot", rate=3, condition={"generation": 1})


def house_rule(session: Session, troupe: Troupe, rule: CostRuleData) -> None:
    add_house_rule(session, uuid.UUID(troupe.id), "vampire", rule)


def second_troupe(troupe: Troupe) -> str:
    response = troupe.custodian.client.post(
        "/troupes", json={"name": "Second City", "lead_handle": troupe.storyteller.handle}
    )
    assert response.status_code == 201, response.text
    backstory_optional(troupe.session, response.json()["id"])
    return response.json()["id"]


# --- membership -----------------------------------------------------------------------


def test_joining_shares_the_sheet_with_the_troupes_staff(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    assert troupe.assistant.client.get(f"/characters/{character_id}").status_code == 404

    joined = troupe.player.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id}
    )

    assert joined.status_code == 201
    assert troupe.assistant.client.get(f"/characters/{character_id}").status_code == 200
    assert troupe.player.client.get(f"/characters/{character_id}/troupes").json() == [
        {
            "troupe_id": troupe.id,
            "troupe_name": "Lords of the Night",
            "home": False,
        }
    ]

    assert (
        troupe.player.client.delete(f"/characters/{character_id}/troupes/{troupe.id}").status_code
        == 204
    )
    assert troupe.assistant.client.get(f"/characters/{character_id}").status_code == 404


def test_only_the_player_adds_their_character_to_a_troupe(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = troupe.stranger.client.post(
        f"/characters/{character_id}/troupes", json={"troupe_id": troupe.id}
    )

    assert response.status_code == 404


# --- a first home troupe ------------------------------------------------------------------


def test_a_first_home_troupe_with_nothing_to_reconcile(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Brujah")
    buy(troupe.player, character_id, "skills", "Brawl", 2)

    preview = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe/preview", json={"troupe_id": troupe.id}
    )
    assert preview.json() == []
    assert request_home(troupe.player, character_id, troupe.id).status_code == 201

    waiting = queue(troupe.assistant, troupe.id)
    assert [(w["kind"], w["character_name"], w["reconciliation"]) for w in waiting] == [
        ("home_troupe_change", "Agnes", [])
    ]
    decided = troupe.assistant.client.post(f"/approvals/{waiting[0]['id']}/approve", json={})
    assert decided.json()["status"] == "approved"

    character = troupe.player.client.get(f"/characters/{character_id}").json()
    assert character["status"] == "active"
    assert character["home_troupe_id"] == troupe.id
    after = sheet(troupe.player, character_id)
    # Accepting the character as home freezes the sheet as accepted.
    assert [(t["troupe_id"], t["home"]) for t in after["troupes"]] == [(troupe.id, True)]
    brawl = next(t for t in after["traits"] if t["name"] == "Brawl")
    assert brawl["min_rating"] == 2
    assert after["xp"]["balance"] == 27


def test_every_difference_needs_a_settlement(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "skills", "Brawl", 2)  # 1 + 2 = 3 XP under the plain rules
    house_rule(session, troupe, GEN_1_SKILLS_AT_3)

    preview = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe/preview", json={"troupe_id": troupe.id}
    ).json()

    assert preview == [
        {
            "category": "skills",
            "name": "Brawl",
            "detail": "",
            "difference": "cost_differs",
            "rating": 2,
            "old_cost": 3,
            "new_cost": 6,
            "allowed_settlements": ["pay_difference", "keep_price", "remove_and_refund"],
            "pool_rating": None,
            "excess": 0,
            "extra": False,
        }
    ]
    # Not let in with the difference unsettled.
    response = request_home(troupe.player, character_id, troupe.id)
    assert response.status_code == 422
    assert "Brawl" in response.json()["detail"]


def test_paying_the_difference(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "skills", "Brawl", 2)
    house_rule(session, troupe, GEN_1_SKILLS_AT_3)

    response = request_home(
        troupe.player,
        character_id,
        troupe.id,
        [{"category": "skills", "name": "Brawl", "settlement": "pay_difference"}],
    )
    assert response.status_code == 201, response.text
    waiting = queue(troupe.storyteller, troupe.id)[0]
    assert [(r["trait"], r["proposed_settlement"]) for r in waiting["reconciliation"]] == [
        ("Brawl", "pay_difference")
    ]
    troupe.storyteller.client.post(f"/approvals/{waiting['id']}/approve", json={})

    assert sheet(troupe.player, character_id)["xp"]["balance"] == 30 - 3 - 3
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert (history[-1]["kind"], history[-1]["amount"]) == ("settlement", -3)


def test_staff_can_settle_differently_from_the_player(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "skills", "Brawl", 2)
    house_rule(session, troupe, GEN_1_SKILLS_AT_3)
    request_home(
        troupe.player,
        character_id,
        troupe.id,
        [{"category": "skills", "name": "Brawl", "settlement": "keep_price"}],
    )
    waiting = queue(troupe.assistant, troupe.id)[0]

    troupe.assistant.client.post(
        f"/approvals/{waiting['id']}/approve",
        json={
            "settlements": [
                {"item_id": waiting["reconciliation"][0]["id"], "settlement": "pay_difference"}
            ]
        },
    )

    assert sheet(troupe.player, character_id)["xp"]["balance"] == 24
    decided = troupe.assistant.client.get(
        f"/troupes/{troupe.id}/approvals", params={"state": "approved"}
    ).json()[0]
    assert decided["reconciliation"][0]["settlement"] == "pay_difference"


def test_a_banned_trait_is_removed_and_refunded(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "merits", "Acute Sense", 1)
    house_rule(
        session,
        troupe,
        CostRuleData("merits", "not_allowed", trait="Acute Sense", text="Not in this city"),
    )

    preview = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe/preview", json={"troupe_id": troupe.id}
    ).json()
    assert preview[0]["difference"] == "not_allowed"
    assert preview[0]["allowed_settlements"] == ["remove_and_refund", "keep_price"]

    request_home(
        troupe.player,
        character_id,
        troupe.id,
        [{"category": "merits", "name": "Acute Sense", "settlement": "remove_and_refund"}],
    )
    troupe.lead.client.post(f"/approvals/{queue(troupe.lead, troupe.id)[0]['id']}/approve", json={})

    after = sheet(troupe.player, character_id)
    assert without_starting_traits(after["traits"]) == []
    assert after["xp"]["balance"] == 30


def test_settlements_the_character_cannot_afford_are_refused(
    troupe: Troupe, session: Session
) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "attributes", "Physical", 9)  # 27 of 30 XP
    house_rule(session, troupe, CostRuleData("attributes", "per_dot", rate=4))

    response = request_home(
        troupe.player,
        character_id,
        troupe.id,
        [{"category": "attributes", "name": "Physical", "settlement": "pay_difference"}],
    )

    assert response.status_code == 409


def test_the_sheet_is_locked_until_the_request_is_decided_or_withdrawn(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    request_home(troupe.player, character_id, troupe.id)

    locked = troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "skills", "name": "Brawl", "rating": 1},
    )
    assert locked.status_code == 409

    assert troupe.player.client.delete(f"/characters/{character_id}/home-troupe").status_code == 204
    assert queue(troupe.assistant, troupe.id) == []
    buy(troupe.player, character_id, "skills", "Brawl", 1)


def test_a_character_says_which_troupe_it_is_waiting_on(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    def asking() -> list[str | None]:
        return [c["asking_troupe_id"] for c in troupe.player.client.get("/characters").json()]

    assert asking() == [None]
    request_home(troupe.player, character_id, troupe.id)
    assert asking() == [troupe.id]
    one = troupe.player.client.get(f"/characters/{character_id}").json()
    assert one["asking_troupe_id"] == troupe.id
    troupe.player.client.delete(f"/characters/{character_id}/home-troupe")
    assert asking() == [None]


def test_only_the_new_troupes_running_staff_decide(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    other = sign_up(troupe.client_for, "other-lead")
    other_troupe = troupe.custodian.client.post(
        "/troupes", json={"name": "Elsewhere", "lead_handle": other.handle}
    ).json()["id"]
    request_home(troupe.player, character_id, troupe.id)
    approval_id = queue(troupe.lead, troupe.id)[0]["id"]

    for person in (troupe.narrator, troupe.player, other):
        assert person.client.post(f"/approvals/{approval_id}/approve", json={}).status_code == 403
    assert queue(other, other_troupe) == []


def test_declined_requests_leave_the_character_where_it_was(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    request_home(troupe.player, character_id, troupe.id)
    approval_id = queue(troupe.lead, troupe.id)[0]["id"]

    troupe.lead.client.post(f"/approvals/{approval_id}/decline", json={"note": "Full up"})

    character = troupe.player.client.get(f"/characters/{character_id}").json()
    assert character["status"] == "active"
    troupes = troupe.player.client.get(f"/characters/{character_id}/sheet").json()["troupes"]
    # Still in the troupe, as a visitor.
    assert [(t["home"], t["waiting"]) for t in troupes] == [(False, False)]
    assert character["home_troupe_id"] is None


# --- moving between home troupes ------------------------------------------------------------


def make_home(
    troupe: Troupe,
    staff: Person,
    character_id: str,
    troupe_id: str,
    settlements: list[dict[str, str]] | None = None,
) -> None:
    response = request_home(troupe.player, character_id, troupe_id, settlements)
    assert response.status_code == 201, response.text
    approval_id = queue(staff, troupe_id)[0]["id"]
    decided = staff.client.post(f"/approvals/{approval_id}/approve", json={})
    assert decided.status_code == 200, decided.text


def test_moving_home_troupes_reconciles_against_what_was_actually_paid(
    troupe: Troupe, session: Session
) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "skills", "Brawl", 2)  # 3 XP
    house_rule(session, troupe, GEN_1_SKILLS_AT_3)
    make_home(
        troupe,
        troupe.lead,
        character_id,
        troupe.id,
        [{"category": "skills", "name": "Brawl", "settlement": "pay_difference"}],
    )  # now paid 6
    second = second_troupe(troupe)

    preview = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe/preview", json={"troupe_id": second}
    ).json()

    # The plain rules charge 3, and the character has paid 6 in all.
    assert [(p["name"], p["old_cost"], p["new_cost"]) for p in preview] == [("Brawl", 6, 3)]
    make_home(
        troupe,
        troupe.storyteller,
        character_id,
        second,
        [{"category": "skills", "name": "Brawl", "settlement": "refund_difference"}],
    )
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 27
    assert (
        troupe.player.client.get(f"/characters/{character_id}").json()["home_troupe_id"] == second
    )
    moved = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "home_troupe.moved_away")
    ).one()
    assert str(moved.troupe_id) == troupe.id


def test_a_character_in_xp_debt_can_move_but_not_deeper_into_it(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home(troupe, troupe.lead, character_id, troupe.id)
    owed = troupe.lead.client.post(
        f"/characters/{character_id}/xp/debt",
        json={"change": "add", "amount": 40, "reason": "Owed"},
    )
    assert owed.status_code == 200, owed.text
    second = second_troupe(troupe)

    make_home(troupe, troupe.storyteller, character_id, second)

    assert (
        troupe.player.client.get(f"/characters/{character_id}").json()["home_troupe_id"] == second
    )
    # Its 5 banked XP paid some; the new troupe's XP floor may top it up, never down.
    assert sheet(troupe.player, character_id)["xp"]["debt"] <= 40 - 5


def test_requesting_the_current_home_troupe_is_refused(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home(troupe, troupe.lead, character_id, troupe.id)

    assert request_home(troupe.player, character_id, troupe.id).status_code == 409


def test_leaving_the_home_troupe_leaves_no_home_troupe(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home(troupe, troupe.lead, character_id, troupe.id)

    troupe.player.client.delete(f"/characters/{character_id}/troupes/{troupe.id}")

    assert troupe.player.client.get(f"/characters/{character_id}").json()["home_troupe_id"] is None


def test_after_joining_sheet_changes_need_no_approval(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home(troupe, troupe.lead, character_id, troupe.id)

    buy(troupe.player, character_id, "skills", "Dodge", 1)

    assert queue(troupe.assistant, troupe.id) == []
