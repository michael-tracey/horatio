"""Traits that give other traits: health, Willpower, focuses, free dots, higher caps."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(
    person: Person,
    character_id: str,
    category: str,
    name: str,
    rating: int | None = 1,
    detail: str = "",
) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating, "detail": detail},
    )


def sheet(person: Person, character_id: str) -> Any:
    return person.client.get(f"/characters/{character_id}/sheet").json()


def ratings(person: Person, character_id: str, category: str) -> dict[str, Any]:
    return {
        t["name"] + (f": {t['detail']}" if t["detail"] else ""): t["rating"]
        for t in sheet(person, character_id)["traits"]
        if t["category"] == category
    }


def test_rugged_adds_a_health_level_to_each_track_and_takes_it_back(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert take(troupe.player, character_id, "merits", "Rugged", 3).status_code == 200
    health = ratings(troupe.player, character_id, "health_levels")
    assert health == {"Healthy": 4, "Injured": 4, "Incapacitated": 4}
    healthy = next(
        t for t in sheet(troupe.player, character_id)["traits"] if t["name"] == "Healthy"
    )
    assert (healthy["granted_rating"], healthy["granted_by"]) == (1, ["Rugged"])

    take(troupe.player, character_id, "merits", "Rugged", 0)

    assert ratings(troupe.player, character_id, "health_levels") == {
        "Healthy": 3,
        "Injured": 3,
        "Incapacitated": 3,
    }


def test_flaws_can_take_traits_away(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    take(troupe.player, character_id, "flaws", "Low Pain Threshold", 3)
    take(troupe.player, character_id, "flaws", "Short Attention Span", 4)

    assert ratings(troupe.player, character_id, "health_levels") == {
        "Healthy": 3,
        "Injured": 2,
        "Incapacitated": 2,
    }
    assert ratings(troupe.player, character_id, "willpower_sources") == {"Willpower": 5}


def test_unyielding_raises_willpower(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    take(troupe.player, character_id, "merits", "Unyielding", 4)

    assert ratings(troupe.player, character_id, "willpower_sources") == {"Willpower": 7}


def test_a_chosen_grant_needs_its_choice(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Followers of Set")

    refused = take(troupe.player, character_id, "merits", "Personal Cult", 1)

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "Say which for Personal Cult: put Haven, Herd, Resources in its detail."
    )
    catalogue = troupe.player.client.get("/rules/vampire").json()["traits"]
    cult = next(t for t in catalogue if t["name"] == "Personal Cult")
    assert cult["choices"] == ["Haven", "Herd", "Resources"]


def test_free_dots_refund_what_was_bought_and_go_with_the_merit(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Followers of Set")
    take(troupe.player, character_id, "backgrounds", "Resources", 2)  # a Neonate pays 1 + 2
    before = sheet(troupe.player, character_id)["xp"]["balance"]

    taken = take(troupe.player, character_id, "merits", "Personal Cult", 1, "Resources")

    assert taken.status_code == 200, taken.text
    after = sheet(troupe.player, character_id)
    resources = next(t for t in after["traits"] if t["name"] == "Resources")
    assert (resources["rating"], resources["free_rating"], resources["granted_rating"]) == (5, 5, 5)
    # The merit costs 1; the 3 XP paid for Resources comes back.
    assert after["xp"]["balance"] == before - 1 + 3
    # Granted dots cannot be sold back.
    assert take(troupe.player, character_id, "backgrounds", "Resources", 4).status_code == 422

    take(troupe.player, character_id, "merits", "Personal Cult", 0, "Resources")

    assert "Resources" not in ratings(troupe.player, character_id, "backgrounds")
    # Dropping the merit refunds its 1 XP like any merit bought since; the free
    # dots simply go.
    assert sheet(troupe.player, character_id)["xp"]["balance"] == before - 1 + 3 + 1


def test_skills_stop_at_five_unless_a_grant_raises_them(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Toreador")
    troupe.custodian.client.post(
        f"/characters/{character_id}/xp", json={"amount": 100, "reason": "Test"}
    )

    refused = take(troupe.player, character_id, "skills", "Brawl", 6)
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Brawl cannot go above 5."

    take(troupe.player, character_id, "merits", "Artist's Blessing", 1, "Performance: Singing")

    assert ratings(troupe.player, character_id, "skills") == {"Performance: Singing": 3}
    assert (
        take(troupe.player, character_id, "skills", "Performance", 7, "Singing").status_code == 200
    )
    assert (
        take(troupe.player, character_id, "skills", "Performance", 8, "Singing").status_code == 422
    )


def test_one_focus_per_attribute_unless_granted(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Lasombra")
    take(troupe.player, character_id, "focus_socials", "Manipulation")

    refused = take(troupe.player, character_id, "focus_socials", "Appearance")
    assert refused.status_code == 409
    assert "only merits can grant more" in refused.json()["detail"]

    assert take(troupe.player, character_id, "merits", "Angelic Visage", 1).status_code == 200
    assert ratings(troupe.player, character_id, "focus_socials") == {
        "Charisma": 1,
        "Manipulation": 1,
    }


def test_a_chosen_focus(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player, clan="Malkavian")

    take(troupe.player, character_id, "merits", "Expanded Consciousness", 1, "Wits")

    assert ratings(troupe.player, character_id, "focus_mentals") == {"Wits": 1}


def test_npcs_get_their_grants_too(troupe: Troupe) -> None:
    npc = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": "Tough"}
    ).json()["id"]

    troupe.storyteller.client.put(
        f"/characters/{npc}/npc/ratings",
        json={"category": "merits", "name": "Rugged", "rating": 3},
    )

    assert ratings(troupe.storyteller, npc, "health_levels")["Healthy"] == 4
