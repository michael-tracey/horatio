"""Character sheets: traits, purchases and XP.

The sheet as it stands lives in `character_traits`, and its player edits it
freely. Every rated change is a purchase in the XP history, priced by the
character's troupe rules (its home troupe's, or the plain rule set before it
has one). When a troupe accepts the character as its home, the sheet is frozen
as a `sheet_version`: the player may lower ratings back down to that, undoing
purchases since, but taking away accepted dots is a storyteller's business.

Once the character has a home troupe, every discipline dot it buys waits on
that troupe's staff: the XP is spent at once and refunded if they decline.
Only a home troupe request locks the sheet, so the differences it settles stay
the differences there are.

A trait can also be held by exception (horatio.trait_exceptions): asked of the
home troupe's staff, or given by them, it sets aside the checks it names for
that trait alone, and `sheet_violations` leaves them out.
"""

import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, true
from sqlalchemy.orm import Session

from horatio import audit, notifications, repricing, xp_range
from horatio.models import (
    Approval,
    Character,
    CharacterTrait,
    DisciplinePurchase,
    RuleSet,
    SheetVersion,
    TraitCategory,
    TraitDefinition,
    TraitException,
    Troupe,
    TroupeMembership,
    User,
    XpEntry,
)
from horatio.rules.checks import Context, Violation, traits_in, violations
from horatio.rules.conditions import describe as describe_condition
from horatio.rules.grants import Effects, choices, effects, raised_by
from horatio.rules.model import FreeChoice, RuleSetData, SheetTrait, TroupeRules
from horatio.rules.pricing import (
    NotAllowed,
    PricingError,
    Quote,
    fixed_rating,
    points,
    purchase_cost,
    trait_cost,
)
from horatio.rules.splats import SPLATS
from horatio.rules.store import read_troupe_rules

if TYPE_CHECKING:
    from horatio.diablerie import Adjust

TraitKey = tuple[str, str, str]  # category, name, detail

# Categories whose every dot, once the character has a home troupe, waits on its staff.
NEEDS_HOME_APPROVAL = frozenset({"disciplines"})

# Approvals that hold dots on the sheet until decided: declining or withdrawing
# takes them back and refunds the XP.
HELD_KINDS = ("discipline", "review", "exception")

FINISH_CREATION_FIRST = (
    "Build the character in the creation wizard first; "
    + "experience can be spent once it is finished."
)


def conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


class Unpriced(HTTPException):
    """The rules give no price for a change: a trait that cannot be bought, say."""

    def __init__(self, message: str) -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


@dataclass
class SheetRow:
    trait: CharacterTrait
    definition: TraitDefinition
    category: TraitCategory

    @property
    def key(self) -> TraitKey:
        return (self.category.key, self.definition.name, self.trait.detail)

    def as_rules_trait(self) -> SheetTrait:
        return SheetTrait(
            category=self.category.key,
            name=self.definition.name,
            rating=self.trait.rating,
            free_rating=self.trait.free_rating,
            detail=self.trait.detail,
            granted_rating=self.trait.granted_rating,
            choices=tuple(FreeChoice(**c) for c in self.trait.choices),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "category": self.category.key,
            "name": self.definition.name,
            "detail": self.trait.detail,
            "rating": self.trait.rating,
            "free_rating": self.trait.free_rating,
            "note": self.trait.note,
        }


def lock_character(db: Session, character_id: uuid.UUID) -> Character:
    """Lock the character's row for the rest of the transaction, so two purchases
    at once cannot both spend the same XP."""
    character = db.get(Character, character_id, with_for_update=True)
    assert character is not None
    return character


def rules_troupe(character: Character) -> uuid.UUID | None:
    """Whose rules the character plays by: its home troupe's, else the troupe it is
    being built for, else none (the plain rule set)."""
    return character.home_troupe_id or character.building_troupe_id


def rules_for(db: Session, character: Character) -> TroupeRules:
    return read_troupe_rules(db, character.splat, rules_troupe(character))


def sync_fixed_ratings(db: Session, character: Character) -> None:
    """Hold each fixed-rating merit and flaw at its value under the character's
    rules, after those rules change: a troupe's new price for it, or a new home or
    building troupe. Nothing is refunded or charged; purchases keep what they cost."""
    rules = rules_for(db, character)
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    for row in rows:
        value = fixed_rating(rules, sheet, row.category.key, row.definition.name)
        trait = row.trait
        if value is None or not trait.rating or trait.rating == value:
            continue
        trait.rating = value
        trait.free_rating = min(trait.free_rating, value)
        trait.granted_rating = min(trait.granted_rating, value)
        if trait.creation_pick is not None:
            trait.creation_pick = min(trait.creation_pick, value)
    db.flush()


def held_at(db: Session, character: Character, category: str, name: str) -> int | None:
    """The rating the character holds a merit or flaw at (pricing.fixed_rating)."""
    sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
    return fixed_rating(rules_for(db, character), sheet, category, name)


def sync_troupe_fixed_ratings(db: Session, troupe_id: uuid.UUID) -> None:
    """`sync_fixed_ratings` for every character playing by the troupe's rules."""
    for character in db.scalars(
        select(Character).where(
            (Character.home_troupe_id == troupe_id)
            | (Character.home_troupe_id.is_(None) & (Character.building_troupe_id == troupe_id))
        )
    ):
        sync_fixed_ratings(db, character)


def sheet_rows(db: Session, character: Character) -> list[SheetRow]:
    rows = db.execute(
        select(CharacterTrait, TraitDefinition, TraitCategory)
        .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(CharacterTrait.character_id == character.id)
        .order_by(TraitCategory.position, TraitDefinition.name, CharacterTrait.detail)
    )
    return [SheetRow(t, d, c) for t, d, c in rows]


def memberships(db: Session, character: Character) -> list[TroupeMembership]:
    """The troupes the character is in now."""
    return list(
        db.scalars(
            select(TroupeMembership)
            .where(
                TroupeMembership.character_id == character.id, TroupeMembership.left_at.is_(None)
            )
            .order_by(TroupeMembership.joined_at)
        )
    )


def membership(db: Session, character: Character, troupe_id: uuid.UUID) -> TroupeMembership | None:
    return next((m for m in memberships(db, character) if m.troupe_id == troupe_id), None)


