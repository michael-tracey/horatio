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

Some merits give free dots that a player places in the wizard (#566), but such an
NPC holds the merit with nothing placed. So the fitting places them too, where a
merit it holds lets it: Ventrue Royalty's 4, 3 and 2 (a `free_choices` grant's
places), each on a different one of its backgrounds rated at least the place, and
a Path merit's conversion (`convert`), which makes the Path's dots free up to the
Humanity a character starts with, as converting it from Humanity would have kept
them. A trait takes a pick or a place, never both: the places are fitted together
with the creation picks of their category, for the most saved in all, which is
never less than fitting either first (where a place and a pick would save as
much, the place goes there). Staff move or take off a place as they do a pick.
Given to a player, the places become the merit's own choices
(`CharacterTrait.choices`).

The other free_choices grants are not fitted, and what they give is priced as
bought: Chosen of Cappadocius's specialisations cost nothing anyway, and a merit
that Auspicious, Old Habits, Piece That Remains or Shadows of the Past gives would
have to be told apart from the merits the creation points buy.

`python -m horatio.npc_picks` fits every NPC that needs it, once migration 0155 has
marked the ones built so far; Custodian › Tools fits one troupe's (horatio.troupe_fit).
"""

import sys
from collections import Counter
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cache

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import audit, clan_merits
from horatio.creation import Fitting, Pool, no_picks, pools_for, restriction_error, stray_pools
from horatio.models import Character, CharacterTrait, User
from horatio.rules.checks import matches
from horatio.rules.grants import GrantData, choices, chosen_target, holds_source, options
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
# A creation pick's slot in best_picks, beside a merit's places (keyed by its grant).
PICK = ""


def fitted(npc: Character) -> bool:
    return npc.kind == "npc" and npc.npc_form == "sheeted" and npc.fits_picks


def drop(trait: CharacterTrait) -> None:
    """Take the pick off the trait, and the free dots it gave."""
    trait.free_rating = max(0, trait.free_rating - (trait.creation_pick or 0))
    trait.creation_pick = None
    trait.pick_by = None


def drop_place(trait: CharacterTrait) -> None:
    """Take a merit's place off the trait, and the free dots it gave."""
    trait.free_rating = max(0, trait.free_rating - (trait.grant_place or 0))
    trait.grant_place = None
    trait.place_grant = None
    trait.place_by = None


def set_straight(trait: CharacterTrait, rating: int) -> None:
    """Set an NPC's trait straight to `rating`, as staff or an import do. A pick
    or a merit's place the trait no longer reaches goes; free dots never pass the
    rating."""
    if trait.grant_place is not None and rating < trait.grant_place:
        drop_place(trait)
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
    """Take off every pick and place the fitting placed, leaving what staff set."""
    for trait in db.scalars(
        select(CharacterTrait).where(
            CharacterTrait.character_id == npc.id,
            or_(CharacterTrait.pick_by == FIT, CharacterTrait.place_by == FIT),
        )
    ):
        if trait.pick_by == FIT:
            drop(trait)
        if trait.place_by == FIT:
            drop_place(trait)
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
    return unfree(row) and row.trait.pick_by != OFF


def open_to_place(row: SheetRow) -> bool:
    """A trait the fitting may give a merit's place, as `open_to_fit` a pick."""
    return unfree(row) and row.trait.place_by != OFF


def unfree(row: SheetRow) -> bool:
    t = row.trait
    return (
        row.category.rated
        and bool(t.rating)
        and t.creation_pick is None
        and t.free_rating == 0
        and t.granted_rating == 0
    )


