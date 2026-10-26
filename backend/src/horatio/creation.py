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

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, CharacterTrait, User
from horatio.rules.checks import holds_trait, matches, traits_in
from horatio.rules.model import CreationRuleData, SheetTrait, TroupeRules
from horatio.rules.splats import SPLATS
from horatio.sheets import (
    SheetRow,
    conflict,
    ensure_named,
    ensure_offered,
    ensure_unlocked,
    find_definition,
    held_at,
    path_start,
    rules_for,
    sheet_effects,
    sheet_rows,
    sheet_violations,
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
    # A splat fact each trait must have to take a pick here, such as "in_clan".
    restriction: str | None = None
    # For a pool the rules no longer give (see `stray_pools`): the traits held that
    # took it away, as (category, name).
    because: list[tuple[str, str]] = field(default_factory=list)

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


def held_in(
    sheet: Sequence[SheetTrait], condition: Mapping[str, Any] | None
) -> list[tuple[str, str]]:
    """The traits a creation rule's condition names that the sheet holds, as (category,
    name): what the rule is because of."""
    return sorted(
        (c, n)
        for c, n in traits_in(condition)
        if n and holds_trait(sheet, {"category": c, "name": n})
    )


def pools_for(
    rules: Sequence[CreationRuleData], rows: Sequence[SheetRow]
) -> dict[tuple[str, int], Pool]:
    """The pools these creation rules give, with the picks already placed in them.
    Picks that fit no pool are left out; `stray_picks` finds them."""
    pools: dict[tuple[str, int], Pool] = {}
    sheet = [row.as_rules_trait() for row in rows]
    for rule in rules:
        # A creation rule's condition is about the sheet, not one trait.
        if rule.when and not matches(rule.when, sheet, SheetTrait(category="", name="")):
            continue
        key = pool_key(rule)
        # A rule that holds because of a trait on the sheet says so (Inept's one pick fewer).
        because = held_in(sheet, rule.when)
        if rule.points is not None:
            pools[key] = Pool(
                rule.category,
                0,
                "points",
                rule.points,
                restriction=rule.restriction,
                because=because,
            )
        else:
            assert rule.rating is not None and rule.picks is not None
            pools[key] = Pool(
                rule.category,
                rule.rating,
                "picks",
                rule.picks,
                restriction=rule.restriction,
                because=because,
            )
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


def stray_pools(
    rules: Sequence[CreationRuleData],
    rows: Sequence[SheetRow],
    placed: Mapping[tuple[str, int], Pool],
) -> list[Pool]:
    """Picks that fit no pool now, because a rule that gave their pool has switched off
    (Thin Blooded takes away the pick at 2). They are kept, never dropped, each
    rating as a pool with nothing allowed, so the wizard can show them and have them
    moved. The pool says what took it away."""
    seated = {id(r) for pool in placed.values() for r in pool.traits}
    sheet = [row.as_rules_trait() for row in rows]
    strays: dict[tuple[str, int], Pool] = {}
    for row in rows:
        pick, category = row.trait.creation_pick, row.category.key
        if pick is None or id(row) in seated:
            continue
        beside = [p for p in placed.values() if p.category == category and p.kind == "picks"]
        if not beside:
            continue
        if (category, pick) not in strays:
            lost = {
                trait
                for rule in rules
                if rule.category == category and rule.rating == pick and rule.when
                for trait in held_in(sheet, rule.when)
            }
            strays[(category, pick)] = Pool(
                category,
                pick,
                "picks",
                0,
                restriction=beside[0].restriction,
                because=sorted(lost),
            )
        strays[(category, pick)].traits.append(row)
    return list(strays.values())


def budget_changes(db: Session, character: Character) -> dict[str, list[tuple[str, str]]]:
    """For each category, the traits the sheet holds that change what its creation rules
    give: Thin Blooded and Inept for the starting disciplines."""
    sheet = [row.as_rules_trait() for row in sheet_rows(db, character)]
    changes: dict[str, list[tuple[str, str]]] = {}
    for rule in rules_for(db, character).creation_rules():
        if rule.when:
            found = changes.setdefault(rule.category, [])
            found.extend(t for t in held_in(sheet, rule.when) if t not in found)
    return {category: found for category, found in changes.items() if found}


def freed_picks(
    db: Session, character: Character
) -> dict[tuple[str, str, str], list[tuple[str, str]]]:
    """The creation picks a trait now gives for free, by (category, name, detail), and the
    traits that give it: a pick on Herd while Personal Cult makes Herd free to 5. The
    pick is spent on dots the character has without it, so it can go elsewhere."""
    found = sheet_effects(db, character)
    freed: dict[tuple[str, str, str], list[tuple[str, str]]] = {}
    for row in sheet_rows(db, character):
        pick = row.trait.creation_pick
        if pick is None or row.category.key == "merits" or row.category.key == "flaws":
            continue
        if found.free_up_to.get(row.key, 0) >= pick:
            freed[row.key] = list(dict.fromkeys(found.givers.get(row.key, [])))
    return freed


@dataclass
class Given:
    """A trait the character holds with no creation pick of its own: its dots come
    from a merit (Extrasensory Perceptions' Perception focus, Diva's Fame 2)."""

    category: str
    name: str
    detail: str
    rating: int
    because: list[tuple[str, str]]


def given_traits(db: Session, character: Character, categories: Sequence[str]) -> list[Given]:
    """The traits in these categories that merits give, which a pick cannot go on."""
    found = sheet_effects(db, character)
    return [
        Given(
            row.category.key,
            row.definition.name,
            row.trait.detail,
            row.trait.granted_rating,
            list(dict.fromkeys(found.givers.get(row.key, []))),
        )
        for row in sheet_rows(db, character)
        if row.category.key in categories
        and row.trait.creation_pick is None
        and row.trait.granted_rating > 0
        and (row.trait.rating or 0) > 0
    ]


def pools_with_strays(db: Session, character: Character) -> list[Pool]:
    rules = rules_for(db, character).creation_rules()
    rows = sheet_rows(db, character)
    placed = pools_for(rules, rows)
    return [*placed.values(), *stray_pools(rules, rows, placed)]


RESTRICTION_TEXT = {"in_clan": "in-clan"}


class Fitting:
    """Whether a trait may take a pick from a pool, given the sheet as it stands
    (for "in_clan", that means the character's clan and the merits that change
    its in-clan disciplines). Read once, for as many traits as are asked about."""

    def __init__(self, db: Session, character: Character):
        self.rules = rules_for(db, character)
        self.sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
        self.facts = SPLATS[character.splat].facts

    def _facts(self, pool: Pool, name: str, detail: str) -> Mapping[str, Any]:
        trait = SheetTrait(category=pool.category, name=name, detail=detail, rating=0)
        return self.facts(self.rules, self.sheet, trait)

    def meets(self, pool: Pool, name: str, detail: str) -> bool:
        """Whether the trait meets the pool's restriction (is in-clan)."""
        if pool.restriction is None:
            return True
        return bool(self._facts(pool, name, detail).get(pool.restriction))

    def without_dot(self, pool: Pool, name: str, detail: str) -> tuple[tuple[str, str], ...]:
        """The traits that leave this one without a free starting dot, as (category,
        name): Inept's discipline, or an extra in-clan discipline a merit gave."""
        if pool.restriction is None:
            return ()
        return tuple(self._facts(pool, name, detail).get("no_free_dot_because", ()))

    def __call__(self, pool: Pool, name: str, detail: str) -> bool:
        return self.meets(pool, name, detail) and not self.without_dot(pool, name, detail)


def fitting(db: Session, character: Character) -> Fitting:
    return Fitting(db, character)


def category_names(db: Session, character: Character, pool: Pool) -> list[str]:
    rule_set = rules_for(db, character).rule_set
    return sorted(n for (c, n) in rule_set.traits if c == pool.category)


def options(db: Session, character: Character, pool: Pool, fits: Fitting) -> list[str] | None:
    """The traits a restricted pool's picks go on, such as the in-clan disciplines
    (some of which can still take no free dot: see `without_dot`); None for a pool
    open to its whole category."""
    if pool.restriction is None:
        return None
    return [n for n in category_names(db, character, pool) if fits.meets(pool, n, "")]


def without_dot(
    db: Session, character: Character, pool: Pool, fits: Fitting
) -> dict[str, tuple[tuple[str, str], ...]]:
    """The traits of a restricted pool that take no pick, though in-clan or priced as
    in-clan, and what leaves each without: the extra discipline Additional Common
    Discipline gives, and the one Inept names."""
    if pool.restriction is None:
        return {}
    found = {n: fits.without_dot(pool, n, "") for n in category_names(db, character, pool)}
    return {n: because for n, because in found.items() if because}


def restriction_error(pool: Pool, name: str, fits: Fitting | None = None) -> HTTPException:
    kind = RESTRICTION_TEXT.get(pool.restriction or "", pool.restriction or "")
    if fits is not None and (by := fits.without_dot(pool, name, "")):
        causes = ", ".join(dict.fromkeys(n for _, n in by))
        return unprocessable(f"{name} starts without a free dot ({causes}), so it takes no pick.")
    return unprocessable(
        f"{name} is not {kind}. Only {kind} {pool.category.replace('_', ' ')} can take these picks;"
        " choose the clan first if you have not."
    )


def grant_starting_traits(
    db: Session, rules: TroupeRules, character: Character, skip: Collection[str] = ()
) -> None:
    """Give the character the rule set's starting traits, but for those in the
    categories in `skip` (an NPC that is no vampire has no Humanity)."""
    for starting in rules.starting_traits():
        if starting.category in skip:
            continue
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
        fixed = held_at(db, character, category, definition.name)
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
    fits = fitting(db, character)
    if not fits(pool, definition.name, detail):
        raise restriction_error(pool, definition.name, fits)
    ensure_offered(db, character, category, definition.name)

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
        ensure_named(definition, detail)
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
        name=f"★ {name}" if definition.troupe_id else name,
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

    rows = {
        (r.definition.name, r.trait.detail): r
        for r in sheet_rows(db, character)
        if r.category.key == category
    }
    wanted: dict[tuple[str, str], int] = {}
    definitions = {}
    for spec in picks:
        definition, _ = find_definition(db, character, category, spec.name)
        key = (definition.name, spec.detail)
        if key in wanted:
            raise unprocessable(f"{spec.name} is picked twice.")
        fixed = held_at(db, character, category, definition.name)
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
                # A pick the rules no longer give a pool for (Thin Blooded's dot at 2) may
                # stay as it was, until its player moves it; nothing new goes there.
                kept = [
                    k
                    for k, r in wanted.items()
                    if r == rating
                    and (row := rows.get(k)) is not None
                    and row.trait.creation_pick == rating
                ]
                if len(kept) == sum(1 for r in wanted.values() if r == rating):
                    continue
                raise unprocessable(f"There are no {category.replace('_', ' ')} picks at {rating}.")
            used = sum(1 for r in wanted.values() if r == rating)
            if used > pool.allowed:
                raise conflict(f"Only {pool.allowed} at {rating}; that is {used}.")
    # A pick kept as it was may stay where it no longer fits (a starting dot on a
    # discipline that is no longer in-clan): the wizard marks it, and finishing
    # refuses it. Only a new or moved pick must fit.
    fits = fitting(db, character)
    for (name, detail), rating in wanted.items():
        kept = rows.get((name, detail))
        if kept is not None and kept.trait.creation_pick == rating:
            continue
        pool = all_pools.get((category, 0 if is_points else rating))
        if pool is not None and not fits(pool, name, detail):
            raise restriction_error(pool, name, fits)
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
        if row is None:
            ensure_named(definitions[key], key[1])
            ensure_offered(db, character, category, key[0])
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
    if SPLATS[character.splat].has_domitor and not (character.domitor_id or character.domitor_name):
        raise conflict("Name the ghoul's domitor first: its clan and disciplines follow from it.")
    every = pools_with_strays(db, character)
    unplaced = [p for p in every if p.kind == "picks" and p.remaining > 0]
    if unplaced:
        raise conflict(
            "Place every pick first: "
            + ", ".join(
                f"{p.remaining} {p.category.replace('_', ' ')} at {p.rating}" for p in unplaced
            )
        )
    # More picks than the rules give: a merit may have taken a pool away, as Thin
    # Blooded does the pick at 2. They are kept until their player moves them.
    over = [
        f"{row.definition.name} at {pool.rating}"
        for pool in every
        if pool.kind == "picks" and pool.remaining < 0
        for row in pool.traits
    ]
    if over:
        raise conflict("These picks are more than the rules now give: " + ", ".join(over))
    # The clan may have changed since the picks were placed.
    fits = fitting(db, character)
    stray = [
        row.definition.name
        for pool in every
        for row in pool.traits
        if not fits(pool, row.definition.name, row.trait.detail)
    ]
    if stray:
        raise conflict("These picks are not allowed for this character: " + ", ".join(stray))
    if character.kind == "pc":
        broken = [
            v.message
            for v in sheet_violations(db, character)
            if v.check.strength in ("refuse", "complete")
        ]
        if broken:
            raise conflict("Before finishing: " + " ".join(dict.fromkeys(broken)))
    character.creation_completed_at = datetime.now(UTC)
    db.flush()
    audit.record(db, player, "creation.complete", character_id=character.id)


@dataclass
class PathStart:
    category: str
    # The Path the character is on, and the merit that put them on it.
    name: str
    rating: int
    because: tuple[str, str]
    page: str | None = None


def path_starts(db: Session, character: Character) -> list[PathStart]:
    """The Paths whose Morality starts lower than Humanity's: bought in creation, a Path
    merit starts its Path at 4 instead of 5 (core p. 306)."""
    if character.kind != "pc" or character.creation_completed_at is not None:
        return []
    rules = rules_for(db, character)
    found = sheet_effects(db, character)
    rows = sheet_rows(db, character)
    starts: list[PathStart] = []
    for (category, origin), path in found.converts.items():
        lowered = path_start(rules, category, origin)
        by = found.converted_by.get((category, origin))
        row = next(
            (r for r in rows if (r.category.key, r.definition.name) == (category, path)), None
        )
        if path == origin or lowered is None or by is None or row is None:
            continue
        if row.trait.rating == row.trait.free_rating == lowered[0]:
            page = rules.rule_set.trait_properties(category, origin).get("path_start_page")
            starts.append(PathStart(category, path, lowered[0], by, page))
    return starts