def approved_snapshot(
    db: Session, character: Character, troupe_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    """The sheet as `troupe_id` last approved it; empty if it never has."""
    found = membership(db, character, troupe_id) if troupe_id else None
    if found is None or found.approved_version_id is None:
        return []
    return db.get_one(SheetVersion, found.approved_version_id).snapshot


def approved_ratings(
    db: Session, character: Character, troupe_id: uuid.UUID | None
) -> dict[TraitKey, int | None]:
    return {
        (t["category"], t["name"], t["detail"]): t["rating"]
        for t in approved_snapshot(db, character, troupe_id)
    }


def accepted_ratings(db: Session, character: Character) -> dict[TraitKey, int]:
    """The lowest each trait can go: its rating when the home troupe accepted the
    character, or a discipline dot the home troupe has approved since."""
    floor: dict[TraitKey, int] = {}
    if character.home_troupe_id is None:
        return floor
    for key, rating in approved_ratings(db, character, character.home_troupe_id).items():
        floor[key] = rating or 0
    found = membership(db, character, character.home_troupe_id)
    accepted_at = (
        db.get_one(SheetVersion, found.approved_version_id).approved_at
        if found is not None and found.approved_version_id is not None
        else None
    )
    query = (
        select(
            TraitCategory.key,
            TraitDefinition.name,
            DisciplinePurchase.detail,
            DisciplinePurchase.to_rating,
        )
        .join(Approval, DisciplinePurchase.approval_id == Approval.id)
        .join(TraitDefinition, DisciplinePurchase.trait_definition_id == TraitDefinition.id)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .where(
            Approval.character_id == character.id,
            Approval.troupe_id == character.home_troupe_id,
            Approval.status == "approved",
        )
    )
    if accepted_at is not None:
        query = query.where(Approval.decided_at >= accepted_at)
    for category, name, detail, rating in db.execute(query):
        floor[(category, name, detail)] = max(floor.get((category, name, detail), 0), rating)
    # A trait staff gave by exception, like dots they approved.
    for row, exception in held_by_exception(db, character):
        if exception.given_at is not None and (
            accepted_at is None or exception.given_at >= accepted_at
        ):
            floor[row.key] = max(floor.get(row.key, 0), exception.rating)
    return floor


def pending_disciplines(
    db: Session, character: Character
) -> list[tuple[Approval, DisciplinePurchase]]:
    rows = db.execute(
        select(Approval, DisciplinePurchase)
        .join(DisciplinePurchase, DisciplinePurchase.approval_id == Approval.id)
        .where(Approval.character_id == character.id, Approval.status == "pending")
        .order_by(Approval.id)
    )
    return [(a, d) for a, d in rows]


def xp_balance(db: Session, character: Character) -> int:
    return (
        db.scalar(
            select(func.coalesce(func.sum(XpEntry.amount), 0)).where(
                XpEntry.character_id == character.id
            )
        )
        or 0
    )


def pending_approvals(db: Session, character: Character, kind: str | None = None) -> list[Approval]:
    query = select(Approval).where(
        Approval.character_id == character.id, Approval.status == "pending"
    )
    if kind is not None:
        query = query.where(Approval.kind == kind)
    return list(db.scalars(query.order_by(Approval.id)))


def ensure_unlocked(db: Session, character: Character) -> None:
    if character.status == "retired":
        raise conflict("This character is retired.")
    if pending_approvals(db, character, "home_troupe_change"):
        raise conflict("A home troupe request is waiting. Withdraw it to edit the sheet.")


def find_definition(
    db: Session, character: Character, category_key: str, name: str
) -> tuple[TraitDefinition, TraitCategory]:
    found = db.execute(
        select(TraitDefinition, TraitCategory)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .where(
            RuleSet.splat == character.splat,
            TraitCategory.key == category_key,
            TraitDefinition.name == name,
        )
    ).first()
    if found is None:
        raise unprocessable(f"There is no {category_key} trait called {name!r}.")
    return found[0], found[1]


def check_context(
    db: Session,
    character: Character,
    sheet: Sequence[SheetTrait],
    priced: Iterable[tuple[str, str, str | None]] | None = None,
) -> Context:
    """What checks know beyond the sheet. `priced` is what the sheet's grants price
    as in-clan, where the caller has it already."""
    rules = rules_for(db, character)
    # Paths a merit prices as in-clan (Thaumaturgic Expertise) count as in-clan here.
    if priced is None:
        priced = effects(rules.rule_set.grants, sheet, rules.rule_set).in_clan_priced
    native = frozenset(SPLATS[character.splat].in_clan(rules, sheet))
    return Context(
        accepted=character.home_troupe_id is not None,
        in_clan=native | {f"{name}: {detail}" if detail else name for _, name, detail in priced},
        native=native,
        primary=primary_set(character, native),
        kinds=rules.rule_set.kinds,
    )


def primary_set(character: Character, native: frozenset[str]) -> frozenset[str]:
    """The paths that are primary: the ones the player named, and for each other
    discipline the clan's in-clan path, which is primary until another is named."""
    named = character.primary_paths
    return frozenset(named.values()) | {n for n in native if n.split(": ")[0] not in named}


def path_disciplines(rules: TroupeRules) -> list[str]:
    """Disciplines learned as paths with a primary path the others cannot go
    above, as the troupe's checks say: "Thaumaturgy"."""
    found: list[str] = []
    for check in rules.checks():
        for condition in (check.requires, check.forbids):
            test = (condition or {}).get("above_in_clan")
            if test and test.get("name_prefix"):
                found.append(test["name_prefix"].removesuffix(": ").strip())
    return sorted(set(found))


@dataclass(frozen=True)
class PrimaryPath:
    discipline: str
    # The primary path: the one the player named, else the clan's in-clan one.
    path: str | None
    # Whether that is the clan's in-clan path.
    native: bool
    # The clan's in-clan path of the discipline, if the character holds it.
    default: str | None
    # Where the player names it: the paths held, highest first.
    options: list[str]


def primary_paths(db: Session, character: Character) -> list[PrimaryPath]:
    """For each path discipline the character has paths in, which is primary."""
    rules = rules_for(db, character)
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    native = check_context(db, character, sheet).native
    found: list[PrimaryPath] = []
    for discipline in path_disciplines(rules):
        held = sorted(
            (
                t
                for t in sheet
                if t.category == "disciplines" and t.name.startswith(f"{discipline}: ")
            ),
            key=lambda t: (-(t.rating or 0), t.name),
        )
        held = [t for t in held if t.rating]
        if not held:
            continue
        in_clan_path = next((t.name for t in held if t.name in native), None)
        named = character.primary_paths.get(discipline)
        path = named if named in {t.name for t in held} else in_clan_path
        found.append(
            PrimaryPath(
                discipline,
                path,
                native=path is not None and path == in_clan_path,
                default=in_clan_path,
                options=[t.name for t in held],
            )
        )
    return found


def name_primary_path(
    db: Session, user: User, character: Character, discipline: str, path: str | None
) -> None:
    """Name the character's primary path of a discipline; None un-names it, and the
    clan's in-clan path, if any, is primary again. The primary is the first path to
    reach 2 dots, so no other path may be higher than it (MET: VTM p. 187); a clan's
    in-clan path is only the default (p. 172, p. 187)."""
    current = {p.discipline: p for p in primary_paths(db, character)}
    if discipline not in path_disciplines(rules_for(db, character)):
        raise unprocessable(f"{discipline} has no primary path.")
    chosen = current.get(discipline)
    if path is not None:
        if chosen is None or path not in chosen.options:
            raise unprocessable(f"Name a path of {discipline} the character has.")
        rating = {r.definition.name: r.trait.rating or 0 for r in sheet_rows(db, character)}
        higher = next((p for p in chosen.options if rating[p] > rating[path]), None)
        if higher is not None:
            raise conflict(
                f"{higher} is higher; no path can go above the primary path, "
                "so name the highest (p. 187)."
            )
    if chosen is not None and path == chosen.default:
        path = None
    named = {k: v for k, v in character.primary_paths.items() if k != discipline}
    character.primary_paths = {**named, discipline: path} if path else named
    db.flush()
    audit.record(
        db,
        user,
        "sheet.primary_path",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        discipline=discipline,
        path=path or "none",
    )


def held_by_exception(db: Session, character: Character) -> list[tuple[SheetRow, TraitException]]:
    """The character's traits held by exception, with their exceptions, oldest first."""
    rows = {r.trait.id: r for r in sheet_rows(db, character)}
    return [
        (rows[e.character_trait_id], e)
        for e in db.scalars(
            select(TraitException)
            .where(TraitException.character_id == character.id)
            .order_by(TraitException.created_at, TraitException.id)
        )
        if e.character_trait_id in rows
    ]


def excepted_checks(db: Session, character: Character) -> dict[tuple[str, str, str, str], int]:
    """The checks exceptions set aside, as violation keys (check, category, name,
    detail), each with the highest rating it is set aside up to."""
    found: dict[tuple[str, str, str, str], int] = {}
    for row, exception in held_by_exception(db, character):
        for check in exception.checks:
            key = (check["key"], *row.key)
            found[key] = max(found.get(key, 0), exception.rating)
    return found


def sheet_violations(db: Session, character: Character) -> list[Violation]:
    """The checks the character's sheet breaks now, but for those an exception
    sets aside for its trait, at up to the rating it was given at."""
    sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
    context = check_context(db, character, sheet)
    found = violations(rules_for(db, character).checks(), sheet, context)
    excepted = excepted_checks(db, character)
    return [v for v in found if (v.subject.rating or 0) > excepted.get(v.key, -1)]


def blocking(violation: Violation, character: Character) -> bool:
    """Whether a broken check stops a change: refuse checks always; complete
    checks once the character's creation is finished."""
    strength = violation.check.strength
    return strength == "refuse" or (
        strength == "complete" and character.creation_completed_at is not None
    )


# Stands in for the detail a player will give, when asking whether a trait can be taken.
FIELD_TO_BE_CHOSEN = "(to be chosen)"


@dataclass(frozen=True)
class Refusal:
    """Why a trait cannot be taken, and the traits held elsewhere on the sheet that
    the refusing check looks at, as (category, name): Archaic's Computer on Skills,
    or the clan a clan merit is not for."""

    message: str
    because: tuple[tuple[str, str], ...] = ()


def unavailable(
    db: Session,
    character: Character,
    category_key: str,
    as_if: str = "sheet",
    picks: Sequence[str] = (),
    planned: Sequence[SheetTrait] | None = None,
) -> dict[str, str]:
    """For each trait in a category the character does not hold, why it cannot be
    taken (`refusals`, by message alone)."""
    found = refusals(db, character, category_key, as_if, picks, planned)
    return {name: refusal.message for name, refusal in found.items()}


def refusals(
    db: Session,
    character: Character,
    category_key: str,
    as_if: str = "sheet",
    picks: Sequence[str] = (),
    planned: Sequence[SheetTrait] | None = None,
    at: int | None = None,
) -> dict[str, Refusal]:
    """For each trait in a category the character does not hold, why a check would
    refuse it, or the troupe's costs say it cannot be bought, if either would. A
    merit or flaw is tried at its point value, a ritual at its level, anything else
    at 1 dot.

    `as_if` "picks" first puts `picks` in place of the category's creation picks (the
    wizard's ticks before they are saved); "empty" first takes everything in the
    category away, leaving what no choice there could make allowed. Neither looks
    at costs, as creation picks are free. `planned` is the sheet to judge in place
    of the saved one: as a cart's changes would leave it.

    With `at`, each trait of a rated category is tried at that rating, those held too
    (in place of what they are now): where a pick of that many dots clashes, such as
    Generation 3 for a Thin Blooded vampire."""
    rules = rules_for(db, character)
    rule_set = rules.rule_set
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows] if planned is None else list(planned)
    if as_if == "empty":
        sheet = [t for t in sheet if t.category != category_key]
    elif as_if == "picks":
        picked = {
            r.definition.name
            for r in rows
            if r.category.key == category_key and r.trait.creation_pick is not None
        }
        sheet = [t for t in sheet if not (t.category == category_key and t.name in picked)]
        held_now = {t.name for t in sheet if t.category == category_key}
        sheet += [
            SheetTrait(
                category=category_key,
                name=name,
                rating=fixed_rating(rules, sheet, category_key, name) or 1,
                free_rating=0,
            )
            for name in dict.fromkeys(picks)
            if (category_key, name) in rule_set.traits and name not in held_now
        ]
    held = {t.name for t in sheet if t.category == category_key}
    checks = rules.checks()
    context = check_context(db, character, sheet)
    # Trying a trait no grant gives from or looks at leaves the grants as they are,
    # so their answer for the sheet serves every such trial (grants are slow to redo).
    grants = rule_set.grants
    priced = effects(grants, sheet, rule_set).in_clan_priced
    moves_grants = {(g.source["category"], g.source["name"]) for g in grants} | {
        key for g in grants for key in traits_in(g.when)
    }
    before = {v.key for v in violations(checks, sheet, context)}
    # Nor can a trial break a check that neither is about the category nor looks at
    # it, unless it changes what is in-clan; so only these need trying again.
    touching = [
        c
        for c in checks
        if c.category == category_key or any(key[0] == category_key for key in c.looks_at)
    ]
    rated = rule_set.categories[category_key].rated
    # Where the trial only adds a trait, only the checks about it, or that look at
    # it or its whole category, can change; each by its place in `touching`, so
    # they are tried in the same order.
    about_any = [i for i, c in enumerate(touching) if c.name is None]
    about_named: dict[str, list[int]] = {}
    looking: dict[tuple[str, str | None], list[int]] = {}
    for i, check in enumerate(touching):
        if check.name is not None:
            about_named.setdefault(check.name, []).append(i)
        for key in check.looks_at:
            looking.setdefault(key, []).append(i)
    reasons: dict[str, Refusal] = {}

    def because(violation: Violation, name: str) -> tuple[tuple[str, str], ...]:
        looks = violation.check.looks_at
        subject = violation.subject
        found = [
            (t.category, t.full_name)
            for t in sheet
            if t.category != category_key
            and t.rating != 0
            and ((t.category, t.name) in looks or (t.category, None) in looks)
        ]
        # The trait the check is about, held elsewhere, bars this one too (Archaic bars
        # Computer): it is the cause, though the check does not look at it.
        if subject.name != name and any(
            t.category == subject.category and t.name == subject.name and t.category != category_key
            for t in sheet
        ):
            found.append((subject.category, subject.full_name))
        return tuple(dict.fromkeys(found))

    for category, name in rule_set.traits:
        if category != category_key or (name in held and at is None):
            continue
        trying = touching
        if rated:
            places = {
                *about_any,
                *about_named.get(name, ()),
                *looking.get((category, name), ()),
                *looking.get((category, None), ()),
            }
            trying = [touching[i] for i in sorted(places)]
        rating = (at or fixed_rating(rules, sheet, category, name) or 1) if rated else None
        # The detail is chosen when the trait is added, so a trait refused only for
        # lacking one (Performance needs a field, p. 92) is tried again with one.
        new: list[Violation] = []
        for detail in ("", FIELD_TO_BE_CHOSEN):
            candidate = SheetTrait(
                category=category, name=name, detail=detail, rating=rating, free_rating=0
            )
            trial = [
                t
                for t in sheet
                if (rated or t.category != category)
                and not (at is not None and t.category == category and t.name == name)
            ] + [candidate]
            trial_context = check_context(
                db,
                character,
                trial,
                None if {(category, name), (category, None)} & moves_grants else priced,
            )
            same_clan = (trial_context.in_clan, trial_context.native) == (
                context.in_clan,
                context.native,
            )
            new = [
                v
                for v in violations(trying if same_clan else checks, trial, trial_context)
                if blocking(v, character) and v.key not in before
            ]
            if not new:
                break
        if new:
            # The trait's own problem first: "Talisman is already…" when trying Spellslinger.
            own = [v for v in new if v.subject.name == name]
            first = (own or new)[0]
            # Every holder is named, not only the first check's: a Thin Blooded flaw for a
            # Brujah is refused for the Generation and for the clan.
            holders = dict.fromkeys(h for v in new for h in because(v, name))
            reasons[name] = Refusal(first.message, tuple(holders))
        elif as_if == "sheet" and rating is not None and at is None:
            refused = not_for_sale(rules, sheet, category, name, rating)
            if refused is not None:
                reasons[name] = Refusal(refused)
    return reasons


