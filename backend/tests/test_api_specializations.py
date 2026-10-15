"""Specialisations: troupe lists, one per dot, filling in a missing field, and
building a character by a troupe's rules."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from horatio.rules.model import CostRuleData
from horatio.rules.store import add_house_rule
from tests.api_helpers import Person, Troupe, finish, new_character

ELITE = "influence_elite_specializations"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def take(
    person: Person, character_id: str, category: str, name: str, rating: int = 1, detail: str = ""
) -> Any:
    return person.client.put(
        f"/characters/{character_id}/traits",
        json={"category": category, "name": name, "rating": rating, "detail": detail},
    )


def built_for(troupe: Troupe) -> str:
    response = troupe.player.client.post(
        "/characters",
        json={"splat": "vampire", "name": "Agnes", "building_troupe_id": troupe.id},
    )
    assert response.status_code == 201, response.text
    assert response.json()["building_troupe_id"] == troupe.id
    character_id: str = response.json()["id"]

    finish(troupe, character_id)
    return character_id


def test_a_troupe_sets_its_own_list_and_its_characters_choose_from_it(troupe: Troupe) -> None:
    path = f"/troupes/{troupe.id}/specializations/{ELITE}"
    assert troupe.assistant.client.put(path, json={"names": ["Police"]}).status_code == 403

    listed = troupe.storyteller.client.put(path, json={"names": ["Police", "Finance", "Police"]})

    elite = next(k for k in listed.json() if k["category"] == ELITE)
    assert elite["troupe"] == ["Finance", "Police"]
    character_id = built_for(troupe)
    take(troupe.player, character_id, "backgrounds", "Influences: The Elite", 2)
    kinds = troupe.player.client.get(f"/characters/{character_id}/specializations").json()
    mine = next(k for k in kinds if k["category"] == ELITE)
    assert (mine["options"], mine["from_troupe"], mine["custom"]) == (
        ["Finance", "Police"],
        True,
        False,
    )

    assert take(troupe.player, character_id, ELITE, "Custom", 1, "Police").status_code == 200
    refused = take(troupe.player, character_id, ELITE, "Banks")
    assert refused.status_code == 409
    assert refused.json()["detail"] == "This troupe's Influence: Elite are: Finance, Police."


def test_without_a_troupe_list_the_catalogue_and_free_text_apply(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    take(troupe.player, character_id, "backgrounds", "Contacts", 1)

    assert (
        take(troupe.player, character_id, "contacts_specializations", "Custom").status_code == 422
    )
    named = take(troupe.player, character_id, "contacts_specializations", "Custom", 1, "Bethany")
    assert named.status_code == 200, named.text
    second = take(troupe.player, character_id, "contacts_specializations", "Custom", 1, "Carlos")
    assert second.status_code == 409
    assert second.json()["detail"] == "Each dot of Contacts gives one contact. (p. 99)"


def test_a_missing_field_can_be_filled_in(troupe: Troupe, session: Session) -> None:
    character_id = new_character(troupe, troupe.player)
    crafts = session.scalars(select_definition("skills", "Crafts")).one()
    session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id), trait_definition_id=crafts.id, rating=1
        )
    )
    session.flush()
    assert any(
        "need a field" in p["message"]
        for p in troupe.player.client.get(f"/characters/{character_id}/sheet").json()["problems"]
    )

    filled = troupe.player.client.put(
        f"/characters/{character_id}/traits/detail",
        json={"category": "skills", "name": "Crafts", "detail": "Pottery"},
    )

    assert filled.status_code == 200, filled.text
    sheet = filled.json()
    assert ("Crafts", "Pottery") in [(t["name"], t["detail"]) for t in sheet["traits"]]
    assert not any("need a field" in p["message"] for p in sheet["problems"])


def test_building_for_a_troupe_uses_its_house_rules(troupe: Troupe, session: Session) -> None:
    add_house_rule(
        session,
        uuid.UUID(troupe.id),
        "vampire",
        CostRuleData(category="merits", trait="Rugged", scheme="fixed", rate=2),
    )
    plain = new_character(troupe, troupe.player)
    built = built_for(troupe)

    def price(character_id: str) -> int:
        return troupe.player.client.post(
            f"/characters/{character_id}/quote",
            json={"category": "merits", "name": "Rugged", "rating": 3},
        ).json()["cost"]

    assert (price(plain), price(built)) == (3, 2)
    # Building for the troupe, asking it to be home finds nothing to reconcile.
    preview = troupe.player.client.post(
        f"/characters/{built}/home-troupe/preview", json={"troupe_id": troupe.id}
    )
    assert preview.json() == []


def test_the_build_troupe_can_change_until_a_home_troupe_accepts(troupe: Troupe) -> None:
    character_id = new_character(troupe, troupe.player)
    path = f"/characters/{character_id}/building-troupe"

    assert (
        troupe.player.client.put(path, json={"troupe_id": troupe.id}).json()["building_troupe_id"]
        == troupe.id
    )
    assert (
        troupe.player.client.put(path, json={"troupe_id": None}).json()["building_troupe_id"]
        is None
    )
    assert troupe.stranger.client.put(path, json={"troupe_id": troupe.id}).status_code == 404


def select_definition(category: str, name: str) -> Any:
    from sqlalchemy import select

    return (
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == category, TraitDefinition.name == name)
    )
