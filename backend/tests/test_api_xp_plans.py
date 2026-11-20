"""A character's plan (horatio.xp_plans): the traits its player means to buy with XP
later, priced as the cart prices them, and its player's own."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_cart import held, spend
from tests.test_api_equipment_passing import npc
from tests.test_api_house_costs import add as add_price
from tests.test_api_house_costs import homed
from tests.test_api_viewing import view_as
from tests.test_api_xp_awards import award

pytestmark = pytest.mark.usefixtures("without_bank")


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def line(category: str, name: str, rating: int, detail: str = "") -> dict[str, Any]:
    return {"category": category, "name": name, "detail": detail, "rating": rating}


def plan_of(person: Person, character_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/xp-plan")


def keep(person: Person, character_id: str, *lines: dict[str, Any], shared: bool = False) -> Any:
    response = person.client.put(
        f"/characters/{character_id}/xp-plan", json={"lines": list(lines), "shared": shared}
    )
    assert response.status_code == 200, response.text
    return response.json()


def as_cart(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"kind": "set", "category": x["category"], "name": x["name"], "rating": x["rating"]}
        for x in lines
    ]


def test_the_plan_prices_each_line_as_the_cart_does(troupe: Troupe, session: Session) -> None:
    # The troupe's own price for attributes; a Brujah at home there, with XP to spend.
    assert add_price(troupe, category="attributes", scheme="per_dot", rate=5).status_code == 201
    character_id = homed(troupe, session, clan="Brujah")
    assert award(troupe, [(character_id, 100)]).status_code < 300
    physical = held(troupe.player, character_id).get("Physical") or 0
    lines = [
        line("disciplines", "Potence", 1),  # in-clan
        line("disciplines", "Dominate", 1),  # out of clan
        line("attributes", "Physical", physical + 1),  # the troupe's price
        line("skills", "Brawl", 1),
        line("skills", "Brawl", 3),  # from where the line before leaves it
    ]

    plan = keep(troupe.player, character_id, *lines)
    dry_run = spend(troupe.player, character_id, *as_cart(lines), dry_run=True)

    assert dry_run.status_code == 200, dry_run.text
    in_cart = [(x["cost"], x["refused"]) for x in dry_run.json()["lines"]]
    in_plan = [(x["cost"], x["refused"]) for x in plan["lines"]]
    assert in_plan == in_cart
    assert [refused for _, refused in in_plan] == [None] * 5
    costs = [cost for cost, _ in in_plan]
    assert costs[0] != costs[1]  # in-clan costs less
    assert costs[2] == 5
    assert costs[4] == 2 + 3
    assert [x["from_rating"] for x in plan["lines"]] == [0, 0, physical, 0, 1]
    # Pricing it bought nothing.
    assert "Brawl" not in held(troupe.player, character_id)
    assert plan["balance"] == dry_run.json()["balance"]


def test_a_plan_is_priced_even_beyond_the_xp_to_pay_for_it(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    plan = keep(
        troupe.player,
        character_id,
        line("skills", "Brawl", 5),
        line("skills", "Dodge", 5),
        line("skills", "Stealth", 5),
    )

    assert plan["balance"] == 30
    assert [(x["cost"], x["refused"]) for x in plan["lines"]] == [(15, None)] * 3
    assert [(x["total"], x["affordable"]) for x in plan["lines"]] == [
        (15, True),
        (30, True),
        (45, False),
    ]
    # No home troupe, so no usual award to say how far off the last is.
    assert (plan["award"], plan["lines"][2]["games"]) == (None, None)
    assert [x["games"] for x in plan["lines"][:2]] == [0, 0]
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert [e["amount"] for e in history] == [30]


def test_games_away_go_by_the_troupes_usual_award(troupe: Troupe, session: Session) -> None:
    character_id = homed(troupe, session)
    lines = [line("skills", "Brawl", 5), line("skills", "Dodge", 5), line("skills", "Stealth", 5)]

    plan = keep(troupe.player, character_id, *lines)

    # The troupe's session XP, 8 a game: 45 is 15 more than her 30, two games' worth.
    assert plan["award"] == {"per_game": 8, "source": "the troupe's session XP"}
    assert [x["games"] for x in plan["lines"]] == [0, 0, 2]

    # A chart gives the figure for a game attended in her band of earned XP.
    record = session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    record.game_xp = {
        "bands": [{"up_to": 100, "attended": 4, "absentee": 1}, {"attended": 2, "absentee": 1}]
    }
    session.flush()

    plan = plan_of(troupe.player, character_id).json()

    assert plan["award"] == {"per_game": 4, "source": "the troupe's chart, 0–100 band"}
    assert [x["games"] for x in plan["lines"]] == [0, 0, 4]


def test_a_line_goes_to_the_cart_only_when_it_can_be_bought(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    plan = keep(
        troupe.player,
        character_id,
        line("skills", "Brawl", 2),
        line("skills", "Brawl", 3),  # not until Brawl is at 2
        line("skills", "Dodge", 5),
        line("skills", "Stealth", 5),  # more than she has, with the lines before it
    )

    assert [x["buyable"] for x in plan["lines"]] == [True, False, True, False]

    # Once bought, a line is done.
    assert spend(troupe.player, character_id, *as_cart([line("skills", "Brawl", 2)])).json()[
        "applied"
    ]
    plan = plan_of(troupe.player, character_id).json()

    first = plan["lines"][0]
    assert (first["held"], first["cost"], first["buyable"]) == (True, None, False)
    assert (plan["lines"][1]["from_rating"], plan["lines"][1]["buyable"]) == (2, True)


def test_a_refused_line_says_why(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    plan = keep(
        troupe.player, character_id, line("flaws", "Archaic", 2), line("skills", "Computer", 1)
    )

    refused = [x["refused"] for x in plan["lines"]]
    assert refused[0] is not None and "Archaic character cannot have Computer" in refused[0]
    assert plan["lines"][0]["buyable"] is False


def test_only_what_xp_buys_goes_in_a_plan(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    url = f"/characters/{character_id}/xp-plan"

    def kept(*lines: dict[str, Any]) -> Any:
        return troupe.player.client.put(url, json={"lines": list(lines)})

    assert kept(line("clan", "Brujah", 1)).status_code == 422
    assert kept(line("skills", "Basket Weaving", 1)).status_code == 422
    assert kept(line("skills", "Brawl", 0)).status_code == 422
    assert kept(*[line("skills", "Brawl", 1)] * 51).status_code == 422
    assert troupe.player.client.get(url).json()["lines"] == []


def test_a_plan_is_its_players_own(troupe: Troupe, session: Session) -> None:
    character_id = homed(troupe, session)
    keep(troupe.player, character_id, line("skills", "Brawl", 1))
    staff = (troupe.lead, troupe.storyteller, troupe.assistant, troupe.custodian)

    # Unshared, only its player sees it, though staff see the sheet.
    for person in staff:
        assert person.client.get(f"/characters/{character_id}/sheet").status_code == 200
        assert plan_of(person, character_id).status_code == 404
    for person in (troupe.narrator, troupe.stranger):
        assert plan_of(person, character_id).status_code == 404
    mine = plan_of(troupe.player, character_id).json()
    assert (mine["mine"], mine["shared"]) == (True, False)

    keep(troupe.player, character_id, line("skills", "Brawl", 1), shared=True)

    # Shared, the staff who see the sheet see it, and only its player changes it.
    for person in staff:
        seen = plan_of(person, character_id)
        assert seen.status_code == 200, seen.text
        assert (seen.json()["mine"], len(seen.json()["lines"])) == (False, 1)
        changed = person.client.put(
            f"/characters/{character_id}/xp-plan", json={"lines": [], "shared": True}
        )
        assert changed.status_code in (403, 404)
    for person in (troupe.narrator, troupe.stranger):
        assert plan_of(person, character_id).status_code == 404
    assert len(plan_of(troupe.player, character_id).json()["lines"]) == 1


def test_viewing_as_the_player_shows_the_plan_unpriced(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    keep(troupe.player, character_id, line("skills", "Brawl", 1))
    view_as(troupe.custodian, troupe.player)

    seen = plan_of(troupe.custodian, character_id)

    assert seen.status_code == 200, seen.text
    assert seen.json()["priced"] is False
    assert seen.json()["lines"][0]["cost"] is None


def test_an_npc_has_no_plan(troupe: Troupe) -> None:
    npc_id = npc(troupe, "Marcus")

    response = troupe.storyteller.client.put(
        f"/characters/{npc_id}/xp-plan", json={"lines": [line("skills", "Brawl", 1)]}
    )

    assert response.status_code == 409
