"""Creation picks fitted to an NPC built without the wizard (issue #527).

A player character's creation picks make dots free ("one skill at 4, two at 3…",
MET: VTM p. 84, as the troupe's creation rules have them). An NPC whose ratings are
set straight (built quickly, made sheeted from Stock, or imported from Yorick) has no
picks placed, so without this every dot on it would be priced as bought, and it
would be worth some 110 to 155 XP more than a player character with the same sheet.
Giving it to a player would turn that into real XP (horatio.npc_gifts).

So such an NPC (Character.fits_picks) has its picks fitted to its sheet: the way of
placing them a wizard could have used that leaves the least to pay for at its
troupe's prices, house rules and all. A pick goes only where the wizard would let it:
on a trait rated at least the pick, with no other free dots, that meets the pick's
restriction (an in-clan discipline). Merit and flaw budgets are filled as fully as
they can be, as the wizard fills them.

Staff can put the fitting right where it guessed wrong: place a pick on a trait by
hand, which every refit keeps, or take one off a trait, which the fitting then leaves
alone. The fitting fits the rest around what staff set. Every change to the sheet
refits (horatio.sheets.checked), so the free dots always follow the sheet as it is.
Once the NPC is given to a player, its picks are its own, as a wizard-built
character's are.

`python -m horatio.npc_picks` fits every NPC that needs it, once migration 0155 has
marked the ones built so far; Custodian › Tools fits one troupe's (horatio.troupe_fit).
"""

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, clan_merits
from horatio.creation import Fitting, Pool, no_picks, pools_for, restriction_error, stray_pools
from horatio.models import Character, CharacterTrait, User
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import PricingError, trait_cost
from horatio.sheets import SheetRow, conflict, find_definition, rules_for, sheet_rows, unprocessable

FIT = "fit"
STAFF = "staff"
OFF = "off"

# Placing a pick at all counts for less than a single XP saved, so the fitting saves
# the most XP first, then places as many picks as it can (a focus saves nothing).
PER_XP = 1000
# The merits a clan needs come out of the merit points first, as in the wizard.
CLAN_FIRST = 10**6


def fitted(npc: Character) -> bool:
    return npc.kind == "npc" and npc.npc_form == "sheeted" and npc.fits_picks


def drop(trait: CharacterTrait) -> None:
    """Take the pick off the trait, and the free dots it gave."""
    trait.free_rating = max(0, trait.free_rating - (trait.creation_pick or 0))
    trait.creation_pick = None
    trait.pick_by = None


def set_straight(trait: CharacterTrait, rating: int) -> None:
    """Set an NPC's trait straight to `rating`, as staff or an import do. A pick
    the trait no longer reaches goes; free dots never pass the rating."""
    if trait.creation_pick is not None and rating < trait.creation_pick:
        if trait.pick_by is not None:
            drop(trait)
        else:
            # A wizard's pick, as before this module: the dots left stay free.
            trait.creation_pick = None
    trait.rating = rating
    trait.free_rating = min(trait.free_rating or 0, rating)
    trait.granted_rating = min(trait.granted_rating or 0, rating)


def unfit(db: Session, npc: Character) -> None:
    """Take off every pick the fitting placed, leaving what staff set."""
    for trait in db.scalars(
        select(CharacterTrait).where(
            CharacterTrait.character_id == npc.id, CharacterTrait.pick_by == FIT
        )
    ):
        drop(trait)
    db.flush()


def cost(rules: TroupeRules, sheet: Sequence[SheetTrait], row: SheetRow, free: int) -> int:
    """What the trait's dots above `free` cost at the troupe's prices; 0 for one they
    don't price."""
    try:
        return trait_cost(rules, sheet, replace(row.as_rules_trait(), free_rating=free)).cost
    except PricingError:
        return 0


def open_to_fit(row: SheetRow) -> bool:
    """A trait the fitting may give a pick: rated, with no pick and no free dots of
    its own (a starting trait's, or what a merit gives), and not one staff took a
    pick off."""
    t = row.trait
    return (
        row.category.rated
        and bool(t.rating)
        and t.creation_pick is None
        and t.pick_by != OFF
        and t.free_rating == 0
        and t.granted_rating == 0
    )