def not_for_sale(
    rules: TroupeRules, sheet: Sequence[SheetTrait], category: str, name: str, rating: int
) -> str | None:
    """Why the troupe's costs say the character cannot buy this trait, if they do:
    a Luminary Discipline out-of-clan, say. Read from the rules that would let it
    be bought, where there is just one."""
    try:
        trait_cost(rules, sheet, SheetTrait(category=category, name=name, rating=rating))
    except NotAllowed:
        pass
    except PricingError:
        return None
    else:
        return None
    category_name = rules.rule_set.categories[category].name
    allowing = [
        r
        for r in [*rules.house_rules, *rules.rule_set.cost_rules]
        if r.category == category and r.trait in (None, name) and r.scheme != "not_allowed"
    ]
    words = (
        describe_condition(allowing[0].condition, SPLATS[rules.splat].fact_words)
        if len(allowing) == 1
        else None
    )
    if words:
        return f"{category_name} can be bought only {words}."
    return f"{category_name} cannot be bought by this character."


def sheet_effects(db: Session, character: Character) -> Effects:
    """What the sheet's grants do."""
    rule_set = rules_for(db, character).rule_set
    sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
    return effects(rule_set.grants, sheet, rule_set)


def convert(
    db: Session,
    character: Character,
    rules: TroupeRules,
    found: Effects,
    before: Mapping[tuple[str, str], str] | None = None,
) -> bool:
    """Bring conversions into line: a held Path merit turns Humanity into that
    Path, keeping its dots; without the merit the Path turns back into Humanity.
    Given what the grants wanted `before` a change (to an NPC, whose staff can
    choose its Path directly), only a conversion the change altered is made, and
    losing a merit turns back only the Path that merit gave. Says whether it
    converted anything."""
    targets: dict[tuple[str, str], set[str]] = {}
    for g in rules.rule_set.grants:
        if g.kind == "convert" and g.convert_from:
            possible = targets.setdefault(
                (g.convert_from["category"], g.convert_from["name"]), set()
            )
            possible.update(choices(g, rules.rule_set) or [g.target["name"]])
    changed = False
    rows = sheet_rows(db, character)
    for (category, origin), possible in targets.items():
        wanted = found.converts.get((category, origin), origin)
        current = next(
            (
                r
                for r in rows
                if r.category.key == category and r.definition.name in possible | {origin}
            ),
            None,
        )
        if current is None or current.definition.name == wanted:
            continue
        if before is not None:
            was = before.get((category, origin), origin)
            if wanted == was or (wanted == origin and current.definition.name != was):
                continue
        was = current.definition.name
        definition, _ = find_definition(db, character, category, wanted)
        current.trait.trait_definition_id = definition.id
        if character.kind == "pc" and character.creation_completed_at is None:
            restart_path(rules, current.trait, category, origin, was, wanted)
        changed = True
    db.flush()
    return changed


