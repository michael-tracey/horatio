"""A cart of sheet changes, spent together: all of them, or none."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_creation import creating
from tests.test_api_focus_change import with_focus
from tests.test_api_sheets import make_home_troupe_member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def spend(person: Person, character_id: str, *changes: dict[str, Any], dry_run: bool = False):  # noqa: ANN201
    return person.client.post(
        f"/characters/{character_id}/cart", json={"changes": list(changes), "dry_run": dry_run}
    )


def rating(category: str, name: str, to: int | None, **extra: Any) -> dict[str, Any]:
    return {"kind": "set", "category": category, "name": name, "rating": to, **extra}


def sheet(person: Person, character_id: str) -> dict[str, Any]:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def held(person: Person, character_id: str) -> dict[str, int | None]:
    return {t["name"]: t["rating"] for t in sheet(person, character_id)["traits"]}


def lines(response: Any) -> list[tuple[int | None, str | None]]:
    assert response.status_code == 200, response.text
    return [(line["cost"], line["refused"]) for line in response.json()["lines"]]


def test_a_dry_run_prices_the_cart_and_saves_nothing(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = spend(
        troupe.player,
        character_id,
        rating("skills", "Brawl", 1, from_rating=0),
        # Priced from where the line before leaves it: the second dot costs 2.
        rating("skills", "Brawl", 2, from_rating=1),
        rating("skills", "Dodge", 1),
        dry_run=True,
    )

    assert lines(response) == [(1, None), (2, None), (1, None)]
    assert response.json()["applied"] is False
    assert response.json()["balance"] == 30
    assert "Brawl" not in held(troupe.player, character_id)
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 30


def test_spending_makes_every_change_each_with_its_own_xp_entry(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = spend(
        troupe.player,
        character_id,
        rating("skills", "Brawl", 2, from_rating=0),
        rating("skills", "Dodge", 1, from_rating=0),
    )

    assert lines(response) == [(3, None), (1, None)]
    assert response.json()["applied"] is True
    now = held(troupe.player, character_id)
    assert (now["Brawl"], now["Dodge"]) == (2, 1)
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert [(e["reason"], e["amount"]) for e in history if e["kind"] == "purchase"] == [
        ("Brawl 0 → 2", -3),
        ("Dodge 0 → 1", -1),
    ]


def test_one_refusal_and_nothing_is_spent(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = spend(
        troupe.player,
        character_id,
        rating("skills", "Brawl", 1),
        rating("flaws", "Archaic", 2),
        # Checked as if Archaic were already held.
        rating("skills", "Computer", 1),
    )

    assert lines(response) == [
        (1, None),
        (-2, None),
        (1, "An Archaic character cannot have Computer, Drive, Science or Security. (p. 259)"),
    ]
    assert response.json()["applied"] is False
    assert not {"Brawl", "Archaic", "Computer"} & held(troupe.player, character_id).keys()
    assert sheet(troupe.player, character_id)["xp"]["balance"] == 30


def test_the_xp_runs_out_part_way(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    response = spend(
        troupe.player,
        character_id,
        rating("skills", "Brawl", 5),  # 15
        rating("skills", "Dodge", 5),  # 15
        rating("skills", "Melee", 1),
        dry_run=True,
    )

    assert lines(response) == [
        (15, None),
        (15, None),
        (1, "That costs 1 XP, and the character has 0."),
    ]


def test_a_line_made_from_an_older_sheet_is_refused(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    spend(troupe.player, character_id, rating("skills", "Brawl", 2))

    response = spend(troupe.player, character_id, rating("skills", "Brawl", 2, from_rating=1))

    assert lines(response)[0][1] == (
        "Brawl is at 2 now, not 1: the sheet has changed since this went in the cart."
    )


def test_a_swap_in_the_cart_costs_its_change_cost(troupe: Troupe, session: Session) -> None:
    character_id = with_focus(troupe, session)

    response = spend(
        troupe.player,
        character_id,
        {
            "kind": "swap",
            "category": "focus_physicals",
            "from_name": "Strength",
            "to_name": "Dexterity",
        },
    )

    assert lines(response) == [(10, None)]
    assert "Dexterity" in held(troupe.player, character_id)


def test_a_discipline_dot_spent_from_the_cart_waits_for_approval(
    troupe: Troupe, session: Session
) -> None:
    character_id = new_character(troupe, troupe.player, clan="Brujah")
    make_home_troupe_member(session, troupe, character_id)

    response = spend(
        troupe.player,
        character_id,
        rating("skills", "Brawl", 1),
        rating("disciplines", "Celerity", 1, teacher="Marcus"),
    )

    assert [line["needs_approval"] for line in response.json()["lines"]] == [False, True]
    assert [d["name"] for d in sheet(troupe.player, character_id)["pending_disciplines"]] == [
        "Celerity"
    ]


def test_creation_picks_go_through_the_cart_for_nothing(troupe: Troupe) -> None:
    character_id = creating(troupe)
    pick = {"kind": "pick", "category": "skills", "name": "Brawl", "rating": 4}

    assert lines(spend(troupe.player, character_id, pick)) == [(0, None)]
    assert held(troupe.player, character_id)["Brawl"] == 4

    response = spend(
        troupe.player,
        character_id,
        {"kind": "unpick", "category": "skills", "name": "Brawl"},
        {"kind": "pick", "category": "skills", "name": "Dodge", "rating": 4},
    )

    assert lines(response) == [(0, None), (0, None)]
    assert "Brawl" not in held(troupe.player, character_id)
    assert held(troupe.player, character_id)["Dodge"] == 4


def test_a_second_pick_at_the_same_rating_is_refused(troupe: Troupe) -> None:
    character_id = creating(troupe)

    response = spend(
        troupe.player,
        character_id,
        {"kind": "pick", "category": "skills", "name": "Brawl", "rating": 4},
        {"kind": "pick", "category": "skills", "name": "Dodge", "rating": 4},
    )

    assert lines(response)[1] == (0, "Every Skills pick at 4 is already placed.")
    assert "Brawl" not in held(troupe.player, character_id)


def test_only_the_player_spends_their_cart(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)

    assert spend(troupe.storyteller, character_id, rating("skills", "Brawl", 1)).status_code == 403
    assert spend(troupe.stranger, character_id, rating("skills", "Brawl", 1)).status_code == 404
    assert spend(troupe.player, character_id).status_code == 422