def best_picks(
    slots: Mapping[int, int], options: Sequence[Sequence[tuple[int, int]]]
) -> list[int | None]:
    """The picks to give each candidate, as many as `slots` holds at each rating, for
    the most weight in all: `options[i]` is what candidate i could take, as (rating,
    weight). Exact, by going through the candidates with the picks still left: a
    category has few picks, so few ways to have some left."""
    ratings = sorted(slots)

    @cache
    def go(i: int, left: tuple[int, ...]) -> tuple[int, tuple[int | None, ...]]:
        if i == len(options):
            return 0, ()
        weight, rest = go(i + 1, left)
        best: tuple[int, tuple[int | None, ...]] = (weight, (None, *rest))
        for rating, gain in options[i]:
            j = ratings.index(rating)
            if not left[j]:
                continue
            weight, rest = go(i + 1, (*left[:j], left[j] - 1, *left[j + 1 :]))
            if weight + gain > best[0]:
                best = (weight + gain, (rating, *rest))
        return best

    return list(go(0, tuple(slots[r] for r in ratings))[1])


def best_budget(capacity: int, items: Sequence[tuple[int, int]]) -> list[bool]:
    """Which items, as (points, weight), to take from a budget of `capacity` points
    for the most weight: the knapsack, as budgets are small."""
    if capacity <= 0:
        return [False] * len(items)
    # best[c]: the most weight in c points, and the items taken.
    best: list[tuple[int, tuple[int, ...]]] = [(0, ())] * (capacity + 1)
    for i, (points, weight) in enumerate(items):
        if points <= 0:
            continue
        for c in range(capacity, points - 1, -1):
            weight_with = best[c - points][0] + weight
            if weight_with > best[c][0]:
                best[c] = (weight_with, (*best[c - points][1], i))
    taken = set(max(best, key=lambda b: b[0])[1])
    return [i in taken for i in range(len(items))]


def place(trait: CharacterTrait, pick: int, by: str) -> None:
    trait.creation_pick = pick
    trait.free_rating = pick
    trait.pick_by = by


def fit(db: Session, npc: Character) -> None:
    """Fit the NPC's creation picks to its sheet, around those staff set."""
    if not fitted(npc):
        return
    unfit(db, npc)
    rules = rules_for(db, npc)
    rows = sheet_rows(db, npc)
    sheet = [r.as_rules_trait() for r in rows]
    pools = pools_for(rules.creation_rules(), rows)
    fits = Fitting(db, npc)
    candidates = sorted(
        (r for r in rows if open_to_fit(r)), key=lambda r: (r.definition.name, r.trait.detail)
    )

    for category in dict.fromkeys(p.category for p in pools.values()):
        here = [r for r in candidates if r.category.key == category]
        points = pools.get((category, 0))
        if points is not None and points.kind == "points":
            clan = clan_merits.held(db, npc).names if category == "merits" else set()
            items = [
                (
                    r.trait.rating or 0,
                    (r.trait.rating or 0) * PER_XP
                    + cost(rules, sheet, r, 0)
                    + (CLAN_FIRST if r.definition.name in clan else 0),
                )
                for r in here
                if fits(points, r.definition.name, r.trait.detail)
            ]
            fitting = [r for r in here if fits(points, r.definition.name, r.trait.detail)]
            for row, take in zip(fitting, best_budget(points.remaining, items), strict=True):
                if take:
                    place(row.trait, row.trait.rating or 0, FIT)
            continue
        slots = {
            p.rating: p.remaining
            for p in pools.values()
            if p.category == category and p.kind == "picks" and p.remaining > 0
        }
        if not slots:
            continue
        options = [
            [
                (rating, (cost(rules, sheet, r, 0) - cost(rules, sheet, r, rating)) * PER_XP + 1)
                for rating in slots
                if (r.trait.rating or 0) >= rating
                and fits(pools[(category, rating)], r.definition.name, r.trait.detail)
            ]
            for r in here
        ]
        for row, pick in zip(here, best_picks(slots, options), strict=True):
            if pick is not None:
                place(row.trait, pick, FIT)
    db.flush()


def row_for(db: Session, npc: Character, category: str, name: str, detail: str) -> SheetRow:
    definition, _ = find_definition(db, npc, category, name)
    for row in sheet_rows(db, npc):
        if row.definition.id == definition.id and row.trait.detail == detail:
            return row
    raise unprocessable(f"{name} isn't on {npc.name}'s sheet.")