def path_start(rules: TroupeRules, category: str, origin: str) -> tuple[int, int] | None:
    """A character who takes a Path merit while being built starts on the Path lower
    than on `origin` (Humanity, 5): as (the Path's start, the origin's), or None if
    the rules say nothing of it (core p. 306)."""
    lower = rules.rule_set.trait_properties(category, origin).get("path_start")
    start = next(
        (s.rating for s in rules.starting_traits() if (s.category, s.name) == (category, origin)),
        None,
    )
    return None if lower is None or start is None else (lower, start)


def restart_path(
    rules: TroupeRules,
    trait: CharacterTrait,
    category: str,
    origin: str,
    was: str,
    now: str,
) -> None:
    """Taking a Path merit during creation lowers Morality's starting dots to the Path's
    start (4 instead of 5), and dropping it puts them back. Dots bought on top, or a
    Morality that was already moved, are left as they are."""
    starts = path_start(rules, category, origin)
    if starts is None or (was != origin) == (now != origin):
        return
    lower, usual = starts
    before, after = (usual, lower) if was == origin else (lower, usual)
    if trait.rating == before and trait.free_rating == before:
        trait.rating = trait.free_rating = after


# How many times granted traits may grant others in turn (Web of Knives gives
# the Path of Blood merit, which converts Humanity).
GRANT_DEPTH = 4


def apply_grants(
    db: Session,
    user: User,
    character: Character,
    converts_before: Mapping[tuple[str, str], str] | None = None,
) -> None:
    """Bring every granted trait into line with the grants the sheet now holds:
    add what new grants give, take back what lost grants gave (nothing refunded,
    MET: VTM p. 236), and refund dots a `free_up_to` grant now makes free. A
    merit or flaw is given whole, at its value. A granted trait can grant others,
    so this goes round until nothing changes."""
    for _ in range(GRANT_DEPTH):
        if not grant_once(db, user, character, converts_before):
            return


def grant_once(
    db: Session,
    user: User,
    character: Character,
    converts_before: Mapping[tuple[str, str], str] | None,
) -> bool:
    """One round of apply_grants. Says whether it changed anything."""
    rules = rules_for(db, character)
    changed = convert(db, character, rules, sheet_effects(db, character), converts_before)
    found = sheet_effects(db, character)
    sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
    for key in list(found.free_up_to):
        # A merit is held at its value, so giving it means giving all of it.
        whole = fixed_rating(rules, sheet, key[0], key[1])
        if whole is not None:
            found.free_up_to[key] = whole
    wanted: dict[TraitKey, tuple[int, int]] = {
        key: (amount, 0) for key, amount in found.added.items()
    }
    for key, amount in found.free_up_to.items():
        wanted[key] = (wanted.get(key, (0, 0))[0], amount)
    rows = {r.key: r for r in sheet_rows(db, character)}
    for key in set(wanted) | {k for k, r in rows.items() if r.trait.granted_rating}:
        added, free_up_to = wanted.get(key, (0, 0))
        row = rows.get(key)
        if row is None:
            if added <= 0 and free_up_to <= 0:
                continue
            definition, _ = find_definition(db, character, key[0], key[1])
            trait = CharacterTrait(
                character_id=character.id,
                trait_definition_id=definition.id,
                detail=key[2],
                rating=0,
                free_rating=0,
                granted_rating=0,
            )
            db.add(trait)
        else:
            trait = row.trait
        old = trait.granted_rating
        base_rating = (trait.rating or 0) - old
        base_free = trait.free_rating - old
        granted = added + max(0, free_up_to - base_free)
        # Dots the player bought inside the newly free range are refunded.
        bought = max(0, min(base_rating, free_up_to) - base_free)
        if bought:
            refund = trait_cost(
                rules,
                [],
                SheetTrait(key[0], key[1], base_free + bought, base_free, key[2]),
            ).cost
            definition, _ = find_definition(db, character, key[0], key[1])
            if refund:
                db.add(
                    XpEntry(
                        character_id=character.id,
                        kind="purchase",
                        amount=refund,
                        reason=f"{key[1]}: dots now free ({', '.join(found.sources.get(key, []))})",
                        entered_by=user.id,
                        trait_definition_id=definition.id,
                        detail=key[2] or None,
                        from_rating=base_free + bought,
                        to_rating=base_free,
                        cost_basis={"grant": found.sources.get(key, [])},
                    )
                )
            base_rating -= bought
        if granted == old and not bought:
            continue
        changed = True
        trait.rating = max(0, base_rating + granted)
        trait.free_rating = max(0, base_free + granted)
        trait.granted_rating = granted
        if trait.rating == 0 and trait.free_rating == 0 and trait.creation_pick is None:
            db.delete(trait)
    db.flush()
    return changed


def held_beyond_limit(db: Session, character: Character) -> dict[str, int]:
    """Categories where the character holds more (ungranted) traits than allowed."""
    over: dict[str, int] = {}
    for row in sheet_rows(db, character):
        limit = row.category.max_held
        if limit is None or not row.trait.rating or row.trait.granted_rating >= row.trait.rating:
            continue
        over[row.category.key] = over.get(row.category.key, 0) + 1
    return {
        key: count
        for key, count in over.items()
        if count > (rules_for(db, character).rule_set.categories[key].max_held or 0)
    }


def hold_for_review(
    db: Session,
    user: User,
    character: Character,
    violation: Violation,
    ratings_before: Mapping[TraitKey, int],
    xp_before: set[uuid.UUID],
) -> bool:
    """A change that breaks a review check goes ahead but waits on the home troupe,
    like a discipline dot: declining takes the dots back and refunds the XP.
    Whether it now waits: not for a trait lowered, or already waiting."""
    subject = violation.subject
    key = (subject.category, subject.name, subject.detail)
    before, after = ratings_before.get(key, 0), subject.rating or 0
    definition, _ = find_definition(db, character, subject.category, subject.name)
    if after <= before or any(
        d.trait_definition_id == definition.id and d.detail == subject.detail
        for _, d in pending_disciplines(db, character)
    ):
        return False
    spent = -sum(
        db.scalars(
            select(XpEntry.amount).where(
                XpEntry.character_id == character.id,
                XpEntry.trait_definition_id == definition.id,
                XpEntry.id.not_in(xp_before) if xp_before else true(),
            )
        )
    )
    assert character.home_troupe_id is not None
    approval = Approval(
        character_id=character.id,
        troupe_id=character.home_troupe_id,
        kind="review",
        requested_by=user.id,
        player_note=violation.message,
    )
    db.add(approval)
    db.flush()
    db.add(
        DisciplinePurchase(
            approval_id=approval.id,
            trait_definition_id=definition.id,
            detail=subject.detail,
            from_rating=before,
            to_rating=after,
            cost=spent,
        )
    )
    db.flush()
    audit.record(
        db,
        user,
        "approval.request",
        troupe_id=approval.troupe_id,
        character_id=character.id,
        approval_id=approval.id,
        kind="review",
        name=subject.name,
        rating=after,
    )
    notifications.approval_waiting(db, approval)
    return True


def selects(selector: Mapping[str, str], category: str, name: str) -> bool:
    """Whether a `creation_only` entry in the rules data is about this trait."""
    return (
        selector["category"] == category
        and (not selector.get("name") or selector["name"] == name)
        and name.startswith(selector.get("name_prefix", ""))
    )


def locks_at(
    rule_set: RuleSetData, category: str, name: str
) -> Literal["finished", "accepted"] | None:
    """When a trait chosen at creation only stops changing: once creation is
    "finished", or, for one marked `until = "accepted"`, once a first home troupe
    has "accepted" the character. None for any other trait."""
    found = [s for s in rule_set.creation_only if selects(s, category, name)]
    if not found:
        return None
    return "accepted" if all(s.get("until") == "accepted" for s in found) else "finished"


def fixed_once_accepted(name: str) -> str:
    return f"{name} can't change once a home troupe has accepted the character."


def ever_accepted(db: Session, character: Character) -> bool:
    """Whether a home troupe has ever accepted the character: it has entered play.
    Leaving that troupe, or moving to another, changes nothing."""
    if character.home_troupe_id is not None:
        return True
    found = select(SheetVersion.id).where(SheetVersion.character_id == character.id).limit(1)
    return db.scalar(found) is not None


