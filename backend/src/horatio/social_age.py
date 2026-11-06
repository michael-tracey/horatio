"""A character's clan and social age, as the troupe's roster and game badges show
them.

Social age is Neonate, Ancilla or Elder. It starts from the Generation background
(MET: VTM's Generation chart: • Neonate, •• Ancilla, and every kind of elder from
••• up), then merits and flaws with a `social_class` property move it: Machiavellian
Prodigy is treated as one social class higher, Accused of Heresy one lower. It
never goes above Elder or below Neonate.

A splat without Generation (horatio.rules.splats) has no social age: a ghoul is
no Neonate. Its splat's name stands in its place, "Ghoul", so the roster and
badges say what it is beside its domitor's clan. So with an NPC of a kind that is
not a vampire (horatio.rules.npc_kinds): a mortal or a werewolf is no Neonate
either, and its kind's name, "Mortal", stands in its place.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import Character, CharacterTrait, TraitCategory, TraitDefinition
from horatio.rules.npc_kinds import npc_kinds
from horatio.rules.splats import SPLATS

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
    splats: dict[uuid.UUID, str] = {}
    # What an NPC that is not a vampire is, in place of a social age.
    kinds: dict[uuid.UUID, str] = {}
    for who, splat, kind_key, custom in db.execute(
        select(Character.id, Character.splat, Character.npc_kind, Character.npc_custom_kind).where(
            Character.id.in_(character_ids)
        )
    ):
        splats[who] = splat
        kind = npc_kinds().get(kind_key) if kind_key else None
        if kind is not None and not kind.vampiric:
            kinds[who] = (custom or {}).get("name") or kind.name

    def age(who: uuid.UUID) -> str:
        if who in kinds:
            return kinds[who]
        splat = SPLATS.get(splats.get(who, "vampire"))
        if splat is not None and not splat.panels.generation:
            return splat.label
        return age_for(generation[who], shift[who])

    return {c: Standing(clan.get(c), age(c)) for c in character_ids}