def ensure_fitted(npc: Character) -> None:
    if not fitted(npc):
        raise conflict(
            f"{npc.name}'s creation picks were placed in the wizard: change them there."
            if npc.kind == "npc"
            else f"{npc.name} isn't an NPC."
        )


def pin(
    db: Session,
    staff: User,
    npc: Character,
    category: str,
    name: str,
    detail: str,
    rating: int | None,
    replacing: tuple[str, str] | None = None,
) -> None:
    """Place a creation pick on a trait by hand: `rating` free dots of it, or for a
    budget of points (merits, flaws) the whole trait. `replacing` (a name and
    detail) is the trait whose place it takes in the list, which loses its pick
    unless the fitting gives it another. Every refit keeps the pick.

    A trait with a pick at another rating moves. The one it takes the place of, if
    staff placed it, goes where the trait was when it can take a pick there (a
    swap); a fitted one is fitted again with the rest."""
    ensure_fitted(npc)
    row = row_for(db, npc, category, name, detail)
    trait = row.trait
    # Where the trait's pick was, before the fitting's picks are taken off.
    was = trait.creation_pick
    unfit(db, npc)
    swapped: CharacterTrait | None = None
    if replacing is not None:
        other = row_for(db, npc, category, *replacing)
        if other.trait.pick_by == STAFF and other.trait is not trait:
            drop(other.trait)
            swapped = other.trait
    if trait.creation_pick is not None:
        drop(trait)
    if trait.pick_by == OFF:
        trait.pick_by = None
    db.flush()
    rows = sheet_rows(db, npc)
    rules = rules_for(db, npc)
    pools = pools_for(rules.creation_rules(), rows)
    points = pools.get((category, 0))
    held = trait.rating or 0
    if points is not None and points.kind == "points":
        pool, pick = points, held
        if pick > pool.remaining:
            raise conflict(
                f"{name} is {pick} points, and {max(pool.remaining, 0)} of the"
                f" {pool.allowed} are left."
            )
    else:
        if rating is None:
            raise unprocessable("Say which pick it takes.")
        found = pools.get((category, rating))
        if found is None or found.kind != "picks":
            category_name = rules.rule_set.categories[category].name
            raise unprocessable(
                no_picks(rules.creation_rules(), rows, category, category_name, rating)
            )
        pool, pick = found, rating
        if pool.remaining < 1:
            raise conflict(
                f"Every {category.replace('_', ' ')} pick at {rating} is placed by hand:"
                " take one off first."
            )
        if held < pick:
            raise unprocessable(f"{name} is rated {held}, below a pick at {pick}.")
    if trait.free_rating or trait.granted_rating:
        raise unprocessable(f"{name}'s dots are free already, so it takes no pick.")
    fits = Fitting(db, npc)
    if not fits(pool, name, detail):
        raise restriction_error(pool, name, fits)
    place(trait, pick, STAFF)
    db.flush()
    if swapped is not None and was is not None and was != pick and pool.kind == "picks":
        swap_into(db, npc, category, swapped, was)
    fit(db, npc)
    audit.record(
        db,
        staff,
        "npc.pick_placed",
        troupe_id=npc.owner_troupe_id,
        character_id=npc.id,
        name=f"{name}: {detail}" if detail else name,
        pick=pick,
    )


def swap_into(
    db: Session, npc: Character, category: str, trait: CharacterTrait, rating: int
) -> None:
    """Place a pick at `rating` by hand on `trait`, the one a move took the place of,
    if it can take one there: a swap. Otherwise the fitting places it with the rest."""
    rows = sheet_rows(db, npc)
    pool = pools_for(rules_for(db, npc).creation_rules(), rows).get((category, rating))
    row = next((r for r in rows if r.trait is trait), None)
    if (
        pool is None
        or pool.kind != "picks"
        or pool.remaining < 1
        or row is None
        or (trait.rating or 0) < rating
        or trait.free_rating
        or trait.granted_rating
        or not Fitting(db, npc)(pool, row.definition.name, trait.detail)
    ):
        return
    place(trait, rating, STAFF)
    db.flush()