@dataclass(frozen=True)
class Giving:
    """A grant of a merit the NPC holds whose free dots the fitting places: a
    free_choices grant's places (Ventrue Royalty's 4, 3 and 2 on its backgrounds),
    or a Path merit's conversion."""

    grant: GrantData
    # The merit that holds it.
    merit: str
    category: str
    # The traits it may go on: those it offers, or the Path it converts to.
    names: frozenset[str]
    # The places, each used once on a different trait; for a conversion, one: the
    # free dots it gives the Path at most, the starting Humanity's.
    amounts: tuple[int, ...]

    @property
    def key(self) -> str:
        return self.grant.key

    @property
    def converts(self) -> bool:
        return self.grant.kind == "convert"

    def left(self, rows: Sequence[SheetRow]) -> Counter[int]:
        """The places staff have not set by hand."""
        return Counter(self.amounts) - Counter(
            r.trait.grant_place or 0
            for r in rows
            if r.trait.place_by == STAFF and r.trait.place_grant == self.key
        )

    def takes(self, row: SheetRow) -> bool:
        return row.category.key == self.category and row.definition.name in self.names

    def could_take(self, row: SheetRow, amount: int) -> bool:
        """Whether a place of `amount` could go on the trait, by hand: one it may
        go on, rated as high, with no free dots but its own place's."""
        t = row.trait
        own = (t.grant_place or 0) if t.place_grant == self.key else 0
        return (
            self.takes(row)
            and bool(t.rating)
            and (self.converts or (t.rating or 0) >= amount)
            and t.creation_pick is None
            and t.free_rating - own == 0
            and t.granted_rating == 0
        )

    def amount_for(self, row: SheetRow, amount: int) -> int:
        """The free dots a place of `amount` gives the trait: a conversion keeps
        what it can of the Path's rating."""
        return min(row.trait.rating or 0, amount) if self.converts else amount


def givings(rules: TroupeRules, rows: Sequence[SheetRow]) -> dict[str, Giving]:
    """The grants of merits on the sheet that the fitting places, by key. A merit
    with choices of its own (made in the wizard) keeps them."""
    rule_set = rules.rule_set
    sheet = [r.as_rules_trait() for r in rows]
    by_name: dict[tuple[str, str], list[SheetRow]] = {}
    for row in rows:
        by_name.setdefault((row.category.key, row.definition.name), []).append(row)
    found: dict[str, Giving] = {}
    for grant in rule_set.grants:
        places = (grant.picks or {}).get("places") if grant.kind == "free_choices" else None
        if places is None and grant.kind != "convert":
            continue
        for row in by_name.get((grant.source["category"], grant.source["name"]), ()):
            trait = row.as_rules_trait()
            if grant.key in found or not holds_source(trait, grant.source):
                continue
            if grant.when is not None and not matches(grant.when, sheet, trait):
                continue
            if places is not None:
                if any(c.grant == grant.key for c in trait.choices):
                    continue
                names = frozenset(o.name for o in options(grant, rule_set, sheet))
                amounts = tuple(sorted(places, reverse=True))
            else:
                assert grant.convert_from is not None
                origin = (grant.convert_from["category"], grant.convert_from["name"])
                start = next(
                    (s.rating for s in rules.starting_traits() if (s.category, s.name) == origin),
                    None,
                )
                if not start:
                    continue
                if "choose" in grant.target:
                    chosen = chosen_target(grant, trait.detail, rule_set)
                    names = frozenset(
                        [chosen[1]] if chosen is not None else choices(grant, rule_set)
                    )
                else:
                    names = frozenset([grant.target["name"]])
                amounts = (start,)
            found[grant.key] = Giving(
                grant, row.definition.name, grant.categories[0], names, amounts
            )
    return found


def place_on(trait: CharacterTrait, amount: int, grant: str, by: str) -> None:
    trait.grant_place = amount
    trait.place_grant = grant
    trait.free_rating = amount
    trait.place_by = by


def let_go(rows: Sequence[SheetRow], giving: Mapping[str, Giving]) -> None:
    """Take off the places staff set that the sheet no longer allows: the merit
    gone, the trait below the place, or more by hand than the merit gives."""
    seen: Counter[tuple[str, int]] = Counter()
    for row in rows:
        t = row.trait
        if t.place_by != STAFF or t.grant_place is None or t.place_grant is None:
            continue
        found = giving.get(t.place_grant)
        seen[(t.place_grant, t.grant_place)] += 1
        if (
            found is None
            or not found.takes(row)
            or (t.rating or 0) < t.grant_place
            or seen[(t.place_grant, t.grant_place)] > Counter(found.amounts)[t.grant_place]
        ):
            drop_place(t)


