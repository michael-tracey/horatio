"""Stock NPCs (MET: VTM pp. 489–490): NPCs with no full sheet, only an NPC rating
and a few specializations, for a storyteller who needs a bartender, a police
officer or a pack of werewolves in a hurry (issue #215).

- The rating, 1 to 5 (higher where the kind allows), is the NPC's test pool
  halved: its pool in most challenges is rating × 2.
- It has as many specialisations as its rating. A skill specialization adds 5 to
  that skill's pool; a discipline specialization gives that discipline's dots up
  to the rating. Mortals take skill specializations only, but for the numina or
  powers their kind lists (a hunter's True Faith or Hedge Magic).
- No Willpower, so no retests, unless it can overbid; health levels equal to its
  rating (twice that for some kinds); Blood or its kind's resource.
- An infernal Stock NPC of any kind may take the Infernal Investment
  specialisation, which opens every Dark Thaumaturgy ritual to it (the V20 LARP
  SRD, issue #414): the one way a Stock NPC has rituals.

Nothing here reads the database: horatio.npcs keeps Stock NPCs and asks these
rules what they make.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal

from horatio.rules.npc_kinds import MAX_DOTS, BuiltInPower, NpcKind, Resource

# A Stock NPC's test pool is its rating times this (p. 489)...
POOL_PER_RATING = 2
# ...and a skill specialization adds this to it (p. 489).
SKILL_BONUS = 5
# What no Stock NPC has, whatever its kind (p. 490).
STOCK_RULES = (
    "No Willpower: it cannot retest a failed challenge unless it can overbid.",
    "No elder powers or techniques, and no rituals from its Necromancy or Thaumaturgy paths.",
    "No attribute focuses, so no focus effects for its powers.",
    "Out of the fight at no health levels left, but not necessarily dead.",
)
# The V20 LARP SRD's specialisation for an infernal Stock NPC, open to every kind: it
# gives no dots, but every Dark Thaumaturgy ritual (its Infernal Power page).
INFERNAL_INVESTMENT = BuiltInPower(
    name="Infernal Investment",
    note="Every Dark Thaumaturgy ritual; its aura shows infernal taint while it casts one",
)


@dataclass(frozen=True)
class Specialization:
    type: Literal["skill", "power"]
    name: str


@dataclass(frozen=True)
class StatBlock:
    """What the book prints for a Stock NPC (the sample on p. 490)."""

    rating: int
    # The test pool in most challenges.
    pool: int
    # The pool in challenges with each skill it specializes in.
    skill_pools: tuple[tuple[str, int], ...]
    # The dots it reaches in each discipline, path or numina: from its
    # specializations and from its kind.
    powers: tuple[tuple[str, int], ...]
    # Single powers and merits its kind gives it at its rating, and Infernal
    # Investment if it specializes in that.
    built_in: tuple[BuiltInPower, ...]
    health: int
    resource: Resource
    # Stock NPCs have no Willpower and do not retest (p. 490).
    willpower: int = 0
    retests: bool = False


class StockError(ValueError):
    """A Stock NPC the rules do not allow, with the reason in the storyteller's words."""


def pool(rating: int) -> int:
    return rating * POOL_PER_RATING


def skill_pool(rating: int) -> int:
    return pool(rating) + SKILL_BONUS


def health(kind: NpcKind, rating: int) -> int:
    return rating * kind.health_per_rating


def stat_block(kind: NpcKind, rating: int, specializations: Sequence[Specialization]) -> StatBlock:
    dots: dict[str, int] = {}
    for power in kind.powers:
        if power.dots is not None and (power.from_rating or 0) <= rating:
            dots[power.name] = max(dots.get(power.name, 0), power.dots_at(rating))
    for s in specializations:
        if s.type == "power" and s.name != INFERNAL_INVESTMENT.name:
            # The discipline's dots up to the rating, above any its kind gives (a
            # wraith's Dementation, p. 500).
            dots[s.name] = max(dots.get(s.name, 0), min(rating, MAX_DOTS))
    infernal = any(s == Specialization("power", INFERNAL_INVESTMENT.name) for s in specializations)
    return StatBlock(
        rating=rating,
        pool=pool(rating),
        skill_pools=tuple(
            (s.name, skill_pool(rating)) for s in specializations if s.type == "skill"
        ),
        powers=tuple(dots.items()),
        built_in=tuple(p for p in kind.powers if p.dots is None and (p.from_rating or 0) <= rating)
        + ((INFERNAL_INVESTMENT,) if infernal else ()),
        health=health(kind, rating),
        resource=kind.resource,
    )


def check(
    kind: NpcKind,
    rating: int,
    specializations: Sequence[Specialization],
    skills: Collection[str],
    disciplines: Collection[str],
) -> None:
    """Raise StockError unless the rules allow this Stock NPC. `skills` and
    `disciplines` are the names the Vampire rule set has (paths among the
    disciplines)."""
    if not 1 <= rating <= kind.rating_max:
        raise StockError(f"{kind.label} Stock NPCs are rated 1 to {kind.rating_max} (p. 489).")
    if len(specializations) > rating:
        raise StockError(
            f"A Stock NPC has as many specialisations as its rating: {rating} at most (p. 489)."
        )
    seen: set[tuple[str, str]] = set()
    for s in specializations:
        if (s.type, s.name) in seen:
            raise StockError(f"{s.name} is already one of its specialisations.")
        seen.add((s.type, s.name))
        if s.type == "skill":
            if s.name not in skills:
                raise StockError(f"{s.name} is not a skill.")
        elif s.name != INFERNAL_INVESTMENT.name and not kind.may_specialize(s.name, disciplines):
            if kind.mortal and not kind.numina and not kind.specializations:
                raise StockError("A mortal Stock NPC takes skill specialisations only (p. 489).")
            raise StockError(f"{kind.label} Stock NPCs cannot specialise in {s.name}.")