def take_off(
    db: Session, staff: User, npc: Character, category: str, name: str, detail: str
) -> None:
    """Take the pick off a trait, and keep the fitting from giving it one; the pick
    goes where else it fits best."""
    ensure_fitted(npc)
    unfit(db, npc)
    trait = row_for(db, npc, category, name, detail).trait
    if trait.creation_pick is not None:
        drop(trait)
    trait.pick_by = OFF
    db.flush()
    fit(db, npc)
    audit.record(
        db,
        staff,
        "npc.pick_taken_off",
        troupe_id=npc.owner_troupe_id,
        character_id=npc.id,
        name=f"{name}: {detail}" if detail else name,
    )


def refit(db: Session, staff: User, npc: Character) -> None:
    """Forget what staff set, and fit every pick again."""
    ensure_fitted(npc)
    for trait in db.scalars(select(CharacterTrait).where(CharacterTrait.character_id == npc.id)):
        if trait.pick_by == STAFF:
            drop(trait)
        elif trait.pick_by == OFF:
            trait.pick_by = None
    db.flush()
    fit(db, npc)
    audit.record(
        db, staff, "npc.picks_refitted", troupe_id=npc.owner_troupe_id, character_id=npc.id
    )


@dataclass(frozen=True)
class Placed:
    name: str
    detail: str
    # The pick's rating, or the points it takes from a budget.
    pick: int
    by: str  # fit | staff


@dataclass(frozen=True)
class Candidate:
    name: str
    detail: str
    rating: int


@dataclass(frozen=True)
class PoolView:
    category: str
    category_name: str
    kind: str  # picks | points
    # The pick's rating; 0 for a budget of points.
    rating: int
    allowed: int
    placed: list[Placed]
    # The traits a pick here could go on instead.
    candidates: list[Candidate]


@dataclass(frozen=True)
class Picks:
    fitted: bool
    pools: list[PoolView]
    # Traits staff took a pick off, which the fitting leaves alone, as (category, name, detail).
    kept_off: list[tuple[str, str, str]]


def view(db: Session, npc: Character) -> Picks:
    """The NPC's creation picks, pool by pool, and where else each could go."""
    if npc.kind != "npc" or npc.npc_form != "sheeted":
        return Picks(False, [], [])
    rules = rules_for(db, npc)
    rows = sheet_rows(db, npc)
    placed = pools_for(rules.creation_rules(), rows)
    every = [*placed.values(), *stray_pools(rules.creation_rules(), rows, placed)]
    fits = Fitting(db, npc)
    order = list(rules.rule_set.categories)

    def could_take(pool: Pool, row: SheetRow) -> bool:
        t = row.trait
        own = t.creation_pick if t.creation_pick is not None else 0
        return (
            row.category.key == pool.category
            and row.category.rated
            and bool(t.rating)
            and t.free_rating - own == 0
            and t.granted_rating == 0
            and (pool.kind == "points" or (t.rating or 0) >= pool.rating)
            and fits(pool, row.definition.name, t.detail)
        )

    pools = [
        PoolView(
            category=pool.category,
            category_name=rules.rule_set.categories[pool.category].name,
            kind=pool.kind,
            rating=pool.rating,
            allowed=pool.allowed,
            placed=[
                Placed(
                    r.definition.name,
                    r.trait.detail,
                    r.trait.creation_pick or 0,
                    r.trait.pick_by or STAFF,
                )
                for r in pool.traits
            ],
            candidates=[
                Candidate(r.definition.name, r.trait.detail, r.trait.rating or 0)
                for r in sorted(rows, key=lambda r: (r.definition.name, r.trait.detail))
                if could_take(pool, r)
            ],
        )
        for pool in sorted(
            every,
            key=lambda p: (
                order.index(p.category) if p.category in order else len(order),
                -p.rating,
            ),
        )
    ]
    kept_off = [
        (r.category.key, r.definition.name, r.trait.detail) for r in rows if r.trait.pick_by == OFF
    ]
    return Picks(fitted(npc), pools, kept_off)


def fit_all(db: Session) -> int:
    """Fit the picks of every NPC that fits them. Fitting again changes nothing on a
    sheet already fitted, so this can run any number of times."""
    count = 0
    for npc in db.scalars(select(Character).where(Character.fits_picks)):
        if fitted(npc):
            fit(db, npc)
            count += 1
    return count


def main() -> int:
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db, db.begin():
        count = fit_all(db)
    print(f"Fitted the creation picks of {count} NPC{'s' if count != 1 else ''}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