def open_until_accepted(db: Session, character: Character, category: str, name: str) -> bool:
    """A trait chosen at creation only, but open until acceptance, that the player
    can still change with XP: creation is finished and no troupe has accepted the
    character yet (MET: VTM p. 99, Generation)."""
    return (
        character.kind == "pc"
        and character.creation_completed_at is not None
        and locks_at(rules_for(db, character).rule_set, category, name) == "accepted"
        and not ever_accepted(db, character)
    )


def creation_only_traits(db: Session, character: Character) -> dict[TraitKey, int | None]:
    """The character's traits that are chosen at creation only, with their ratings."""
    selectors = rules_for(db, character).rule_set.creation_only
    return {
        r.key: r.trait.rating
        for r in sheet_rows(db, character)
        if any(selects(s, r.category.key, r.definition.name) for s in selectors)
    }


@dataclass(frozen=True)
class SheetState:
    """What a sheet breaks and holds, to judge changes to it against."""

    broken: set[tuple[str, str, str, str]]
    over: dict[str, int]
    fixed: dict[TraitKey, int | None]
    ratings: dict[TraitKey, int]
    xp: set[uuid.UUID]
    # Traits whose grant needs a choice their detail does not make.
    unchosen: set[tuple[str, str, str, str]]


def unchosen_keys(db: Session, character: Character) -> set[tuple[str, str, str, str]]:
    return {(t.category, t.name, t.detail, g.key) for t, g in sheet_effects(db, character).unchosen}


def sheet_state(db: Session, character: Character) -> SheetState:
    return SheetState(
        broken={v.key for v in sheet_violations(db, character)},
        over=held_beyond_limit(db, character),
        fixed=creation_only_traits(db, character),
        ratings={r.key: r.trait.rating or 0 for r in sheet_rows(db, character)},
        xp=set(db.scalars(select(XpEntry.id).where(XpEntry.character_id == character.id))),
        unchosen=unchosen_keys(db, character),
    )


@dataclass(frozen=True)
class Problem:
    """Why a sheet is refused or held for review, and what on it that is about:
    a trait, or (with no name) a category holding too many."""

    message: str
    category: str
    name: str | None = None
    detail: str = ""
    # The traits the broken check looks at, as (category, name), with no name
    # for a whole category: a technique's disciplines.
    looks_at: frozenset[tuple[str, str | None]] = frozenset()


def problem(violation: Violation) -> Problem:
    subject = violation.subject
    return Problem(
        violation.message,
        subject.category,
        subject.name,
        subject.detail,
        violation.check.looks_at,
    )


@dataclass(frozen=True)
class Judgement:
    """What a change to a sheet newly breaks (`broken_since`)."""

    # The problems that refuse it.
    refused: list[Problem] = field(default_factory=list[Problem])
    # The review checks it now waits on.
    reviewed: list[Problem] = field(default_factory=list[Problem])
    # The checks it breaks on traits asked or given by exception, by trait: set
    # aside rather than refusing or waiting.
    excepted: dict[TraitKey, list[Violation]] = field(
        default_factory=dict[TraitKey, list[Violation]]
    )


def broken_since(
    db: Session,
    user: User | None,
    character: Character,
    before: SheetState,
    *,
    checks: bool = True,
    creation_only: bool = True,
    excepting: Iterable[TraitKey] = (),
) -> Judgement:
    """What a player's character's sheet breaks now that it did not `before`: the
    problems that refuse the change, and the review checks it now waits on, each
    raised as an approval if nothing else in the checks refuses it. `checks` judges
    the rule set's checks, how many traits a category holds, and grants left
    unchosen; `creation_only` judges traits only chosen during creation. A check a
    trait in `excepting` breaks, that would refuse or wait, is set aside for an
    exception instead."""
    db.expire_all()
    now_broken = (
        [v for v in sheet_violations(db, character) if v.key not in before.broken] if checks else []
    )
    asked = set(excepting)
    excepted: dict[TraitKey, list[Violation]] = {}
    for violation in now_broken:
        subject = violation.subject
        key = (subject.category, subject.name, subject.detail)
        waits = violation.check.strength == "review"
        if key in asked and (blocking(violation, character) or waits):
            excepted.setdefault(key, []).append(violation)
    set_aside = {v.key for found in excepted.values() for v in found}
    now_broken = [v for v in now_broken if v.key not in set_aside]
    refused = [problem(v) for v in now_broken if blocking(v, character)]
    reviewed: list[Problem] = []
    if user is not None and character.home_troupe_id is not None and not refused:
        for violation in now_broken:
            if violation.check.strength == "review" and hold_for_review(
                db, user, character, violation, before.ratings, before.xp
            ):
                reviewed.append(problem(violation))
    rule_set = rules_for(db, character).rule_set
    if checks:
        for key, count in held_beyond_limit(db, character).items():
            if count > before.over.get(key, 0):
                category = rule_set.categories[key]
                refused.append(
                    Problem(
                        f"A character holds {category.max_held} {category.name.lower()}; "
                        "only merits can grant more.",
                        key,
                    )
                )
    if creation_only:
        fixed_after = creation_only_traits(db, character)
        changed = {
            key
            for key in before.fixed.keys() | fixed_after.keys()
            if before.fixed.get(key, 0) != fixed_after.get(key, 0)
        }
        finished = character.creation_completed_at is not None
        accepted = ever_accepted(db, character) if changed else False
        for key in sorted(changed):
            locked = locks_at(rule_set, key[0], key[1])
            if locked == "accepted" and accepted:
                refused.append(Problem(fixed_once_accepted(key[1]), *key))
            elif locked == "finished" and finished:
                refused.append(
                    Problem(f"{key[1]} can only be chosen during character creation.", *key)
                )
    if checks:
        for trait, grant in sheet_effects(db, character).unchosen:
            # A trait held before its grant needed a choice is left be until changed.
            if (trait.category, trait.name, trait.detail, grant.key) in before.unchosen:
                continue
            options = choices(grant, rule_set)
            listed = ", ".join(options) if len(options) <= 8 else "the trait it applies to"
            refused.append(
                Problem(
                    f"Say which for {trait.name}: put {listed} in its detail.",
                    trait.category,
                    trait.name,
                    trait.detail,
                )
            )
    return Judgement(refused, reviewed, excepted)


def refusal(problems: Sequence[Problem]) -> str:
    return " ".join(dict.fromkeys(p.message for p in problems))


@contextmanager
def checked(
    db: Session, character: Character, user: User | None = None, *, rules: bool = True
) -> Iterator[None]:
    """Make a change to a sheet, then bring its grants into line and refuse the
    change if it breaks a check the sheet did not already break. The change is
    rolled back (to a savepoint taken before it) with the refusal. NPCs get their grants but are
    their staff's to build as they like. With `rules` False, the change is judged
    only on traits chosen during creation: a cart judges the rest once, against
    the sheet it ends with (`broken_since`)."""
    before = sheet_state(db, character)
    # An NPC's Path may be chosen directly, so only the conversions a change
    # alters are made.
    converts_before = sheet_effects(db, character).converts if character.kind != "pc" else None
    savepoint = db.begin_nested()
    try:
        yield
        db.flush()
    except BaseException:
        savepoint.rollback()
        raise
    if user is not None:
        apply_grants(db, user, character, converts_before)
    if character.kind != "pc":
        savepoint.commit()
        return
    refused = broken_since(db, user, character, before, checks=rules).refused
    if refused:
        savepoint.rollback()
        raise conflict(refusal(refused))
    savepoint.commit()


# The archetype a player makes up (p. 86): its detail is the name they give it, and
# its note says what it means for the character.
CUSTOM_ARCHETYPE = ("archetype", "Other…")


def replace_choice(
    db: Session,
    character: Character,
    definition: TraitDefinition,
    category: TraitCategory,
    detail: str,
) -> CharacterTrait:
    """Make `definition` the character's choice in an unrated category such as a
    clan or sect. A choice that needs another one (a faction needs the Sabbat
    sect) is refused without it, and choices that no longer hold are dropped."""
    rows = sheet_rows(db, character)
    chosen = {(r.category.key, r.definition.name) for r in rows if r.category.id != category.id}
    chosen.add((category.key, definition.name))

    def met(needed: TraitCategory) -> bool:
        return not needed.requires or (
            (needed.requires["category"], needed.requires["name"]) in chosen
        )

    if not met(category):
        assert category.requires is not None
        raise unprocessable(f"Only a {category.requires['name']} character has a {category.name}.")
    for row in rows:
        if row.category.id == category.id or not met(row.category):
            db.delete(row.trait)
    db.flush()
    trait = CharacterTrait(
        character_id=character.id, trait_definition_id=definition.id, rating=None, detail=detail
    )
    db.add(trait)
    return trait