def best_picks[K: Hashable](
    slots: Mapping[K, int], options: Sequence[Sequence[tuple[K, int]]]
) -> list[K | None]:
    """The picks to give each candidate, as many as `slots` holds of each kind (a
    rating, or a merit's place), for the most weight in all: `options[i]` is what
    candidate i could take, as (kind, weight). Exact, by going through the
    candidates with the picks still left: a category has few picks, so few ways to
    have some left."""
    ratings = list(slots)

    @cache
    def go(i: int, left: tuple[int, ...]) -> tuple[int, tuple[K | None, ...]]:
        if i == len(options):
            return 0, ()
        weight, rest = go(i + 1, left)
        best: tuple[int, tuple[K | None, ...]] = (weight, (None, *rest))
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
    """Fit the NPC's creation picks, and the places its merits give, to its sheet,
    around those staff set."""
    if not fitted(npc):
        return
    unfit(db, npc)
    rules = rules_for(db, npc)
    rows = sheet_rows(db, npc)
    giving = givings(rules, rows)
    let_go(rows, giving)
    for found in giving.values():
        if found.converts:
            for row in rows:
                if found.takes(row) and open_to_place(row):
                    place_on(row.trait, found.amount_for(row, found.amounts[0]), found.key, FIT)
    places = [g for g in giving.values() if not g.converts]
    sheet = [r.as_rules_trait() for r in rows]
    pools = pools_for(rules.creation_rules(), rows)
    fits = Fitting(db, npc)
    ordered = sorted(rows, key=lambda r: (r.definition.name, r.trait.detail))

    def saved(row: SheetRow, slot: tuple[str, int]) -> int:
        """What a pick or place saves, weighted: the XP first, then placing it at
        all; and of two that save as much, the merit's place, as the merit's
        places are where its traits are and the picks go anywhere."""
        free = slot[1]
        weight = (cost(rules, sheet, row, 0) - cost(rules, sheet, row, free)) * PER_XP + 1
        return weight if slot[0] == PICK else weight + 1

    categories = [*(p.category for p in pools.values()), *(g.category for g in places)]
    for category in dict.fromkeys(categories):
        here = [r for r in ordered if r.category.key == category]
        slots: dict[tuple[str, int], int] = {}
        points = pools.get((category, 0))
        if points is not None and points.kind == "points":
            clan = clan_merits.held(db, npc).names if category == "merits" else set()
            fitting = [
                r
                for r in here
                if open_to_fit(r) and fits(points, r.definition.name, r.trait.detail)
            ]
            items = [
                (
                    r.trait.rating or 0,
                    (r.trait.rating or 0) * PER_XP
                    + cost(rules, sheet, r, 0)
                    + (CLAN_FIRST if r.definition.name in clan else 0),
                )
                for r in fitting
            ]
            for row, take in zip(fitting, best_budget(points.remaining, items), strict=True):
                if take:
                    place(row.trait, row.trait.rating or 0, FIT)
        else:
            slots = {
                (PICK, p.rating): p.remaining
                for p in pools.values()
                if p.category == category and p.kind == "picks" and p.remaining > 0
            }
        # Each of a merit's places goes on a different trait: of two by one name
        # (Allies twice), only the higher rated can take one.
        open_for: dict[str, dict[str, SheetRow]] = {}
        for found in places:
            if found.category != category:
                continue
            for amount, count in found.left(rows).items():
                if count > 0:
                    slots[(found.key, amount)] = count
            taken = {r.definition.name for r in here if r.trait.place_grant == found.key}
            first: dict[str, SheetRow] = {}
            for row in sorted(here, key=lambda r: -(r.trait.rating or 0)):
                name = row.definition.name
                if found.takes(row) and open_to_place(row) and name not in taken:
                    first.setdefault(name, row)
            open_for[found.key] = first
        if not slots:
            continue
        options = [
            [
                (slot, saved(r, slot))
                for slot in slots
                if (r.trait.rating or 0) >= slot[1]
                and (
                    open_to_fit(r)
                    and fits(pools[(category, slot[1])], r.definition.name, r.trait.detail)
                    if slot[0] == PICK
                    else open_for[slot[0]].get(r.definition.name) is r
                )
            ]
            for r in here
        ]
        for row, chosen in zip(here, best_picks(slots, options), strict=True):
            if chosen is None:
                continue
            kind, rating = chosen
            if kind == PICK:
                place(row.trait, rating, FIT)
            else:
                place_on(row.trait, rating, kind, FIT)
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


