"""Checks on real sheets: clan merits, combinations, prerequisites."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import XpEntry
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
    return new_character(troupe, troupe.player, clan=clan)


def test_clan_merits_are_for_their_clan_and_its_bloodlines(troupe: Troupe) -> None:
    brujah = as_clan(troupe, "Brujah")
    toreador = as_clan(troupe, "Toreador")
    ishtarri = as_clan(troupe, "Toreador: Ishtarri")

    refused = take(troupe.player, brujah, "merits", "Absent Sway", 3)
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("Absent Sway is only for Toreador.")
    assert take(troupe.player, toreador, "merits", "Absent Sway", 3).status_code == 200
    assert take(troupe.player, ishtarri, "merits", "Absent Sway", 3).status_code == 200


def test_the_clan_cannot_change_once_creation_is_finished(troupe: Troupe) -> None:
    character_id = as_clan(troupe, "Toreador")

    refused = take(troupe.player, character_id, "clan", "Brujah", None)

    assert refused.status_code == 409
    assert "can only be chosen during character creation" in refused.json()["detail"]
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
    assert ("Calm Heart", "refuse") in [(p["name"], p["strength"]) for p in problems]


def test_blood_magic_needs_training_or_the_clan(troupe: Troupe) -> None:
    brujah = as_clan(troupe, "Brujah")
    tremere = as_clan(troupe, "Tremere")

    assert (
        take(troupe.player, brujah, "disciplines", "Thaumaturgy: Path of Blood").status_code == 409
    )
    assert (
        take(troupe.player, tremere, "disciplines", "Thaumaturgy: Path of Blood").status_code == 200
    )
    assert (
        take(troupe.player, tremere, "disciplines", "Thaumaturgy: Lure of Flames").status_code
        == 409
    )
    take(
        troupe.player, tremere, "merits", "Thaumaturgic Expertise", 1, "Thaumaturgy: Lure of Flames"
    )
    assert (
        take(troupe.player, tremere, "disciplines", "Thaumaturgy: Lure of Flames").status_code
        == 200
    )


def test_techniques_need_their_prerequisites(troupe: Troupe) -> None:
    character_id = as_clan(troupe, "Brujah")

    refused = take(troupe.player, character_id, "techniques", "Fearful Blow")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Fearful Blow needs Potence 2 and Presence 2. (p. 227)"


def test_rituals_are_bought_at_their_level_with_a_path_that_high(troupe: Troupe) -> None:
    character_id = as_clan(troupe, "Tremere")
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="award",
            amount=100,
            reason="Test",
            entered_by=uuid.UUID(troupe.custodian.id),
        )
    )
    troupe.session.flush()
    take(troupe.player, character_id, "disciplines", "Thaumaturgy: Path of Blood", 1)
    level = 2  # Ritual levels come from the book; pick one level 2 ritual.
    catalogue = troupe.player.client.get("/rules/vampire").json()["traits"]
    ritual = next(
        t["name"]
        for t in catalogue
        if t["category"] == "rituals"
        and t["name"].startswith("Thaumaturgy: ")
        and t["fixed_rating"] == level
    )

    assert take(troupe.player, character_id, "rituals", ritual, 1).status_code == 422
    refused = take(troupe.player, character_id, "rituals", ritual, level)
    assert refused.status_code == 409
    assert "needs a path of Thaumaturgy at 2" in refused.json()["detail"]
    take(troupe.player, character_id, "disciplines", "Thaumaturgy: Path of Blood", 2)
    bought = take(troupe.player, character_id, "rituals", ritual, level)
    assert bought.status_code == 200, bought.text
    assert bought.json()["cost"] == 4


def test_a_path_merit_costs_two_for_its_clan(troupe: Troupe) -> None:
    lasombra = as_clan(troupe, "Lasombra")
    brujah = as_clan(troupe, "Brujah")

    def price(character_id: str) -> int:
        return troupe.player.client.post(
            f"/characters/{character_id}/quote",
            json={"category": "merits", "name": "Path of Night", "rating": 3},
        ).json()["cost"]

    assert (price(lasombra), price(brujah)) == (2, 3)


def test_true_brujah_pay_double_for_morality(troupe: Troupe) -> None:
    true_brujah = as_clan(troupe, "Brujah: True Brujah")

    raised = take(troupe.player, true_brujah, "paths", "Humanity", 6)

    assert raised.json()["cost"] == 20


def test_no_more_rituals_than_thaumaturgy_dots(troupe: Troupe) -> None:
    character_id = as_clan(troupe, "Tremere")
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="award",
            amount=100,
            reason="Test",
            entered_by=uuid.UUID(troupe.custodian.id),
        )
    )
    troupe.session.flush()
    take(troupe.player, character_id, "disciplines", "Thaumaturgy: Path of Blood", 1)
    catalogue = troupe.player.client.get("/rules/vampire").json()["traits"]
    first, second = [
        t["name"]
        for t in catalogue
        if t["category"] == "rituals"
        and t["name"].startswith("Thaumaturgy: ")
        and t["fixed_rating"] == 1
    ][:2]

    assert take(troupe.player, character_id, "rituals", first, 1).status_code == 200
    refused = take(troupe.player, character_id, "rituals", second, 1)
    assert refused.status_code == 409
    assert "no more rituals than their dots" in refused.json()["detail"]
