"""A troupe's fixed price for a merit is its value there: its rating, what it costs,
and what it counts towards the merit limit and the creation points."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe, new_character
from tests.test_api_creation import creation, pick, pool
from tests.test_api_sheets import buy, make_home_troupe_member, sheet

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def talisman_at_2(troupe: Troupe) -> dict[str, Any]:
    """As LOTS plays it: Talisman is a 2-point merit (the book says 3)."""
    response = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/costs",
        json={"category": "merits", "trait": "Talisman", "scheme": "fixed", "rate": 2},
    )
    assert response.status_code == 201, response.text
    return response.json()


def held(character_sheet: dict[str, Any], name: str) -> dict[str, Any]:
    return next(t for t in character_sheet["traits"] if t["name"] == name)


def merit_points(character_sheet: dict[str, Any]) -> int:
    return next(lim["used"] for lim in character_sheet["limits"] if lim["category"] == "merits")


def catalogue_rating(troupe: Troupe, troupe_id: str | None) -> int:
    query = {"category": "merits", **({"troupe_id": troupe_id} if troupe_id else {})}
    traits = troupe.player.client.get("/rules/vampire", params=query).json()["traits"]
    return next(t["fixed_rating"] for t in traits if t["name"] == "Talisman")


def test_the_troupe_price_sets_the_merits_rating(troupe: Troupe, session: Session) -> None:
    talisman_at_2(troupe)
    tremere = new_character(troupe, troupe.player, clan="Tremere")
    make_home_troupe_member(session, troupe, tremere)

    assert buy(troupe.player, tremere, "merits", "Talisman", 3).status_code == 422
    bought = buy(troupe.player, tremere, "merits", "Talisman", 2)

    assert bought.status_code == 200, bought.text
    assert bought.json()["cost"] == 2
    # Asked of staff once accepted (horatio.merit_requests), and approved.
    for request in troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json():
        troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    after = sheet(troupe.player, tremere)
    assert held(after, "Talisman")["rating"] == 2
    assert merit_points(after) == 2
    assert catalogue_rating(troupe, troupe.id) == 2


def test_other_characters_still_play_it_by_the_book(troupe: Troupe) -> None:
    talisman_at_2(troupe)
    tremere = new_character(troupe, troupe.player, clan="Tremere")

    assert buy(troupe.player, tremere, "merits", "Talisman", 3).json()["cost"] == 3
    assert held(sheet(troupe.player, tremere), "Talisman")["rating"] == 3
    assert catalogue_rating(troupe, None) == 3


def test_a_merit_already_held_takes_the_new_value_without_a_refund(
    troupe: Troupe, session: Session
) -> None:
    tremere = new_character(troupe, troupe.player, clan="Tremere")
    make_home_troupe_member(session, troupe, tremere)
    buy(troupe.player, tremere, "merits", "Talisman", 3)
    # Asked of staff once accepted (horatio.merit_requests), and approved.
    for request in troupe.lead.client.get(f"/troupes/{troupe.id}/approvals").json():
        troupe.lead.client.post(f"/approvals/{request['id']}/approve", json={})
    balance = sheet(troupe.player, tremere)["xp"]["balance"]

    price = talisman_at_2(troupe)

    after = sheet(troupe.player, tremere)
    assert held(after, "Talisman")["rating"] == 2
    assert merit_points(after) == 2
    assert after["xp"]["balance"] == balance

    troupe.storyteller.client.delete(f"/troupes/{troupe.id}/costs/{price['id']}")

    assert held(sheet(troupe.player, tremere), "Talisman")["rating"] == 3


def test_a_merit_follows_the_character_to_its_new_rules(troupe: Troupe) -> None:
    talisman_at_2(troupe)
    tremere = new_character(troupe, troupe.player, clan="Tremere")
    buy(troupe.player, tremere, "merits", "Talisman", 3)

    moved = troupe.player.client.put(
        f"/characters/{tremere}/building-troupe", json={"troupe_id": troupe.id}
    )

    assert moved.status_code == 200, moved.text
    assert held(sheet(troupe.player, tremere), "Talisman")["rating"] == 2


def test_creation_points_count_the_troupe_value(troupe: Troupe) -> None:
    talisman_at_2(troupe)
    response = troupe.player.client.post(
        "/characters",
        json={"splat": "vampire", "name": "Agnes", "building_troupe_id": troupe.id},
    )
    character_id = response.json()["id"]
    troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": "clan", "name": "Tremere", "rating": None},
    )

    picked = pick(troupe.player, character_id, "merits", "Talisman")

    assert picked.status_code == 200, picked.text
    assert pool(creation(troupe.player, character_id), "merits", 0)["used"] == 2
    assert held(sheet(troupe.player, character_id), "Talisman")["rating"] == 2


def test_the_value_comes_from_the_price_that_applies(troupe: Troupe, session: Session) -> None:
    """Assamites keep the book's own price for Path of Blood, and so its rating;
    the troupe's price, and value, are for everyone else."""
    troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/costs",
        json={"category": "merits", "trait": "Path of Blood", "scheme": "fixed", "rate": 4},
    )
    troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/checks/merits/Path of Blood/requirement", json={"strength": "off"}
    )
    assamite = new_character(troupe, troupe.player, clan="Assamite")
    brujah = new_character(troupe, troupe.player, "Bram", clan="Brujah")
    make_home_troupe_member(session, troupe, assamite)
    make_home_troupe_member(session, troupe, brujah)

    assert buy(troupe.player, assamite, "merits", "Path of Blood", 3).json()["cost"] == 2
    assert buy(troupe.player, brujah, "merits", "Path of Blood", 3).status_code == 422
    assert buy(troupe.player, brujah, "merits", "Path of Blood", 4).json()["cost"] == 4