def pin_place(
    db: Session,
    staff: User,
    npc: Character,
    grant: str,
    category: str,
    name: str,
    detail: str,
    amount: int | None,
    replacing: tuple[str, str] | None = None,
) -> None:
    """Place one of a merit's places on a trait by hand, as `pin` a pick: the
    place of `amount` its grant gives, which every refit keeps. A trait with a
    place moves, and one placed by hand whose place it takes goes where the trait
    was, if it can. A Path merit's conversion has no places to choose: placing it
    puts it back on the Path, fitted."""
    ensure_fitted(npc)
    row = row_for(db, npc, category, name, detail)
    trait = row.trait
    was = trait.grant_place if trait.place_grant == grant else None
    unfit(db, npc)
    rules = rules_for(db, npc)
    found = givings(rules, sheet_rows(db, npc)).get(grant)
    if found is None:
        raise unprocessable(f"{npc.name} holds no merit that places those free dots.")
    if not found.takes(row):
        raise unprocessable(f"{found.merit} gives no free dots to {name}.")
    swapped: CharacterTrait | None = None
    if replacing is not None:
        other = row_for(db, npc, category, *replacing)
        if (
            other.trait.place_by == STAFF
            and other.trait.place_grant == grant
            and other.trait is not trait
        ):
            drop_place(other.trait)
            swapped = other.trait
    if trait.grant_place is not None:
        drop_place(trait)
    if trait.place_by == OFF:
        trait.place_by = None
    db.flush()
    if found.converts:
        fit(db, npc)
        audit.record(
            db,
            staff,
            "npc.place_placed",
            troupe_id=npc.owner_troupe_id,
            character_id=npc.id,
            name=f"{name}: {detail}" if detail else name,
            merit=found.merit,
        )
        return
    rows = sheet_rows(db, npc)
    if amount is None or amount not in found.amounts:
        raise unprocessable(
            f"{found.merit} places {', '.join(map(str, found.amounts))}: say which."
        )
    if found.left(rows)[amount] < 1:
        raise conflict(
            f"{found.merit}'s place of {amount} is set by hand on another trait: take it off first."
        )
    if any(
        r.trait.place_grant == grant and r.definition.name == name and r.trait is not trait
        for r in rows
    ):
        raise unprocessable(f"{found.merit} places dots on {name} once.")
    held = trait.rating or 0
    if held < amount:
        raise unprocessable(f"{name} is rated {held}, below a place of {amount}.")
    if trait.creation_pick is not None or trait.free_rating or trait.granted_rating:
        raise unprocessable(f"{name}'s dots are free already, so it takes no place.")
    place_on(trait, amount, grant, STAFF)
    db.flush()
    if swapped is not None and was is not None and was != amount:
        rows = sheet_rows(db, npc)
        back = next((r for r in rows if r.trait is swapped), None)
        if (
            back is not None
            and found.left(rows)[was] > 0
            and (swapped.rating or 0) >= was
            and not (swapped.creation_pick is not None or swapped.free_rating)
            and not swapped.granted_rating
        ):
            place_on(swapped, was, grant, STAFF)
            db.flush()
    fit(db, npc)
    audit.record(
        db,
        staff,
        "npc.place_placed",
        troupe_id=npc.owner_troupe_id,
        character_id=npc.id,
        name=f"{name}: {detail}" if detail else name,
        merit=found.merit,
        place=amount,
    )


def take_place_off(
    db: Session, staff: User, npc: Character, category: str, name: str, detail: str
) -> None:
    """Take a merit's place off a trait, and keep the fitting from giving it one;
    the place goes where else it fits best."""
    ensure_fitted(npc)
    unfit(db, npc)
    trait = row_for(db, npc, category, name, detail).trait
    if trait.grant_place is not None:
        drop_place(trait)
    trait.place_by = OFF
    db.flush()
    fit(db, npc)
    audit.record(
        db,
        staff,
        "npc.place_taken_off",
        troupe_id=npc.owner_troupe_id,
        character_id=npc.id,
        name=f"{name}: {detail}" if detail else name,
    )


