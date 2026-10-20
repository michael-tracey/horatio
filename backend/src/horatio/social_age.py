"""A character's clan and social age, as the troupe's roster and game badges show
them.

Social age is Neonate, Ancilla or Elder. It starts from the Generation background
(MET: VTM's Generation chart: • Neonate, •• Ancilla, and every kind of elder from
••• up), then merits and flaws with a `social_class` property move it: Machiavellian
Prodigy is treated as one social class higher, Accused of Heresy one lower. It
never goes above Elder or below Neonate.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import CharacterTrait, TraitCategory, TraitDefinition

AGES = ("Neonate", "Ancilla", "Elder")


@dataclass(frozen=True)
class Standing:
    clan: str | None
    age: str


def age_for(generation: int, shift: int = 0) -> str:
    """The social age for a Generation rating, moved `shift` classes."""
    start = 0 if generation <= 1 else 1 if generation == 2 else 2
    return AGES[min(max(start + shift, 0), len(AGES) - 1)]


def standings(db: Session, character_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Standing]:
    """Each character's clan and social age, from their sheets as they stand."""
    clan: dict[uuid.UUID, str] = {}
    generation: dict[uuid.UUID, int] = defaultdict(int)
    shift: dict[uuid.UUID, int] = defaultdict(int)
    rows = db.execute(
        select(CharacterTrait, TraitDefinition, TraitCategory.key)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(
            CharacterTrait.character_id.in_(character_ids),
            TraitCategory.key.in_(("clan", "backgrounds", "merits", "flaws")),
        )
    )
    for trait, definition, category in rows:
        if trait.rating == 0:
            continue
        who = trait.character_id
        if category == "clan":
            clan[who] = definition.name
        elif category == "backgrounds":
            if definition.name == "Generation":
                generation[who] = trait.rating or 0
        else:
            shift[who] += int(definition.properties.get("social_class", 0))
    return {c: Standing(clan.get(c), age_for(generation[c], shift[c])) for c in character_ids}
