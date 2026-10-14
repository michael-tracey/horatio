"""Character creation: starting traits, creation picks, and finishing creation.

A new character starts with its splat's starting traits, free. Until its
player finishes creation, they place creation picks: each pick gives one trait
that many free dots ("one skill at 4, two at 3…"), and merits and flaws come
from a budget of points instead. Picks follow the character's troupe rules —
its home troupe's, or the plain rule set before it has one. Finishing needs
every pick placed; points may be left unspent. After that, dots come from XP.

A pick can only go on a trait with no purchased dots, and can only be taken
back while the trait still has none, so free and paid dots never get tangled.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, CharacterTrait, User
from horatio.rules.model import CreationRuleData, TroupeRules
from horatio.sheets import (
    SheetRow,
    conflict,
    ensure_unlocked,
    find_definition,
    rules_for,
    sheet_rows,
    unprocessable,
)


@dataclass
class Pool:
    """Picks at one rating in a category, or a category's budget of points."""

    category: str
    # The pick's rating; 0 for a points budget.
    rating: int
    kind: str  # picks | points
    allowed: int
    traits: list[SheetRow] = field(default_factory=list)

    @property
    def used(self) -> int:
        if self.kind == "points":
            return sum(r.trait.creation_pick or 0 for r in self.traits)
        return len(self.traits)

    @property
    def remaining(self) -> int:
        return self.allowed - self.used


def pool_key(rule: CreationRuleData) -> tuple[str, int]:
    return (rule.category, rule.rating or 0 if rule.points is None else 0)


def pools_for(
    rules: Sequence[CreationRuleData], rows: Sequence[SheetRow]
) -> dict[tuple[str, int], Pool]:
    """The pools these creation rules give, with the picks already placed in them.
    Picks that fit no pool are left out; `stray_picks` finds them."""
    pools: dict[tuple[str, int], Pool] = {}
    for rule in rules:
        key = pool_key(rule)
        if rule.points is not None:
            pools[key] = Pool(rule.category, 0, "points", rule.points)
        else:
            assert rule.rating is not None and rule.picks is not None
            pools[key] = Pool(rule.category, rule.rating, "picks", rule.picks)
    for row in rows:
        if row.trait.creation_pick is None:
            continue
        points = pools.get((row.category.key, 0))
        if points is not None and points.kind == "points":
            points.traits.append(row)
        elif (pool := pools.get((row.category.key, row.trait.creation_pick))) is not None:
            pool.traits.append(row)
    return pools


def pools(db: Session, character: Character) -> dict[tuple[str, int], Pool]:
    return pools_for(rules_for(db, character).creation_rules(), sheet_rows(db, character))


def grant_starting_traits(db: Session, rules: TroupeRules, character: Character) -> None:
    for starting in rules.starting_traits():
        definition, _ = find_definition(db, character, starting.category, starting.name)
        db.add(
            CharacterTrait(
                character_id=character.id,
                trait_definition_id=definition.id,
                rating=starting.rating,
                free_rating=starting.rating or 0,
            )
        )
    db.flush()


def ensure_creating(db: Session, character: Character) -> None:
    ensure_unlocked(db, character)
    if character.creation_completed_at is not None:
        raise conflict("Character creation is finished; dots now come from experience.")


def place_pick(
    db: Session,
    player: User,
    character: Character,
    category: str,
    name: str,
    detail: str,
    rating: int,
) -> CharacterTrait:
    """Place a creation pick: `rating` free dots on a trait, or for merits and
    flaws, the trait at its point value from the budget."""
    ensure_creating(db, character)
    definition, trait_category = find_definition(db, character, category, name)
    all_pools = pools(db, character)
    points_pool = all_pools.get((category, 0))
    if points_pool is not None and points_pool.kind == "points":
        fixed = definition.properties.get("rating")
        rating = fixed if fixed is not None else rating
        pool = points_pool
        if rating > pool.remaining:
            raise conflict(f"That needs {rating} points; {pool.remaining} are left.")
    else:
        pool = all_pools.get((category, rating))
        if pool is None:
            raise unprocessable(f"There are no {trait_category.name} picks at {rating}.")
        if pool.remaining < 1:
            raise conflict(f"Every {trait_category.name} pick at {rating} is already placed.")

    trait = db.scalar(
        select(CharacterTrait).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == detail,
        )
    )
    if trait is not None and (trait.creation_pick is not None or (trait.rating or 0) > 0):
        raise conflict(f"{name} already has dots; a pick goes on a trait that has none.")
    if trait is None:
        trait = CharacterTrait(
            character_id=character.id, trait_definition_id=definition.id, detail=detail
        )
        db.add(trait)
    trait.rating = rating
    trait.free_rating = rating
    trait.creation_pick = rating
    db.flush()
    audit.record(
        db,
        player,
        "creation.pick",
        character_id=character.id,
        category=category,
        name=name,
        detail=detail,
        rating=rating,
    )
    return trait