def refit(db: Session, staff: User, npc: Character) -> None:
    """Forget what staff set, and fit every pick and place again."""
    ensure_fitted(npc)
    for trait in db.scalars(select(CharacterTrait).where(CharacterTrait.character_id == npc.id)):
        if trait.pick_by == STAFF:
            drop(trait)
        elif trait.pick_by == OFF:
            trait.pick_by = None
        if trait.place_by == STAFF:
            drop_place(trait)
        elif trait.place_by == OFF:
            trait.place_by = None
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
    # For a merit's places: the grant's key and the merit that holds it.
    grant: str | None = None
    merit: str | None = None


@dataclass(frozen=True)
class KeptOff:
    category: str
    name: str
    detail: str
    # What was taken off it: a creation pick, or a merit's place.
    kind: str  # pick | place


@dataclass(frozen=True)
class Picks:
    fitted: bool
    pools: list[PoolView]
    # Traits staff took a pick or a place off, which the fitting leaves alone.
    kept_off: list[KeptOff]


def view(db: Session, npc: Character) -> Picks:
    """The NPC's creation picks, pool by pool, and where else each could go; then
    the places its merits give, a pool for each amount."""
    if npc.kind != "npc" or npc.npc_form != "sheeted":
        return Picks(False, [], [])
    rules = rules_for(db, npc)
    rows = sheet_rows(db, npc)
    placed = pools_for(rules.creation_rules(), rows)
    every = [*placed.values(), *stray_pools(rules.creation_rules(), rows, placed)]
    fits = Fitting(db, npc)
    order = list(rules.rule_set.categories)
    ordered = sorted(rows, key=lambda r: (r.definition.name, r.trait.detail))

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

    def category_name(key: str) -> str:
        return rules.rule_set.categories[key].name

    pools = [
        PoolView(
            category=pool.category,
            category_name=category_name(pool.category),
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
                for r in ordered
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
    for found in givings(rules, rows).values():
        here = [r for r in ordered if found.takes(r)]
        if found.converts:
            # A pool for the Path on the sheet, at what converting gives it.
            amounts = {found.amount_for(r, found.amounts[0]): 1 for r in here if r.trait.rating}
        else:
            amounts = Counter(found.amounts)
        for amount, allowed in amounts.items():
            pools.append(
                PoolView(
                    category=found.category,
                    category_name=category_name(found.category),
                    kind="picks",
                    rating=amount,
                    allowed=allowed,
                    placed=[
                        Placed(
                            r.definition.name,
                            r.trait.detail,
                            r.trait.grant_place or 0,
                            r.trait.place_by or STAFF,
                        )
                        for r in here
                        if r.trait.place_grant == found.key
                        and (found.converts or r.trait.grant_place == amount)
                    ],
                    candidates=[
                        Candidate(r.definition.name, r.trait.detail, r.trait.rating or 0)
                        for r in here
                        if found.could_take(r, amount)
                    ],
                    grant=found.key,
                    merit=found.merit,
                )
            )
    kept_off = [
        KeptOff(r.category.key, r.definition.name, r.trait.detail, kind)
        for r in rows
        for kind, by in (("pick", r.trait.pick_by), ("place", r.trait.place_by))
        if by == OFF
    ]
    return Picks(fitted(npc), pools, kept_off)


def hand_over_places(db: Session, npc: Character) -> None:
    """Make the places the NPC's merits give its own, as a player's choices are,
    for it is given to a player: each merit's choices (`CharacterTrait.choices`),
    the biggest place first, with the dots they place left free on their traits.
    A Path keeps its free dots, as converting it would have."""
    rows = sheet_rows(db, npc)
    for found in givings(rules_for(db, npc), rows).values():
        if found.converts:
            continue
        chosen = sorted(
            (r for r in rows if r.trait.place_grant == found.key and r.trait.grant_place),
            key=lambda r: -(r.trait.grant_place or 0),
        )
        merit = next(
            (r for r in rows if (r.category.key, r.definition.name) == source_of(found.grant)),
            None,
        )
        if merit is None or not chosen:
            continue
        merit.trait.choices = [
            *merit.trait.choices,
            *(
                {
                    "grant": found.key,
                    "name": r.definition.name,
                    "detail": r.trait.detail,
                    "amount": r.trait.grant_place,
                }
                for r in chosen
            ),
        ]
    for row in rows:
        row.trait.grant_place = None
        row.trait.place_grant = None
        row.trait.place_by = None
    db.flush()


def source_of(grant: GrantData) -> tuple[str, str]:
    return (grant.source["category"], grant.source["name"])


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