def start_character(db: Session, player: User, character: Character) -> None:
    """Give a new character its starting XP: the XP floor of the troupe it is built
    for, or the rule set's starting XP when it is built in its player's vault."""
    reason = "Starting experience"
    if character.building_troupe_id is not None:
        troupe = db.get_one(Troupe, character.building_troupe_id)
        starting_xp = xp_range.figures(db, troupe).floor
        reason = f"Starting experience: {troupe.name}'s XP floor"
    else:
        starting_xp = db.scalar(select(RuleSet.starting_xp).where(RuleSet.splat == character.splat))
    if starting_xp:
        db.add(
            XpEntry(
                character_id=character.id,
                kind="award",
                amount=starting_xp,
                reason=reason,
                entered_by=player.id,
            )
        )


@dataclass
class Change:
    # What it cost; None for an unrated trait, or one given free.
    quote: Quote | None
    trait: CharacterTrait | None
    # Given free: what it would have cost, where the rules price it.
    normal_cost: int | None = None
    # Earlier purchases it repriced (horatio.repricing), each with its own XP line.
    repriced: tuple[repricing.Repriced, ...] = ()

    @property
    def repricing_cost(self) -> int:
        return sum(r.cost for r in self.repriced)


# How a change is made by exception (horatio.trait_exceptions): "asked" of the home
# troupe's staff, waiting on an exception approval rather than any other; or
# "given" by them, waiting on nothing.
ByException = Literal["asked", "given"] | None


def quote_change(
    db: Session,
    character: Character,
    category_key: str,
    name: str,
    detail: str,
    rating: int | None,
) -> tuple[Quote | None, int | None]:
    """What setting this trait to `rating` would cost, without doing it.
    Returns the quote (None for unrated traits) and the current rating."""
    definition, category = find_definition(db, character, category_key, name)
    rows = sheet_rows(db, character)
    current = next(
        (r for r in rows if r.definition.id == definition.id and r.trait.detail == detail), None
    )

    if not category.rated:
        if rating is not None:
            raise unprocessable(f"{category.name} has no rating.")
        return None, None
    if category.derived:
        raise unprocessable(
            f"{category.name} come from the rest of the sheet; "
            "merits, flaws and powers change them."
        )

    if rating is None:
        raise unprocessable(f"{category.name} needs a rating.")
    fixed = fixed_rating(
        rules_for(db, character), [r.as_rules_trait() for r in rows], category.key, definition.name
    )
    if fixed is not None and rating not in (0, fixed):
        raise unprocessable(f"{name} is always rated {fixed}.")

    current_rating = (current.trait.rating or 0) if current else 0
    current_free = current.trait.free_rating if current else 0
    if rating < current_free:
        raise unprocessable("A rating cannot go below its free dots.")
    if category.usual_max is not None and rating > current_rating:
        highest = category.usual_max + raised_by(
            sheet_effects(db, character), category.key, definition.name, detail
        )
        if rating > highest:
            raise unprocessable(f"{name} cannot go above {highest}.")

    sheet = [r.as_rules_trait() for r in rows]
    before = SheetTrait(
        category=category.key,
        name=definition.name,
        rating=current_rating,
        free_rating=current_free,
        detail=detail,
    )
    try:
        quote = purchase_cost(rules_for(db, character), sheet, before, rating)
    except PricingError as error:
        raise Unpriced(str(error)) from error
    return quote, current_rating


def chosen_during_creation(db: Session, character: Character, category: TraitCategory) -> bool:
    """Free traits no creation pick covers, such as a Caitiff's in-clan disciplines,
    are chosen during creation like a clan."""
    rules = rules_for(db, character)
    if any(r.category == category.key for r in rules.creation_rules()):
        return False
    return all(
        r.scheme == "free" for r in rules.rule_set.cost_rules if r.category == category.key
    ) and any(r.category == category.key for r in rules.rule_set.cost_rules)


def owed_for(
    db: Session, character: Character, category: TraitCategory, gained: int, fixed: bool
) -> int:
    """Downtime actions gaining `gained` dots in `category` costs the character: per
    dot, or once for a trait bought whole (a merit)."""
    if not category.downtime_actions or gained <= 0 or character.home_troupe_id is None:
        return 0
    rows = sheet_rows(db, character)
    for waiver in category.downtime_waived_by:
        if any(
            r.category.key == waiver["category"] and r.definition.name == waiver["name"]
            for r in rows
        ):
            return 0
    return category.downtime_actions * (1 if fixed else gained)


def owe(db: Session, user: User, character: Character, amount: int, reason: str) -> None:
    from horatio.downtimes import owe_actions  # imports this module

    owe_actions(db, user, character, amount, reason)


def held_points(
    db: Session, character: Character, category_key: str, leave_out: TraitKey | None = None
) -> int:
    """The points the character holds in a category, as its troupe prices them.
    A merit another trait gives is not counted: the character did not buy it."""
    rules = rules_for(db, character)
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    return sum(
        points(rules, sheet, trait)
        for r, trait in zip(rows, sheet, strict=True)
        if r.category.key == category_key and r.key != leave_out and not trait.granted
    )


def within_points_limit(
    db: Session,
    character: Character,
    category: TraitCategory,
    definition: TraitDefinition,
    detail: str,
    rating: int,
    quote: Quote,
) -> Quote:
    """Hold a purchase to its category's points limit. A category that costs XP
    (merits) refuses going over it; one that pays XP (flaws) pays nothing past it."""
    assert category.points_limit is not None
    key = (category.key, definition.name, detail)
    others = held_points(db, character, category.key, leave_out=key)
    rows = sheet_rows(db, character)
    current = next((r for r in rows if r.key == key), None)
    after = SheetTrait(
        category=category.key,
        name=definition.name,
        rating=rating,
        free_rating=current.trait.free_rating if current else 0,
        detail=detail,
    )
    worth = points(rules_for(db, character), [r.as_rules_trait() for r in rows], after)
    if quote.cost > 0 and others + worth > category.points_limit:
        raise conflict(
            f"That would bring {category.name.lower()} to {others + worth} points; "
            f"a character can hold at most {category.points_limit}."
        )
    if quote.cost < 0:
        payable = max(0, category.points_limit - others)
        return replace(quote, cost=-min(-quote.cost, payable))
    return quote


