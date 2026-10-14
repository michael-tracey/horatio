"""Character sheets through the API: buying traits, XP, and approval."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import AuditEvent, Character, TroupeMembership, User
from horatio.rules.model import CostRuleData
from horatio.rules.store import add_house_rule
from horatio.sheets import freeze_sheet
from tests.api_helpers import Person, Troupe, new_character, without_starting_traits


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def buy(
    person: Person, character_id: str, category: str, name: str, rating: int | None, **extra: Any
):  # noqa: ANN201
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating, **extra},
    )


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    response = person.client.get(f"/characters/{character_id}/sheet")
    assert response.status_code == 200, response.text
    return response.json()


def make_home_troupe_member(session: Session, troupe: Troupe, character_id: str) -> None:
    """Stand-in for an approved home troupe change, which arrives in a later step."""
    character = session.get_one(Character, uuid.UUID(character_id))
    character.home_troupe_id = uuid.UUID(troupe.id)
    character.creation_completed_at = datetime.now(UTC)
    session.add(TroupeMembership(troupe_id=character.home_troupe_id, character_id=character.id))
    session.flush()
    lead = session.get_one(User, uuid.UUID(troupe.lead.id))
    freeze_sheet(session, lead, character, uuid.UUID(troupe.id))
    session.flush()


# --- buying --------------------------------------------------------------------


def test_new_characters_start_with_30_xp(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert sheet(troupe.player, character_id)["xp"] == {"balance": 30, "earned": 30, "spent": 0}
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert [(e["kind"], e["amount"], e["reason"]) for e in history] == [
        ("award", 30, "Starting experience")
    ]


def test_buying_a_skill(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = buy(troupe.player, character_id, "skills", "Brawl", 2)

    assert response.status_code == 200, response.text
    # No Generation background counts as generation 1, where skills cost 1, 2, 3…
    assert response.json()["cost"] == 3  # 1 + 2
    result = response.json()["sheet"]
    assert result["xp"]["balance"] == 27
    assert [
        (t["name"], t["rating"], t["approved_rating"])
        for t in without_starting_traits(result["traits"])
    ] == [("Brawl", 2, None)]
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert history[-1] == {
        **history[-1],
        "kind": "purchase",
        "amount": -3,
        "trait": "Brawl",
        "from_rating": 0,
        "to_rating": 2,
    }


def test_a_quote_prices_without_buying(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = troupe.player.client.post(
        f"/characters/{character_id}/quote",
        json={"category": "skills", "name": "Brawl", "rating": 3},
    )

    assert response.json()["cost"] == 6  # 1 + 2 + 3 at generation 1
    assert response.json()["basis"]["scheme"] == "progressive"
    assert without_starting_traits(sheet(troupe.player, character_id)["traits"]) == []


def test_you_cannot_spend_xp_you_do_not_have(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    assert buy(troupe.player, character_id, "skills", "Brawl", 5).json()["cost"] == 15

    response = buy(troupe.player, character_id, "attributes", "Physical", 6)  # 18 XP

    assert response.status_code == 409
    assert "has 15" in response.json()["detail"]
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 15


def test_merits_cost_their_point_value_and_flaws_give_xp(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert buy(troupe.player, character_id, "merits", "Acute Sense", 3).status_code == 422
    assert buy(troupe.player, character_id, "merits", "Acute Sense", 1).json()["cost"] == 1
    flaw = buy(troupe.player, character_id, "flaws", "Amnesia", 1)

    assert flaw.status_code == 200, flaw.text
    assert flaw.json()["cost"] < 0
    assert flaw.json()["sheet"]["xp"]["balance"] == 30 - 1 - flaw.json()["cost"]


def test_choosing_a_clan_replaces_the_last_choice_and_costs_nothing(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    buy(troupe.player, character_id, "clan", "Brujah", None)
    response = buy(troupe.player, character_id, "clan", "Tremere", None)

    assert response.json()["cost"] == 0
    assert [t["name"] for t in without_starting_traits(response.json()["sheet"]["traits"])] == [
        "Tremere"
    ]


def test_the_clan_sets_in_clan_discipline_prices(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "clan", "Brujah", None)

    in_clan = buy(troupe.player, character_id, "disciplines", "Celerity", 2)
    out_of_clan = troupe.player.client.post(
        f"/characters/{character_id}/quote",
        json={"category": "disciplines", "name": "Dominate", "rating": 2},
    )

    assert in_clan.json()["cost"] == 9  # 3 + 6
    assert out_of_clan.json()["cost"] == 12  # 4 + 8


def test_only_catalogue_traits_can_be_bought(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert buy(troupe.player, character_id, "skills", "Juggling", 1).status_code == 422
    assert buy(troupe.player, character_id, "clan", "Brujah", 2).status_code == 422
    assert buy(troupe.player, character_id, "skills", "Brawl", None).status_code == 422


def test_unapproved_purchases_can_be_undone_for_a_refund(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "skills", "Brawl", 3)

    response = buy(troupe.player, character_id, "skills", "Brawl", 1)

    assert response.json()["cost"] == -5  # gives back dots 2 and 3
    assert response.json()["sheet"]["xp"]["balance"] == 29
    response = buy(troupe.player, character_id, "skills", "Brawl", 0)
    assert without_starting_traits(response.json()["sheet"]["traits"]) == []
    assert response.json()["sheet"]["xp"]["balance"] == 30


def test_purchases_use_the_home_troupes_house_rules(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)
    add_house_rule(
        session, uuid.UUID(troupe.id), "vampire", CostRuleData("skills", "per_dot", rate=1)
    )

    assert buy(troupe.player, character_id, "skills", "Brawl", 3).json()["cost"] == 3


def test_purchases_are_audited(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "skills", "Brawl", 1)

    event = session.scalars(select(AuditEvent).where(AuditEvent.action == "sheet.purchase")).one()
    assert event.data["name"] == "Brawl"
    assert event.data["cost"] == 1


# --- who sees and changes what ----------------------------------------------------


def test_sheets_are_private_from_other_players_and_narrators(
    troupe: Troupe, session: Session
) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)

    assert troupe.stranger.client.get(f"/characters/{character_id}/sheet").status_code == 404
    assert troupe.narrator.client.get(f"/characters/{character_id}/sheet").status_code == 404
    assert troupe.assistant.client.get(f"/characters/{character_id}/sheet").status_code == 200


def test_staff_cannot_edit_a_players_sheet(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)

    assert buy(troupe.storyteller, character_id, "skills", "Brawl", 1).status_code == 403


def test_home_troupe_running_staff_award_xp(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    award = {"amount": 5, "reason": "Attended October game"}
    assert troupe.assistant.client.post(
        f"/characters/{character_id}/xp", json=award
    ).status_code in (
        404,
        409,
    )
    make_home_troupe_member(session, troupe, character_id)

    for person in (troupe.narrator, troupe.player, troupe.stranger):
        assert person.client.post(f"/characters/{character_id}/xp", json=award).status_code in (
            403,
            404,
        )
    response = troupe.assistant.client.post(f"/characters/{character_id}/xp", json=award)

    assert response.status_code == 201
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 35


# --- approval ----------------------------------------------------------------------


def test_a_character_in_no_troupe_has_nobody_to_ask(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    buy(troupe.player, character_id, "skills", "Brawl", 1)

    assert (
        troupe.player.client.post(f"/characters/{character_id}/approval", json={}).status_code
        == 409
    )


def test_approving_a_sheet_change(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)
    buy(troupe.player, character_id, "skills", "Brawl", 2)

    request = troupe.player.client.post(
        f"/characters/{character_id}/approval", json={"note": "Trained with the Sheriff"}
    )
    assert request.status_code == 201, request.text

    # Locked while waiting.
    assert buy(troupe.player, character_id, "skills", "Dodge", 1).status_code == 409
    # The queue, which narrators cannot see.
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}/approvals").status_code == 403
    queue = troupe.assistant.client.get(f"/troupes/{troupe.id}/approvals").json()
    assert [(q["character_name"], q["player_note"]) for q in queue] == [
        ("Agnes", "Trained with the Sheriff")
    ]
    assert [(c["name"], c["approved_rating"], c["rating"]) for c in queue[0]["changes"]] == [
        ("Brawl", None, 2)
    ]

    decided = troupe.assistant.client.post(
        f"/approvals/{queue[0]['id']}/approve", json={"note": "Welcome"}
    )

    assert decided.json()["status"] == "approved"
    after = sheet(troupe.player, character_id)
    assert after["pending_changes"] == []
    assert after["pending_approvals"] == []
    assert without_starting_traits(after["traits"])[0]["approved_rating"] == 2
    # Approved dots cannot be taken back by the player.
    assert buy(troupe.player, character_id, "skills", "Brawl", 1).status_code == 409
    assert buy(troupe.player, character_id, "skills", "Brawl", 3).status_code == 200


def test_declining_unlocks_the_sheet(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)
    buy(troupe.player, character_id, "skills", "Brawl", 2)
    approval_id = troupe.player.client.post(f"/characters/{character_id}/approval", json={}).json()[
        0
    ]["id"]

    decided = troupe.storyteller.client.post(
        f"/approvals/{approval_id}/decline", json={"note": "Not in one month"}
    )

    assert decided.json()["status"] == "declined"
    assert decided.json()["staff_note"] == "Not in one month"
    assert buy(troupe.player, character_id, "skills", "Brawl", 1).status_code == 200
    assert (
        troupe.storyteller.client.post(f"/approvals/{approval_id}/approve", json={}).status_code
        == 409
    )


def test_withdrawing_a_request(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)
    buy(troupe.player, character_id, "skills", "Brawl", 2)
    troupe.player.client.post(f"/characters/{character_id}/approval", json={})

    assert troupe.player.client.delete(f"/characters/{character_id}/approval").status_code == 204
    assert troupe.assistant.client.get(f"/troupes/{troupe.id}/approvals").json() == []
    assert buy(troupe.player, character_id, "skills", "Brawl", 1).status_code == 200


def test_nothing_to_approve(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)

    assert (
        troupe.player.client.post(f"/characters/{character_id}/approval", json={}).status_code
        == 409
    )


# --- the catalogue -------------------------------------------------------------------


def test_the_catalogue_lists_traits_with_house_rule_text(troupe: Troupe, session: Session) -> None:
    add_house_rule(
        session,
        uuid.UUID(troupe.id),
        "vampire",
        CostRuleData("merits", "fixed", rate=4, trait="Acute Sense", text="Rare in our city"),
    )

    plain = troupe.player.client.get("/rules/vampire", params={"category": "merits"}).json()
    ours = troupe.player.client.get(
        "/rules/vampire", params={"category": "merits", "troupe_id": troupe.id}
    ).json()

    acute = next(t for t in plain["traits"] if t["name"] == "Acute Sense")
    assert acute["fixed_rating"] == 1
    assert acute["house_rule"] is None
    assert next(t for t in ours["traits"] if t["name"] == "Acute Sense")["house_rule"] == (
        "Rare in our city"
    )
    assert {c["key"] for c in plain["categories"]} >= {"clan", "skills", "merits"}


def test_the_catalogue_says_which_attribute_a_skill_goes_with(troupe: Troupe) -> None:
    skills = troupe.player.client.get("/rules/vampire", params={"category": "skills"}).json()

    attributes = {t["name"]: t["attribute"] for t in skills["traits"]}
    assert (attributes["Brawl"], attributes["Empathy"], attributes["Occult"]) == (
        "Physical",
        "Social",
        "Mental",
    )
    assert None not in attributes.values()
