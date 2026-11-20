"""A character's plan (horatio.xp_plans): the traits its player means to buy with XP
later, priced as the cart prices them, and its player's own."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import DowntimeCycle, ScheduledGame
from horatio.models import Troupe as TroupeRecord
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_bond_fading import retire
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


def keep(
    person: Person,
    character_id: str,
    *lines: dict[str, Any],
    shared: bool = False,
    cart: list[dict[str, Any]] | None = None,
) -> Any:
    response = person.client.put(
        f"/characters/{character_id}/xp-plan",
        json={"lines": list(lines), "shared": shared, "cart": cart or []},
    )
    assert response.status_code == 200, response.text
    return response.json()


def priced_after(person: Person, character_id: str, cart: list[dict[str, Any]]) -> Any:
    response = person.client.post(f"/characters/{character_id}/xp-plan/price", json={"cart": cart})
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

    # The troupe's session XP, 8 a game, and with no games held yet, its 2 XP for a
    # downtime, a cycle a game: 45 is 15 more than her 30, two games' worth.
    assert plan["award"] == {
        "per_game": 8,
        "source": "the troupe's session XP",
        "downtime": 2,
        "downtime_source": "the troupe's 2 XP a downtime, counting a cycle a game",
    }
    assert [x["games"] for x in plan["lines"]] == [0, 0, 2]

    # A chart gives the figure for a game attended in her band of earned XP.
    record = session.get_one(TroupeRecord, uuid.UUID(troupe.id))
    record.game_xp = {
        "bands": [{"up_to": 100, "attended": 4, "absentee": 1}, {"attended": 2, "absentee": 1}]
    }
    session.flush()

    plan = plan_of(troupe.player, character_id).json()

    assert plan["award"]["per_game"] == 4
    assert plan["award"]["source"] == "the troupe's chart, 0–100 band"
    assert [x["games"] for x in plan["lines"]] == [0, 0, 3]  # 15 at 4 + 2 a game


def test_games_away_count_the_downtime_xp_the_troupes_cycles_give(
    troupe: Troupe, session: Session
) -> None:
    character_id = homed(troupe, session)
    troupe_id = uuid.UUID(troupe.id)
    now = datetime.now(UTC)
    # In the last year, four games and two cycles of 3 XP for completing each; an older
    # cycle and a game still to come don't count.
    for days_ago in (300, 200, 100, 10, -7):
        starts = now - timedelta(days=days_ago)
        session.add(
            ScheduledGame(
                troupe_id=troupe_id, starts_at=starts, ends_at=starts + timedelta(hours=4)
            )
        )
    for days_ago, xp in ((250, 3), (60, 3), (400, 10)):
        opened = now - timedelta(days=days_ago)
        session.add(
            DowntimeCycle(
                troupe_id=troupe_id,
                name=f"Cycle {days_ago}",
                status="closed",
                opened_at=opened,
                closes_at=opened + timedelta(days=14),
                grace_ends_at=opened + timedelta(days=16),
                closed_at=opened + timedelta(days=16),
                completion_xp=xp,
            )
        )
    session.flush()

    plan = keep(
        troupe.player,
        character_id,
        line("skills", "Brawl", 5),
        line("skills", "Dodge", 5),
        line("skills", "Stealth", 5),
        line("skills", "Melee", 5),
    )

    # 6 XP over 4 games is 1.5 a game, so 9.5 a game in all.
    assert plan["award"] == {
        "per_game": 8,
        "source": "the troupe's session XP",
        "downtime": 1.5,
        "downtime_source": "6 XP from 2 downtime cycles over 4 games in the last year",
    }
    # Her 30 pays for two; the others are 15 and 30 short: 1.6 and 3.2 games.
    assert [x["games"] for x in plan["lines"]] == [0, 0, 2, 4]

    # Capped at the monthly 10, the downtime's 1.5 counts toward it: 8 of a game's XP fits.
    record = session.get_one(TroupeRecord, troupe_id)
    record.game_xp = {"cap": "cap"}
    session.flush()
    assert plan_of(troupe.player, character_id).json()["award"]["per_game"] == 8
    record.game_xp = {"cap": "cap", "monthly_xp": 6}
    session.flush()
    assert plan_of(troupe.player, character_id).json()["award"]["per_game"] == 4

    # Games but no downtime XP: none is counted.
    for cycle in session.query(DowntimeCycle).filter_by(troupe_id=troupe_id):
        cycle.completion_xp = 0
    record.game_xp = {}
    session.flush()
    award = plan_of(troupe.player, character_id).json()["award"]
    assert (award["downtime"], award["downtime_source"]) == (0, None)


def test_the_plan_is_priced_after_what_is_in_the_cart(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    cart = [{"kind": "set", "category": "skills", "name": "Brawl", "rating": 2, "from_rating": 0}]
    lines = [line("skills", "Brawl", 2), line("skills", "Brawl", 4), line("skills", "Dodge", 4)]

    alone = keep(troupe.player, character_id, *lines)
    after = priced_after(troupe.player, character_id, cart)

    # Alone, Brawl to 2 costs 3 and to 4 then 7 more; with Brawl 2 in the cart, the
    # first is the cart's already, and the second raises from 2.
    assert [(x["from_rating"], x["cost"]) for x in alone["lines"]] == [(0, 3), (2, 7), (0, 10)]
    assert [(x["from_rating"], x["cost"]) for x in after["lines"]] == [
        (2, None),
        (2, 7),
        (0, 10),
    ]
    assert [(x["held"], x["in_cart"]) for x in after["lines"]] == [
        (True, True),
        (False, False),
        (False, False),
    ]
    # The cart's 3 comes first: of her 30, 27 is left, for 7 then 17 in all.
    assert (after["balance"], after["cart_cost"]) == (30, 3)
    assert [(x["total"], x["affordable"], x["buyable"]) for x in after["lines"]] == [
        (0, False, False),
        (7, True, True),
        (17, True, True),
    ]
    # The same as a cart dry run of the cart and the plan's lines after it.
    dry_run = spend(
        troupe.player,
        character_id,
        *cart,
        *as_cart(lines[1:]),
        dry_run=True,
    ).json()
    assert [x["cost"] for x in dry_run["lines"]] == [3, 7, 10]
    # Saving it with the cart prices it the same; pricing bought nothing.
    assert keep(troupe.player, character_id, *lines, cart=cart)["lines"] == after["lines"]
    assert "Brawl" not in held(troupe.player, character_id)

    # A cart line the sheet has moved on from is refused, and spends nothing.
    stale = [{**cart[0], "from_rating": 1}]
    assert priced_after(troupe.player, character_id, stale)["cart_cost"] == 0
    assert priced_after(troupe.player, character_id, stale)["lines"] == alone["lines"]


def test_the_cart_spending_the_xp_leaves_the_plan_short(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    cart = [{"kind": "set", "category": "skills", "name": "Dodge", "rating": 5}]

    plan = keep(troupe.player, character_id, line("skills", "Brawl", 5), cart=cart)

    # Dodge 5 takes 15 of her 30; Brawl 5's 15 still fits, but not a second time.
    assert plan["cart_cost"] == 15
    assert plan["lines"][0]["affordable"] is True
    cart.append({"kind": "set", "category": "skills", "name": "Stealth", "rating": 5})
    plan = priced_after(troupe.player, character_id, cart)
    assert plan["cart_cost"] == 30
    assert (plan["lines"][0]["affordable"], plan["lines"][0]["buyable"]) == (False, False)


def test_a_retired_characters_plan_stays_as_it_was(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    keep(troupe.player, character_id, line("skills", "Brawl", 1), shared=True)
    retire(troupe.player, character_id, "inactive")

    changed = troupe.player.client.put(
        f"/characters/{character_id}/xp-plan", json={"lines": [], "shared": False}
    )
    seen = plan_of(troupe.player, character_id)

    assert changed.status_code == 409, changed.text
    assert changed.json()["detail"] == "This character is retired."
    assert seen.status_code == 200, seen.text
    plan = seen.json()
    assert (plan["priced"], plan["shared"]) == (False, True)
    assert [(x["name"], x["cost"], x["buyable"]) for x in plan["lines"]] == [("Brawl", None, False)]


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
