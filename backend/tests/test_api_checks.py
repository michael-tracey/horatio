"""Checks on real sheets: clan merits, combinations, prerequisites."""

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


def as_clan(troupe: Troupe, clan: str) -> str:
    character_id = new_character(troupe, troupe.player)
    assert take(troupe.player, character_id, "clan", clan, None).status_code == 200
    return character_id


def test_clan_merits_are_for_their_clan_and_its_bloodlines(troupe: Troupe) -> None:
    brujah = as_clan(troupe, "Brujah")
    toreador = as_clan(troupe, "Toreador")
    ishtarri = as_clan(troupe, "Toreador: Ishtarri")

    refused = take(troupe.player, brujah, "merits", "Absent Sway", 3)
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("Absent Sway is only for Toreador.")
    assert take(troupe.player, toreador, "merits", "Absent Sway", 3).status_code == 200
    assert take(troupe.player, ishtarri, "merits", "Absent Sway", 3).status_code == 200


def test_changing_clan_cannot_strand_a_clan_merit(troupe: Troupe) -> None:
    character_id = as_clan(troupe, "Toreador")
    take(troupe.player, character_id, "merits", "Absent Sway", 3)

    assert take(troupe.player, character_id, "clan", "Brujah", None).status_code == 409
    sheet = troupe.player.client.get(f"/characters/{character_id}/sheet").json()
    assert next(t["name"] for t in sheet["traits"] if t["category"] == "clan") == "Toreador"


def test_barred_by_clan_but_not_by_bloodline(troupe: Troupe) -> None:
    brujah = as_clan(troupe, "Brujah")
    true_brujah = as_clan(troupe, "Brujah: True Brujah")

    assert take(troupe.player, brujah, "merits", "Calm Heart").status_code == 409
    assert take(troupe.player, true_brujah, "merits", "Calm Heart").status_code == 200
    assert take(troupe.player, true_brujah, "skills", "Empathy").status_code == 409


def test_combinations_are_refused_whichever_comes_first(troupe: Troupe) -> None:
    flaw_first = new_character(troupe, troupe.player)
    skill_first = new_character(troupe, troupe.player)

    take(troupe.player, flaw_first, "flaws", "Archaic", 2)
    refused = take(troupe.player, flaw_first, "skills", "Computer")
    take(troupe.player, skill_first, "skills", "Computer")

    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "An Archaic character cannot have Computer, Drive, Science or Security. (p. 259)"
    )
    assert take(troupe.player, skill_first, "flaws", "Archaic", 2).status_code == 409


def test_prerequisites(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)

    assert take(troupe.player, character_id, "merits", "Szlachta", 2).status_code == 409


def test_unavailable_choices_come_with_reasons(troupe: Troupe) -> None:
    character_id = as_clan(troupe, "Brujah")

    found = troupe.player.client.get(
        f"/characters/{character_id}/unavailable", params={"category": "merits"}
    ).json()

    assert found["Absent Sway"].startswith("Absent Sway is only for Toreador.")
    assert found["Calm Heart"].startswith("Brujah cannot take Calm Heart")
    assert "Acute Sense" not in found
    assert "Brotherhood" not in found


def test_npcs_are_built_freely_but_problems_show(troupe: Troupe) -> None:
    npc = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/npcs", json={"name": "Odd One"}
    ).json()["id"]

    def rate(category: str, name: str, rating: int | None) -> int:
        return troupe.storyteller.client.put(
            f"/characters/{npc}/npc/ratings",
            json={"category": category, "name": name, "rating": rating},
        ).status_code

    assert rate("clan", "Brujah", None) == 200
    assert rate("merits", "Calm Heart", 1) == 200

    problems = troupe.storyteller.client.get(f"/characters/{npc}/sheet").json()["problems"]
    assert [(p["name"], p["strength"]) for p in problems] == [("Calm Heart", "refuse")]
