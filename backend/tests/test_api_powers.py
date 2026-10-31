"""What a character can take among its powers: Generation's say over techniques and
elder powers (MET: VTM p. 101), rituals, and the list as the cart would leave it."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition, XpEntry
from tests.api_helpers import Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(troupe: Troupe, character_id: str, category: str, name: str, rating: int = 1) -> Any:
    return troupe.player.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating},
    )


def set_generation(session: Session, character_id: str, generation: int) -> None:
    """Generation as picked at creation, or as staff later correct it."""
    definition = session.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == "backgrounds", TraitDefinition.name == "Generation")
    ).one()
    held = session.scalars(
        select(CharacterTrait).where(
            CharacterTrait.character_id == uuid.UUID(character_id),
            CharacterTrait.trait_definition_id == definition.id,
        )
    ).one_or_none()
    if held is None:
        held = CharacterTrait(
            character_id=uuid.UUID(character_id), trait_definition_id=definition.id
        )
        session.add(held)
    held.rating = held.free_rating = held.creation_pick = generation
    session.flush()


def vampire(troupe: Troupe, clan: str, generation: int, *traits: tuple[str, str, int]) -> str:
    """A finished vampire of `clan` and `generation`, with XP to spare, holding `traits`."""
    character_id = new_character(troupe, troupe.player, clan=clan)
    troupe.session.add(
        XpEntry(
            character_id=uuid.UUID(character_id),
            kind="award",
            amount=1000,
            reason="Test",
            entered_by=uuid.UUID(troupe.custodian.id),
        )
    )
    set_generation(troupe.session, character_id, generation)
    for category, name, rating in traits:
        taken = take(troupe, character_id, category, name, rating)
        assert taken.status_code == 200, taken.text
    return character_id


def unavailable(
    troupe: Troupe, character_id: str, category: str, changes: list[dict[str, Any]] | None = None
) -> dict[str, str]:
    response = troupe.player.client.post(
        f"/characters/{character_id}/unavailable",
        json={"categories": [category], "changes": changes or []},
    )
    assert response.status_code == 200, response.text
    return response.json()[category]


def catalogue(troupe: Troupe, category: str) -> list[dict[str, Any]]:
    traits = troupe.player.client.get("/rules/vampire").json()["traits"]
    return [t for t in traits if t["category"] == category]


ELDER = "Celerity: Projectile"
OTHER_ELDER = "Celerity: Quickness"
CELERITY_5 = ("disciplines", "Celerity", 5)


def test_neonates_and_ancillae_learn_no_elder_powers(troupe: Troupe) -> None:
    ancilla = vampire(troupe, "Brujah", 2, CELERITY_5)

    # Its price refuses it first; the check says why.
    assert take(troupe, ancilla, "elder_disciplines", ELDER).status_code == 422
    assert unavailable(troupe, ancilla, "elder_disciplines")[ELDER] == (
        "A Neonate's or Ancilla's blood is too thin for elder powers. (p. 101)"
    )


def test_a_pretender_elder_learns_techniques_at_20_and_one_elder_power(troupe: Troupe) -> None:
    pretender = vampire(troupe, "Brujah", 3, CELERITY_5, ("disciplines", "Potence", 2))
    technique = take(troupe, pretender, "techniques", "Fearful Blow")
    assert technique.status_code == 409  # Presence 2 too
    take(troupe, pretender, "disciplines", "Presence", 2)

    technique = take(troupe, pretender, "techniques", "Fearful Blow")
    assert technique.status_code == 200, technique.text
    assert technique.json()["cost"] == 20
    elder = take(troupe, pretender, "elder_disciplines", ELDER)
    assert elder.status_code == 200, elder.text
    assert elder.json()["cost"] == 18  # in-clan
    assert unavailable(troupe, pretender, "elder_disciplines")[OTHER_ELDER] == (
        "A Pretender Elder can learn only one elder power. (p. 101)"
    )


def test_master_elders_learn_no_techniques(troupe: Troupe) -> None:
    master = vampire(
        troupe,
        "Brujah",
        4,
        CELERITY_5,
        ("disciplines", "Potence", 2),
        ("disciplines", "Presence", 2),
    )

    assert take(troupe, master, "techniques", "Fearful Blow").status_code == 422
    techniques = unavailable(troupe, master, "techniques")
    assert techniques["Fearful Blow"] == (
        "A Master or Luminary Elder cannot learn techniques. (p. 101)"
    )
    assert len(techniques) == len(catalogue(troupe, "techniques"))
    assert take(troupe, master, "elder_disciplines", ELDER).status_code == 200
    assert take(troupe, master, "elder_disciplines", OTHER_ELDER).status_code == 200


def test_a_technique_held_when_generation_rises_shows_as_a_problem(
    troupe: Troupe, session: Session
) -> None:
    pretender = vampire(
        troupe,
        "Brujah",
        3,
        ("disciplines", "Potence", 2),
        ("disciplines", "Presence", 2),
        ("techniques", "Fearful Blow", 1),
    )
    # Staff correct the Generation to 4.
    set_generation(session, pretender, 4)

    problems = troupe.player.client.get(f"/characters/{pretender}/sheet").json()["problems"]
    assert ("Fearful Blow", "refuse") in [(p["name"], p["strength"]) for p in problems]


def test_what_costs_rule_out_is_unavailable_too(troupe: Troupe) -> None:
    luminary = vampire(troupe, "Brujah", 5)

    found = unavailable(troupe, luminary, "luminary_disciplines")
    names = [t["name"] for t in catalogue(troupe, "luminary_disciplines")]
    in_clan = next(n for n in names if n.startswith("Celerity: "))
    out_of_clan = next(n for n in names if n.startswith("Dominate: "))
    assert in_clan not in found
    assert found[out_of_clan] == (
        "Luminary Disciplines can be bought only in-clan, Generation background 5 or more."
    )


def test_the_cart_opens_what_it_brings_the_prerequisites_for(troupe: Troupe) -> None:
    character_id = vampire(
        troupe, "Brujah", 1, ("disciplines", "Potence", 1), ("disciplines", "Presence", 1)
    )
    assert "Fearful Blow" in unavailable(troupe, character_id, "techniques")

    raises = [
        {"kind": "set", "category": "disciplines", "name": name, "rating": 2, "from_rating": 1}
        for name in ("Potence", "Presence")
    ]
    assert "Fearful Blow" not in unavailable(troupe, character_id, "techniques", raises)
    # A technique in the cart counts as held, so it is not offered again.
    technique = {"kind": "set", "category": "techniques", "name": "Fearful Blow", "rating": 1}
    planned = unavailable(troupe, character_id, "techniques", [technique, *raises])
    assert "Fearful Blow" not in planned
    lowered = {"kind": "set", "category": "disciplines", "name": "Potence", "rating": 0}
    assert "Fearful Blow" in unavailable(troupe, character_id, "techniques", [lowered])


def test_several_categories_at_once_and_unknown_ones_refused(troupe: Troupe) -> None:
    character_id = vampire(troupe, "Brujah", 1)

    both = troupe.player.client.post(
        f"/characters/{character_id}/unavailable",
        json={"categories": ["techniques", "elder_disciplines"]},
    )
    assert set(both.json()) == {"techniques", "elder_disciplines"}
    unknown = troupe.player.client.post(
        f"/characters/{character_id}/unavailable", json={"categories": ["spells"]}
    )
    assert unknown.status_code == 404
    stranger = troupe.stranger.client.post(
        f"/characters/{character_id}/unavailable", json={"categories": ["techniques"]}
    )
    assert stranger.status_code in (403, 404)


def rituals_open(troupe: Troupe, character_id: str) -> list[str]:
    """Rituals the character could take next."""
    barred = unavailable(troupe, character_id, "rituals")
    sheet = troupe.player.client.get(f"/characters/{character_id}/sheet").json()["traits"]
    held = {t["name"] for t in sheet if t["category"] == "rituals"}
    return [
        t["name"]
        for t in catalogue(troupe, "rituals")
        if t["name"] not in barred and t["name"] not in held
    ]


def test_rituals_open_to_a_thaumaturge_by_level(troupe: Troupe) -> None:
    tremere = vampire(troupe, "Tremere", 1, ("disciplines", "Thaumaturgy: Path of Blood", 2))
    levels = {t["name"]: t["fixed_rating"] for t in catalogue(troupe, "rituals")}

    open_ = rituals_open(troupe, tremere)
    assert open_
    assert all(n.startswith("Thaumaturgy: ") and levels[n] <= 2 for n in open_)
    assert rituals_open(troupe, vampire(troupe, "Brujah", 1)) == []


def test_sorcerous_dabbler_opens_low_thaumaturgy_rituals_without_the_discipline(
    troupe: Troupe,
) -> None:
    dabbler = vampire(troupe, "Brujah", 1, ("merits", "Sorcerous Dabbler", 2))
    levels = {t["name"]: t["fixed_rating"] for t in catalogue(troupe, "rituals")}
    first, second, third, fourth = [
        n for n, level in levels.items() if n.startswith("Thaumaturgy: ") and level == 1
    ][:4]
    level_two = next(
        n for n, level in levels.items() if n.startswith("Thaumaturgy: ") and level == 2
    )

    open_ = rituals_open(troupe, dabbler)
    assert {levels[n] for n in open_} == {1, 2}
    for ritual in (first, second, third):
        assert take(troupe, dabbler, "rituals", ritual, 1).status_code == 200
    assert take(troupe, dabbler, "rituals", fourth, 1).status_code == 409
    assert rituals_open(troupe, dabbler) == []
    assert take(troupe, dabbler, "rituals", first, 0).status_code == 200
    # Two level 1 and a level 2 would be more than the merit opens.
    assert take(troupe, dabbler, "rituals", level_two, 2).status_code == 409


def test_memento_mori_opens_necromancy_rituals_by_dementation(troupe: Troupe) -> None:
    ananke = vampire(
        troupe,
        "Malkavian: Ananke",
        1,
        ("disciplines", "Dementation", 1),
        ("merits", "Memento Mori", 2),
    )
    levels = {t["name"]: t["fixed_rating"] for t in catalogue(troupe, "rituals")}

    open_ = rituals_open(troupe, ananke)
    assert open_
    assert all(n.startswith("Necromancy: ") and levels[n] == 1 for n in open_)
    assert take(troupe, ananke, "rituals", open_[0], 1).status_code == 200
    assert rituals_open(troupe, ananke) == []
