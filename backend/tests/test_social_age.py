"""Clan and social age on the troupe's roster: Generation, moved by merits and
flaws that change social class (horatio.social_age)."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition
from horatio.social_age import age_for
from tests.api_helpers import Troupe
from tests.test_api_character_search import member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def created(troupe: Troupe, name: str, clan: str, *traits: tuple[str, str, int | None]) -> None:
    """A character of `clan` in the troupe, with `traits` on its sheet."""
    character_id = member(troupe, troupe.player, name, clan)
    for category, trait, rating in traits:
        definition = troupe.session.scalars(
            select(TraitDefinition)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(TraitCategory.key == category, TraitDefinition.name == trait)
        ).one()
        troupe.session.add(
            CharacterTrait(
                character_id=uuid.UUID(character_id),
                trait_definition_id=definition.id,
                rating=rating,
            )
        )
    troupe.session.flush()


@pytest.mark.parametrize(
    ("generation", "shift", "age"),
    [
        (0, 0, "Neonate"),
        (1, 0, "Neonate"),
        (2, 0, "Ancilla"),
        (3, 0, "Elder"),
        (5, 0, "Elder"),
        (1, 1, "Ancilla"),
        (2, 1, "Elder"),
        (3, 1, "Elder"),
        (3, -1, "Ancilla"),
        (1, -1, "Neonate"),
    ],
)
def test_age_from_generation_and_social_class(generation: int, shift: int, age: str) -> None:
    assert age_for(generation, shift) == age


def test_the_roster_shows_clan_and_social_age(troupe: Troupe) -> None:
    created(
        troupe,
        "Agnes",
        "Brujah",
        ("backgrounds", "Generation", 1),
        ("merits", "Machiavellian Prodigy", None),
    )
    created(troupe, "Mara", "Tremere", ("backgrounds", "Generation", 3))
    created(
        troupe,
        "Nell",
        "Giovanni",
        ("backgrounds", "Generation", 2),
        ("flaws", "Accused of Heresy", None),
    )

    roster = troupe.lead.client.get(f"/troupes/{troupe.id}/characters")

    assert roster.status_code == 200, roster.text
    shown = {e["character_name"]: (e["clan"], e["social_age"]) for e in roster.json()}
    assert shown == {
        "Agnes": ("Brujah", "Ancilla"),
        "Mara": ("Tremere", "Elder"),
        "Nell": ("Giovanni", "Neonate"),
    }