def remove_pick(
    db: Session, player: User, character: Character, category: str, name: str, detail: str
) -> None:
    ensure_creating(db, character)
    definition, _ = find_definition(db, character, category, name)
    trait = db.scalar(
        select(CharacterTrait).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == detail,
        )
    )
    if trait is None or trait.creation_pick is None:
        raise conflict(f"{name} has no creation pick.")
    if (trait.rating or 0) > trait.free_rating:
        raise conflict(f"Undo the dots bought for {name} first.")
    db.delete(trait)
    db.flush()
    audit.record(
        db, player, "creation.unpick", character_id=character.id, category=category, name=name
    )


@dataclass
class PickSpec:
    name: str
    rating: int
    detail: str = ""


def set_category_picks(
    db: Session, player: User, character: Character, category: str, picks: Sequence[PickSpec]
) -> None:
    """Replace every creation pick in one category at once: one wizard step.

    The new picks need not fill the pools (a step can be saved half done), but
    must fit them. Picks on traits with bought dots cannot move or go, and a
    new pick cannot land on a trait that already has dots.
    """
    ensure_creating(db, character)
    all_pools = {key: p for key, p in pools(db, character).items() if key[0] == category}
    if not all_pools:
        raise unprocessable(f"There are no creation picks for {category}.")
    points = all_pools.get((category, 0))
    is_points = points is not None and points.kind == "points"

    wanted: dict[tuple[str, str], int] = {}
    definitions = {}
    for spec in picks:
        definition, _ = find_definition(db, character, category, spec.name)
        key = (definition.name, spec.detail)
        if key in wanted:
            raise unprocessable(f"{spec.name} is picked twice.")
        fixed = definition.properties.get("rating")
        wanted[key] = fixed if is_points and fixed is not None else spec.rating
        definitions[key] = definition

    if is_points:
        assert points is not None
        if sum(wanted.values()) > points.allowed:
            raise conflict(
                f"That is {sum(wanted.values())} points; the budget is {points.allowed}."
            )
    else:
        for rating in set(wanted.values()):
            pool = all_pools.get((category, rating))
            if pool is None:
                raise unprocessable(f"There are no {category.replace('_', ' ')} picks at {rating}.")
            used = sum(1 for r in wanted.values() if r == rating)
            if used > pool.allowed:
                raise conflict(f"Only {pool.allowed} at {rating}; that is {used}.")

    rows = {
        (r.definition.name, r.trait.detail): r
        for r in sheet_rows(db, character)
        if r.category.key == category
    }
    for key, row in rows.items():
        pick = row.trait.creation_pick
        if pick is None or wanted.get(key) == pick:
            continue
        if (row.trait.rating or 0) > row.trait.free_rating:
            raise conflict(f"{key[0]} has bought dots on top of its pick; undo them first.")
        db.delete(row.trait)
    db.flush()

    for key, rating in wanted.items():
        row = rows.get(key)
        if row is not None and row.trait.creation_pick == rating:
            continue
        if row is not None and row.trait.creation_pick is None and (row.trait.rating or 0) > 0:
            raise conflict(f"{key[0]} already has dots; a pick goes on a trait that has none.")
        db.add(
            CharacterTrait(
                character_id=character.id,
                trait_definition_id=definitions[key].id,
                detail=key[1],
                rating=rating,
                free_rating=rating,
                creation_pick=rating,
            )
        )
    db.flush()
    audit.record(
        db,
        player,
        "creation.set_category",
        character_id=character.id,
        category=category,
        picks={f"{n}{': ' + d if d else ''}": r for (n, d), r in wanted.items()},
    )


def complete(db: Session, player: User, character: Character) -> None:
    ensure_creating(db, character)
    unplaced = [p for p in pools(db, character).values() if p.kind == "picks" and p.remaining > 0]
    if unplaced:
        raise conflict(
            "Place every pick first: "
            + ", ".join(
                f"{p.remaining} {p.category.replace('_', ' ')} at {p.rating}" for p in unplaced
            )
        )
    character.creation_completed_at = datetime.now(UTC)
    db.flush()
    audit.record(db, player, "creation.complete", character_id=character.id)