def set_trait(
    db: Session,
    player: User,
    character: Character,
    category_key: str,
    name: str,
    detail: str,
    rating: int | None,
    note: str | None = None,
    teacher: str = "",
    *,
    free: str | None = None,
    by_exception: ByException = None,
) -> Change:
    """Add a trait, change its rating, or (at rating 0) remove it, buying or
    refunding the difference. Unrated traits replace the category's choice.
    `teacher` names who teaches a discipline dot that waits on the home troupe.

    A raise `free` (the reason it is) costs nothing: its dots are free dots, and
    its line in the XP history is 0 XP, with the reason. One made `by_exception`
    never waits as a discipline dot, nor owes downtime actions for learning yet:
    an asked exception owes them when approved, and a given one at once, unless
    it is free."""
    ensure_unlocked(db, character)
    definition, category = find_definition(db, character, category_key, name)
    if rating:
        from horatio.specializations import check_choice  # imports this module

        check_choice(db, character, category, name, detail)

    if not category.rated:
        quote_change(db, character, category_key, name, detail, rating)  # validates
        if (category.key, name) == CUSTOM_ARCHETYPE and not detail.strip():
            raise unprocessable("Name the archetype.")
        trait = replace_choice(db, character, definition, category, detail)
        if note is not None:
            trait.note = note
        db.flush()
        audit.record(
            db, player, "sheet.choose", character_id=character.id, category=category.key, name=name
        )
        return Change(quote=None, trait=trait)

    if character.kind == "npc":
        raise conflict("Set an NPC's ratings directly; NPCs spend no experience.")
    if character.creation_completed_at is None and not chosen_during_creation(
        db, character, category
    ):
        raise conflict(FINISH_CREATION_FIRST)
    existing = db.scalar(
        select(CharacterTrait).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == detail,
        )
    )
    # Generation before acceptance: still creation, so earlier buys follow it.
    reopened = open_until_accepted(db, character, category.key, definition.name)
    # After it, fixed: said before what it would cost. Staff may still give it.
    if (
        by_exception is None
        and character.kind == "pc"
        and (rating or 0) != ((existing.rating or 0) if existing else 0)
        and locks_at(rules_for(db, character).rule_set, category.key, definition.name) == "accepted"
        and ever_accepted(db, character)
    ):
        raise conflict(fixed_once_accepted(name))
    if reopened and existing is not None and rating is not None and rating < existing.free_rating:
        raise conflict(
            f"{name} was chosen at {existing.free_rating} in character creation: "
            "only the dots bought with XP since can be taken back."
        )
    priced: Quote | None
    try:
        priced, current_rating = quote_change(db, character, category_key, name, detail, rating)
    except Unpriced:
        # Given free, it needs no price; staff are told it had none.
        if free is None:
            raise
        priced, current_rating = None, (existing.rating or 0) if existing else 0
    assert rating is not None and current_rating is not None
    if free is not None and rating <= current_rating:
        raise unprocessable("Only a trait added or raised can be free.")
    if priced is not None and category.points_limit is not None and rating > current_rating:
        priced = within_points_limit(db, character, category, definition, detail, rating, priced)
    quote = priced

    accepted = accepted_ratings(db, character).get((category.key, definition.name, detail), 0)
    if rating < accepted and category.buy_off_factor and rating == 0 and quote is not None:
        # Buying off an accepted flaw costs a multiple of what it gave (p. 236).
        held = SheetTrait(category.key, definition.name, current_rating, 0, detail)
        sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
        worth = points(rules_for(db, character), sheet, held)
        quote = Quote(cost=category.buy_off_factor * worth, rule=quote.rule)
    elif rating < accepted:
        raise conflict(
            f"{name} was accepted at {accepted}. Only storytellers can take accepted dots away."
        )
    if any(
        d.trait_definition_id == definition.id and d.detail == detail
        for _, d in pending_disciplines(db, character)
    ):
        raise conflict(
            f"{name} is waiting for the home troupe's approval. Withdraw that to change it."
        )
    cost = 0 if free is not None or quote is None else quote.cost
    repriced: list[repricing.Repriced] = []
    if reopened and rating != current_rating:
        rows = sheet_rows(db, character)
        sheet = [r.as_rules_trait() for r in rows]
        repriced = repricing.repricing(
            db,
            rules_for(db, character),
            character.id,
            sheet,
            repricing.with_rating(sheet, category.key, definition.name, detail, rating),
            {r.key: r.trait.free_rating for r in rows},
            definition.id,
        )
    total = cost + sum(r.cost for r in repriced)
    if total > 0 and xp_balance(db, character) < total:
        raise conflict(
            f"That costs {total} XP"
            + (", with earlier buys repriced" if repriced else "")
            + f", and the character has {xp_balance(db, character)}."
        )

    trait = existing
    if trait is None:
        trait = CharacterTrait(
            character_id=character.id, trait_definition_id=definition.id, rating=0, detail=detail
        )
        db.add(trait)
    if note is not None:
        trait.note = note

    held = (
        rating > current_rating
        and category.key in NEEDS_HOME_APPROVAL
        and character.home_troupe_id is not None
        and character.kind == "pc"
        and by_exception is None
    )
    if rating != current_rating and (cost != 0 or free is not None):
        db.add(
            XpEntry(
                character_id=character.id,
                kind="purchase",
                amount=-cost,
                reason=f"{name} {current_rating} → {rating}"
                + (f", free by exception: {free}" if free is not None else ""),
                entered_by=player.id,
                trait_definition_id=definition.id,
                detail=detail or None,
                from_rating=current_rating,
                to_rating=rating,
                cost_basis={"free": free}
                if free is not None
                else quote.rule.describe()
                if quote is not None
                else {},
            )
        )
    repricing.record(db, player, character.id, repriced, f"{name} {current_rating} → {rating}")
    if rating == 0 and trait.free_rating == 0:
        db.delete(trait)
        trait = None
    else:
        trait.rating = rating
        if free is not None:
            trait.free_rating = (trait.free_rating or 0) + rating - current_rating
    db.flush()
    audit.record(
        db,
        player,
        "sheet.purchase",
        character_id=character.id,
        category=category.key,
        name=name,
        detail=detail,
        from_rating=current_rating,
        to_rating=rating,
        cost=cost,
        free=free or "",
    )
    learning_now = by_exception is None or (by_exception == "given" and free is None)
    if not held and rating > current_rating and learning_now:
        whole = definition.properties.get("rating") is not None
        actions = owed_for(db, character, category, rating - current_rating, whole)
        doing = f"Gaining {name}" if whole else f"Learning {name} {rating}"
        owe(db, player, character, actions, doing)
    if held:
        assert character.home_troupe_id is not None
        approval = Approval(
            character_id=character.id,
            troupe_id=character.home_troupe_id,
            kind="discipline",
            requested_by=player.id,
        )
        db.add(approval)
        db.flush()
        db.add(
            DisciplinePurchase(
                approval_id=approval.id,
                trait_definition_id=definition.id,
                detail=detail,
                from_rating=current_rating,
                to_rating=rating,
                cost=cost,
                teacher=teacher,
            )
        )
        db.flush()
        audit.record(
            db,
            player,
            "approval.request",
            troupe_id=approval.troupe_id,
            character_id=character.id,
            approval_id=approval.id,
            kind=approval.kind,
            name=name,
            rating=rating,
        )
        notifications.approval_waiting(db, approval)
    if free is not None:
        return Change(
            quote=None,
            trait=trait,
            normal_cost=priced.cost if priced else None,
            repriced=tuple(repriced),
        )
    return Change(quote=quote, trait=trait, repriced=tuple(repriced))


def change_choice(
    db: Session,
    player: User,
    character: Character,
    category_key: str,
    from_name: str,
    to_name: str,
) -> int:
    """Swap one trait for another in a category that allows it after creation, such
    as a focus, for the category's change cost. The new trait takes the old one's
    place, starting dots and all; nothing is refunded for the old one. Returns the
    XP spent."""
    ensure_unlocked(db, character)
    if character.creation_completed_at is None:
        raise conflict("During creation, change it in the creation wizard; it is free there.")
    old_definition, category = find_definition(db, character, category_key, from_name)
    new_definition, _ = find_definition(db, character, category_key, to_name)
    if category.change_cost is None:
        raise conflict(f"{category.name} cannot be swapped like this.")
    rows = {r.definition.id: r for r in sheet_rows(db, character) if r.category.id == category.id}
    old = rows.get(old_definition.id)
    if old is None:
        raise conflict(f"The character does not have {from_name}.")
    if new_definition.id in rows:
        raise conflict(f"The character already has {to_name}.")
    cost = category.change_cost
    if xp_balance(db, character) < cost:
        raise conflict(f"That costs {cost} XP, and the character has {xp_balance(db, character)}.")

    old.trait.trait_definition_id = new_definition.id
    # An exception was for the trait swapped away, not the one it becomes.
    db.execute(delete(TraitException).where(TraitException.character_trait_id == old.trait.id))
    db.add(
        XpEntry(
            character_id=character.id,
            kind="fee",
            amount=-cost,
            reason=f"Changed {category.name}: {from_name} → {to_name}",
            entered_by=player.id,
            trait_definition_id=new_definition.id,
        )
    )
    db.flush()
    audit.record(
        db,
        player,
        "sheet.change",
        character_id=character.id,
        category=category.name.lower(),
        from_name=from_name,
        name=to_name,
        cost=cost,
    )
    return cost


def set_detail(
    db: Session, player: User, character: Character, category_key: str, name: str, detail: str
) -> CharacterTrait:
    """Give a trait held without a detail its detail, such as the field of a
    Crafts bought before fields were asked for. Before acceptance any detail can
    be changed; afterwards only a missing one filled in."""
    ensure_unlocked(db, character)
    definition, category = find_definition(db, character, category_key, name)
    trait = db.scalar(
        select(CharacterTrait)
        .where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
        )
        .order_by(CharacterTrait.detail)
    )
    if trait is None:
        raise conflict(f"The character does not have {name}.")
    if trait.detail and character.home_troupe_id is not None:
        raise conflict(f"{name} already has its detail: {trait.detail}.")
    clash = db.scalar(
        select(CharacterTrait.id).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == detail,
        )
    )
    if clash is not None:
        raise conflict(f"The character already has {name}: {detail}.")
    before = trait.detail
    trait.detail = detail
    db.flush()
    audit.record(
        db,
        player,
        "sheet.detail",
        character_id=character.id,
        name=name,
        detail=detail,
        before=before or "none",
    )
    return trait


