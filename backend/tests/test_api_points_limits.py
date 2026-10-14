"""Seven points of merits for life; flaws pay at most 7 XP (MET: VTM pp. 106, 235)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.rules.model import CostRuleData
from horatio.rules.store import add_house_rule
from tests.api_helpers import Person, Troupe, new_character
from tests.test_api_sheets import make_home_troupe_member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(person: Person, character_id: str, category: str, name: str, rating: int) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )


def sheet(person: Person, character_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def limits(person: Person, character_id: str) -> dict[str, tuple[int, int]]:
    found = sheet(person, character_id)["limits"]
    return {item["category"]: (item["used"], item["limit"]) for item in found}


def test_a_character_never_holds_more_than_seven_merit_points(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    take(troupe.player, character_id, "merits", "Abyssal Horror", 3)
    take(troupe.player, character_id, "merits", "Rugged", 3)
    assert take(troupe.player, character_id, "merits", "Acute Sense", 1).status_code == 200

    refused = take(troupe.player, character_id, "merits", "Adaptive", 1)

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "That would bring merits to 8 points; a character can hold at most 7."
    )
    assert limits(troupe.player, character_id)["merits"] == (7, 7)
    # Dropping one makes room again.
    take(troupe.player, character_id, "merits", "Acute Sense", 0)
    assert take(troupe.player, character_id, "merits", "Adaptive", 1).status_code == 200


def test_merit_points_count_at_the_troupes_price(troupe: Troupe, session: Session) -> None:
    add_house_rule(
        session,
        uuid.UUID(troupe.id),
        "vampire",
        CostRuleData(category="merits", trait="Rugged", scheme="fixed", rate=2),
    )
    character_id = new_character(troupe, troupe.player)
    make_home_troupe_member(session, troupe, character_id)
    take(troupe.player, character_id, "merits", "Abyssal Horror", 3)
    take(troupe.player, character_id, "merits", "Rugged", 3)  # 2 here

    assert take(troupe.player, character_id, "merits", "Acute Sense", 1).status_code == 200
    assert take(troupe.player, character_id, "merits", "Adaptive", 1).status_code == 200
    assert limits(troupe.player, character_id)["merits"] == (7, 7)


def test_flaws_pay_at_most_seven_xp(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    first = take(troupe.player, character_id, "flaws", "Blood Rot", 5)
    second = take(troupe.player, character_id, "flaws", "Dark Fate", 5)
    third = take(troupe.player, character_id, "flaws", "Amnesia", 1)

    assert [r.json()["cost"] for r in (first, second, third)] == [-5, -2, 0]
    assert sheet(troupe.player, character_id)["xp"]["balance"] == before + 7
    assert limits(troupe.player, character_id)["flaws"] == (11, 7)


def test_the_quote_shows_the_capped_payout(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    take(troupe.player, character_id, "flaws", "Blood Rot", 5)

    quote = troupe.player.client.post(
        f"/characters/{character_id}/quote",
        json={"category": "flaws", "name": "Dark Fate", "rating": 5},
    )

    assert quote.json()["cost"] == -2


def test_the_catalogue_states_the_limits(troupe: Troupe) -> None:
    categories = troupe.player.client.get("/rules/vampire").json()["categories"]

    found = {c["key"]: c["points_limit"] for c in categories}
    assert (found["merits"], found["flaws"], found["skills"]) == (7, 7, None)
