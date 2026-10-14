"""Changing a focus after creation costs 10 XP (MET: VTM p. 90)."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from tests.api_helpers import Person, Troupe, new_character


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def with_focus(troupe: Troupe, session: Session, name: str = "Strength", **kw: Any) -> str:
    """A finished character whose Physical focus was picked at creation."""
    character_id = new_character(troupe, troupe.player, **kw)
    definition = session.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(TraitCategory.key == "focus_physicals", TraitDefinition.name == name)
    ).one()
    session.add(
        CharacterTrait(
            character_id=uuid.UUID(character_id),
            trait_definition_id=definition.id,
            rating=1,
            free_rating=1,
            creation_pick=1,
        )
    )
    session.flush()
    return character_id


def change(person: Person, character_id: str, to: str, frm: str = "Strength") -> Any:
    return person.client.post(
        f"/characters/{character_id}/traits/change",
        json={"category": "focus_physicals", "from_name": frm, "to_name": to},
    )


def focuses(person: Person, character_id: str) -> list[tuple[str, int, int]]:
    sheet = person.client.get(f"/characters/{character_id}/sheet").json()
    return [
        (t["name"], t["rating"], t["free_rating"])
        for t in sheet["traits"]
        if t["category"] == "focus_physicals"
    ]


def test_swapping_a_focus_costs_ten_xp(troupe: Troupe, session: Session) -> None:
    character_id = with_focus(troupe, session)

    changed = change(troupe.player, character_id, "Dexterity")

    assert changed.status_code == 200, changed.text
    assert changed.json()["cost"] == 10
    assert changed.json()["sheet"]["xp"]["balance"] == 20
    # The new focus takes the old one's place, still a free starting pick.
    assert focuses(troupe.player, character_id) == [("Dexterity", 1, 1)]
    history = troupe.player.client.get(f"/characters/{character_id}/xp").json()
    assert (history[-1]["kind"], history[-1]["amount"], history[-1]["reason"]) == (
        "fee",
        -10,
        "Changed Physical Focus: Strength → Dexterity",
    )
    log = troupe.player.client.get(f"/characters/{character_id}/log").json()
    assert log[0]["message"] == (
        "player changed Agnes's physical focus: Strength → Dexterity (10 XP)."
    )


def test_a_swap_needs_the_xp_and_a_real_change(troupe: Troupe, session: Session) -> None:
    character_id = with_focus(troupe, session)

    assert change(troupe.player, character_id, "Strength").status_code == 409
    assert change(troupe.player, character_id, "Stamina", frm="Dexterity").status_code == 409
    assert change(troupe.player, character_id, "Juggling").status_code == 422
    for _ in range(3):
        change(troupe.player, character_id, "Dexterity", frm="Strength")
        change(troupe.player, character_id, "Strength", frm="Dexterity")
    # 30 XP pays for three swaps; the fourth is refused, leaving Dexterity.
    assert focuses(troupe.player, character_id) == [("Dexterity", 1, 1)]
    assert (
        troupe.player.client.get(f"/characters/{character_id}/sheet").json()["xp"]["balance"] == 0
    )


def test_only_swappable_categories_and_only_after_creation(
    troupe: Troupe, session: Session
) -> None:
    creating = with_focus(troupe, session, finished=False)
    character_id = with_focus(troupe, session, name="Stamina")

    assert change(troupe.player, creating, "Dexterity").status_code == 409
    clan = troupe.player.client.post(
        f"/characters/{character_id}/traits/change",
        json={"category": "skills", "from_name": "Brawl", "to_name": "Dodge"},
    )
    assert clan.status_code == 409
    assert change(troupe.stranger, character_id, "Dexterity", frm="Stamina").status_code == 404


def test_the_fee_is_not_a_price_difference_when_moving_home(
    troupe: Troupe, session: Session
) -> None:
    character_id = with_focus(troupe, session)
    change(troupe.player, character_id, "Dexterity")

    preview = troupe.player.client.post(
        f"/characters/{character_id}/home-troupe/preview", json={"troupe_id": troupe.id}
    )

    assert preview.json() == []


def test_the_catalogue_says_focuses_cost_ten_to_change(troupe: Troupe) -> None:
    categories = troupe.player.client.get("/rules/vampire").json()["categories"]

    costs = {c["key"]: c["change_cost"] for c in categories}
    assert (costs["focus_physicals"], costs["focus_mentals"], costs["skills"]) == (10, 10, None)