def freeze_sheet(
    db: Session, approver: User, character: Character, troupe_id: uuid.UUID
) -> SheetVersion:
    """Freeze the sheet as it stands, as `troupe_id` accepted it as home."""
    found = membership(db, character, troupe_id)
    if found is None:
        raise conflict("The character is not in that troupe.")
    number = (
        db.scalar(
            select(func.max(SheetVersion.number)).where(
                SheetVersion.character_id == character.id, SheetVersion.troupe_id == troupe_id
            )
        )
        or 0
    ) + 1
    version = SheetVersion(
        character_id=character.id,
        troupe_id=troupe_id,
        number=number,
        snapshot=[r.snapshot() for r in sheet_rows(db, character)],
        approved_by=approver.id,
    )
    db.add(version)
    db.flush()
    found.approved_version_id = version.id
    return version


def decide(
    db: Session,
    staff: User,
    approval: Approval,
    approve: bool,
    note: str,
    settlement_overrides: Mapping[uuid.UUID, str] | None = None,
    xp: xp_range.Decision | None = None,
    at_cost: bool = False,
    diablerie: "Adjust | None" = None,
) -> Approval:
    """Approve or decline a request. `at_cost`, for a trait asked for free by
    exception: approve it, but charge the XP it costs at the normal price.
    `diablerie`, for a diablerie a player asked to record: what staff change."""
    if approval.status != "pending":
        raise conflict(f"This request is already {approval.status}.")
    character = lock_character(db, approval.character_id)
    if at_cost and not (approve and approval.kind == "exception"):
        raise unprocessable("Only an exception asked for free can be approved at normal cost.")
    if not approve and approval.kind in HELD_KINDS:
        undo_discipline(db, staff, character, approval, "declined")
    elif approve and approval.kind == "exception":
        from horatio.trait_exceptions import approve_asked  # imports this module

        approve_asked(db, staff, character, approval, at_cost)
    elif approval.kind == "diablerie":
        from horatio import diablerie as diablerie_rules  # imports this module

        if approve:
            diablerie_rules.approve_asked(db, staff, character, approval, diablerie)
        else:
            diablerie_rules.declined(db, character, approval)
    elif approve and approval.kind == "discipline":
        bought = db.scalars(
            select(DisciplinePurchase).where(DisciplinePurchase.approval_id == approval.id)
        ).one()
        definition = db.get_one(TraitDefinition, bought.trait_definition_id)
        category = db.get_one(TraitCategory, definition.category_id)
        actions = owed_for(db, character, category, bought.to_rating - bought.from_rating, False)
        owe(db, staff, character, actions, f"Learning {definition.name} {bought.to_rating}")
    elif approve and approval.kind == "home_troupe_change":
        from horatio.reconciliation import approve_change  # imports this module

        approve_change(db, staff, approval, character, settlement_overrides or {}, xp)
    approval.status = "approved" if approve else "declined"
    approval.decided_by = staff.id
    approval.decided_at = datetime.now(UTC)
    approval.staff_note = note
    db.flush()
    audit.record(
        db,
        staff,
        f"approval.{approval.status}",
        troupe_id=approval.troupe_id,
        character_id=character.id,
        approval_id=approval.id,
        kind=approval.kind,
        **discipline_details(db, approval),
        **({"at_cost": True} if at_cost else {}),
    )
    return approval


def discipline_details(db: Session, approval: Approval) -> dict[str, Any]:
    """What the log says about a held purchase: which trait, to what rating."""
    if approval.kind not in HELD_KINDS:
        return {}
    found = db.execute(
        select(TraitDefinition.name, DisciplinePurchase.to_rating)
        .join(DisciplinePurchase, DisciplinePurchase.trait_definition_id == TraitDefinition.id)
        .where(DisciplinePurchase.approval_id == approval.id)
    ).one()
    return {"name": found[0], "rating": found[1]}


def undo_discipline(
    db: Session, user: User, character: Character, approval: Approval, why: str
) -> None:
    """Take back held dots that were not approved, and refund their XP. An
    exception asked for them goes too, and dots it gave free stop being free."""
    bought = db.scalar(
        select(DisciplinePurchase).where(DisciplinePurchase.approval_id == approval.id)
    )
    assert bought is not None
    definition = db.get_one(TraitDefinition, bought.trait_definition_id)
    trait = db.scalar(
        select(CharacterTrait).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == bought.detail,
        )
    )
    asked = db.scalar(select(TraitException).where(TraitException.approval_id == approval.id))
    if asked is not None:
        if asked.free and trait is not None:
            gained = bought.to_rating - bought.from_rating
            trait.free_rating = max(0, trait.free_rating - gained)
        db.delete(asked)
        db.flush()
    if trait is not None:
        if bought.from_rating == 0 and trait.free_rating == 0:
            db.delete(trait)
        else:
            trait.rating = bought.from_rating
    db.add(
        XpEntry(
            character_id=character.id,
            kind="purchase",
            amount=bought.cost,
            reason=f"{definition.name} {bought.to_rating} → {bought.from_rating} ({why})",
            entered_by=user.id,
            trait_definition_id=definition.id,
            detail=bought.detail or None,
            from_rating=bought.to_rating,
            to_rating=bought.from_rating,
            cost_basis={"refund": why},
        )
    )
    db.flush()


def withdraw(db: Session, player: User, approval: Approval) -> Approval:
    if approval.status != "pending":
        raise conflict(f"This request is already {approval.status}.")
    if approval.kind in HELD_KINDS:
        undo_discipline(
            db, player, lock_character(db, approval.character_id), approval, "withdrawn"
        )
    approval.status = "withdrawn"
    approval.decided_at = datetime.now(UTC)
    db.flush()
    audit.record(
        db,
        player,
        "approval.withdrawn",
        troupe_id=approval.troupe_id,
        character_id=approval.character_id,
        approval_id=approval.id,
        kind=approval.kind,
        **discipline_details(db, approval),
    )
    return approval


def earned_and_spent(entries: Iterable[tuple[str, int]]) -> tuple[int, int]:
    """XP earned and spent from (kind, amount) pairs. A correction changes what an
    award gave, and a cap what was earned before joining a troupe, so they count
    toward earned whichever way they go; a reprice changes what a purchase cost,
    so it counts toward spent."""
    earned = spent = 0
    for kind, amount in entries:
        if kind == "reprice":
            spent -= amount
        elif kind in ("correction", "cap") or amount > 0:
            earned += amount
        else:
            spent -= amount
    return earned, spent


# XP entries a correction can put right: XP given, by staff or (in the vault) by the player.
CORRECTABLE = ("award", "self_entered")


def award_xp(db: Session, staff: User, character: Character, amount: int, reason: str) -> XpEntry:
    entry = XpEntry(
        character_id=character.id, kind="award", amount=amount, reason=reason, entered_by=staff.id
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        staff,
        "xp.award",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        amount=amount,
        reason=reason,
    )
    return entry


def awarded(db: Session, award: XpEntry) -> int:
    """What an award gives now: its amount with every correction to it."""
    corrections = db.scalar(
        select(func.coalesce(func.sum(XpEntry.amount), 0)).where(XpEntry.corrects_id == award.id)
    )
    return award.amount + (corrections or 0)


def correct_xp(
    db: Session, staff: User, character: Character, award: XpEntry, amount: int, reason: str
) -> XpEntry:
    """Put right a mistaken award (or self-entered XP): the award is left as
    written, and a correction entry adds the difference between what it gives
    now and `amount`."""
    if award.character_id != character.id or award.kind not in CORRECTABLE:
        raise unprocessable("Only an award can be corrected.")
    was = awarded(db, award)
    difference = amount - was
    if difference == 0:
        raise unprocessable(f"That award already gives {was} XP.")
    balance = xp_balance(db, character)
    if balance + difference < 0:
        raise conflict(
            f"{character.name} has only {balance} XP unspent, so this award can come down"
            f" by at most {balance}."
        )
    entry = XpEntry(
        character_id=character.id,
        kind="correction",
        amount=difference,
        reason=reason,
        entered_by=staff.id,
        corrects_id=award.id,
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        staff,
        "xp.corrected",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        award=award.reason,
        was=was,
        now=amount,
        reason=reason,
    )
    return entry
