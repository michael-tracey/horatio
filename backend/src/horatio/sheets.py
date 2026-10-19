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
"""

import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import (
    Approval,
    Character,
    CharacterTrait,
    DisciplinePurchase,
    RuleSet,
    SheetVersion,
    TraitCategory,
    TraitDefinition,
    TroupeMembership,
    User,
    XpEntry,
)
from horatio.rules.checks import Context, Violation, violations
from horatio.rules.grants import Effects, choices, effects, raised_by
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import (
    PricingError,
    Quote,
    fixed_rating,
    points,
    purchase_cost,
    trait_cost,
)
from horatio.rules.splats import SPLATS
from horatio.rules.store import read_troupe_rules

TraitKey = tuple[str, str, str]  # category, name, detail

# Categories whose every dot, once the character has a home troupe, waits on its staff.
NEEDS_HOME_APPROVAL = frozenset({"disciplines"})

FINISH_CREATION_FIRST = (
    "Build the character in the creation wizard first; "
    + "experience can be spent once it is finished."
)


def conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


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


def check_context(db: Session, character: Character, sheet: Sequence[SheetTrait]) -> Context:
    rules = rules_for(db, character)
    # Paths a merit prices as in-clan (Thaumaturgic Expertise) count as in-clan here.
    priced = effects(rules.rule_set.grants, sheet, rules.rule_set).in_clan_priced
    native = frozenset(SPLATS[character.splat].in_clan(rules, sheet))
    return Context(
        accepted=character.home_troupe_id is not None,
        in_clan=native | {f"{name}: {detail}" if detail else name for _, name, detail in priced},
        native=native,
        primary=frozenset(character.primary_paths.values()),
        kinds=rules.rule_set.kinds,
    )


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
    # The primary path: the clan's in-clan one, or the one the player named.
    path: str | None
    native: bool
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
        if in_clan_path is not None:
            found.append(PrimaryPath(discipline, in_clan_path, native=True, options=[]))
            continue
        named = character.primary_paths.get(discipline)
        found.append(
            PrimaryPath(
                discipline,
                named if named in {t.name for t in held} else None,
                native=False,
                options=[t.name for t in held],
            )
        )
    return found


def name_primary_path(
    db: Session, user: User, character: Character, discipline: str, path: str | None
) -> None:
    """Name the character's primary path of a discipline, where its clan has no
    in-clan path; None un-names it. The primary is the first path to reach 2 dots,
    so no other path may be higher than it (MET: VTM p. 187)."""
    current = {p.discipline: p for p in primary_paths(db, character)}
    if discipline not in path_disciplines(rules_for(db, character)):
        raise unprocessable(f"{discipline} has no primary path.")
    chosen = current.get(discipline)
    if chosen is not None and chosen.native:
        raise conflict(f"{chosen.path} is the primary path, as the clan's in-clan path.")
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


def sheet_violations(db: Session, character: Character) -> list[Violation]:
    """The checks the character's sheet breaks now."""
    sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
    return violations(rules_for(db, character).checks(), sheet, check_context(db, character, sheet))


def blocking(violation: Violation, character: Character) -> bool:
    """Whether a broken check stops a change: refuse checks always; complete
    checks once the character's creation is finished."""
    strength = violation.check.strength
    return strength == "refuse" or (
        strength == "complete" and character.creation_completed_at is not None
    )


def unavailable(
    db: Session,
    character: Character,
    category_key: str,
    as_if: str = "sheet",
    picks: Sequence[str] = (),
) -> dict[str, str]:
    """For each trait in a category the character does not hold, why a check would
    refuse it, if one would. A merit or flaw is tried at its point value, anything
    else at 1 dot.

    `as_if` "picks" first puts `picks` in place of the category's creation picks (the
    wizard's ticks before they are saved); "empty" first takes everything in the
    category away, leaving what no choice there could make allowed."""
    rules = rules_for(db, character)
    rule_set = rules.rule_set
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
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
    before = {v.key for v in violations(checks, sheet, context)}
    rated = rule_set.categories[category_key].rated
    reasons: dict[str, str] = {}
    for category, name in rule_set.traits:
        if category != category_key or name in held:
            continue
        rating = (fixed_rating(rules, sheet, category, name) or 1) if rated else None
        candidate = SheetTrait(category=category, name=name, rating=rating, free_rating=0)
        trial = [t for t in sheet if rated or t.category != category] + [candidate]
        new = [
            v
            for v in violations(checks, trial, check_context(db, character, trial))
            if blocking(v, character) and v.key not in before
        ]
        if new:
            # The trait's own problem first: "Talisman is already…" when trying Spellslinger.
            own = [v for v in new if v.subject.name == name]
            reasons[name] = (own or new)[0].message
    return reasons


def sheet_effects(db: Session, character: Character) -> Effects:
    """What the sheet's grants do."""
    rule_set = rules_for(db, character).rule_set
    sheet = [r.as_rules_trait() for r in sheet_rows(db, character)]
    return effects(rule_set.grants, sheet, rule_set)


def convert(db: Session, character: Character, rules: TroupeRules, found: Effects) -> None:
    """Bring conversions into line: a held Path merit turns Humanity into that
    Path, keeping its dots; without the merit the Path turns back into Humanity."""
    targets = {
        (g.convert_from["category"], g.convert_from["name"]): set()
        for g in rules.rule_set.grants
        if g.kind == "convert" and g.convert_from
    }
    for g in rules.rule_set.grants:
        if g.kind == "convert" and g.convert_from:
            targets[(g.convert_from["category"], g.convert_from["name"])].add(g.target["name"])
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
        definition, _ = find_definition(db, character, category, wanted)
        current.trait.trait_definition_id = definition.id
    db.flush()


def apply_grants(db: Session, user: User, character: Character) -> None:
    """Bring every granted trait into line with the grants the sheet now holds:
    add what new grants give, take back what lost grants gave (nothing refunded,
    MET: VTM p. 236), and refund dots a `free_up_to` grant now makes free."""
    rules = rules_for(db, character)
    convert(db, character, rules, sheet_effects(db, character))
    found = sheet_effects(db, character)
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
        trait.rating = max(0, base_rating + granted)
        trait.free_rating = max(0, base_free + granted)
        trait.granted_rating = granted
        if trait.rating == 0 and trait.free_rating == 0 and trait.creation_pick is None:
            db.delete(trait)
    db.flush()


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
) -> None:
    """A change that breaks a review check goes ahead but waits on the home troupe,
    like a discipline dot: declining takes the dots back and refunds the XP."""
    subject = violation.subject
    key = (subject.category, subject.name, subject.detail)
    before, after = ratings_before.get(key, 0), subject.rating or 0
    definition, _ = find_definition(db, character, subject.category, subject.name)
    if after <= before or any(
        d.trait_definition_id == definition.id and d.detail == subject.detail
        for _, d in pending_disciplines(db, character)
    ):
        return
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


def creation_only_traits(db: Session, character: Character) -> dict[TraitKey, int | None]:
    """The character's traits that are chosen at creation only, with their ratings."""
    selectors = rules_for(db, character).rule_set.creation_only
    return {
        r.key: r.trait.rating
        for r in sheet_rows(db, character)
        if any(
            s["category"] == r.category.key
            and (not s.get("name") or s["name"] == r.definition.name)
            and r.definition.name.startswith(s.get("name_prefix", ""))
            for s in selectors
        )
    }


@contextmanager
def checked(db: Session, character: Character, user: User | None = None) -> Iterator[None]:
    """Make a change to a sheet, then bring its grants into line and refuse the
    change if it breaks a check the sheet did not already break. The change is
    rolled back (to a savepoint taken before it) with the refusal. NPCs get their grants but are
    their staff's to build as they like."""
    before = {v.key for v in sheet_violations(db, character)}
    over_before = held_beyond_limit(db, character)
    fixed_before = creation_only_traits(db, character)
    ratings_before = {r.key: r.trait.rating or 0 for r in sheet_rows(db, character)}
    xp_before = set(db.scalars(select(XpEntry.id).where(XpEntry.character_id == character.id)))
    savepoint = db.begin_nested()
    try:
        yield
        db.flush()
    except BaseException:
        savepoint.rollback()
        raise
    if user is not None:
        apply_grants(db, user, character)
    if character.kind != "pc":
        savepoint.commit()
        return
    db.expire_all()
    now_broken = [v for v in sheet_violations(db, character) if v.key not in before]
    problems = [v.message for v in now_broken if blocking(v, character)]
    if user is not None and character.home_troupe_id is not None and not problems:
        for violation in now_broken:
            if violation.check.strength == "review":
                hold_for_review(db, user, character, violation, ratings_before, xp_before)
    rule_set = rules_for(db, character).rule_set
    for key, count in held_beyond_limit(db, character).items():
        if count > over_before.get(key, 0):
            category = rule_set.categories[key]
            problems.append(
                f"A character holds {category.max_held} {category.name.lower()}; "
                "only merits can grant more."
            )
    if character.creation_completed_at is not None:
        fixed_after = creation_only_traits(db, character)
        changed = {
            key
            for key in fixed_before.keys() | fixed_after.keys()
            if fixed_before.get(key, 0) != fixed_after.get(key, 0)
        }
        for key in sorted(changed):
            problems.append(f"{key[1]} can only be chosen during character creation.")
    for trait, grant in sheet_effects(db, character).unchosen:
        options = choices(grant, rule_set)
        listed = ", ".join(options) if len(options) <= 8 else "the trait it applies to"
        problems.append(f"Say which for {trait.name}: put {listed} in its detail.")
    if problems:
        savepoint.rollback()
        raise conflict(" ".join(dict.fromkeys(problems)))
    savepoint.commit()


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
    """Give a new character the rule set's starting XP."""
    starting_xp = db.scalar(select(RuleSet.starting_xp).where(RuleSet.splat == character.splat))
    if starting_xp:
        db.add(
            XpEntry(
                character_id=character.id,
                kind="award",
                amount=starting_xp,
                reason="Starting experience",
                entered_by=player.id,
            )
        )


@dataclass
class Change:
    quote: Quote | None
    trait: CharacterTrait | None


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
        raise unprocessable(str(error)) from error
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
    """The points the character holds in a category, as its troupe prices them."""
    rules = rules_for(db, character)
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    return sum(
        points(rules, sheet, r.as_rules_trait())
        for r in rows
        if r.category.key == category_key and r.key != leave_out
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
) -> Change:
    """Add a trait, change its rating, or (at rating 0) remove it, buying or
    refunding the difference. Unrated traits replace the category's choice.
    `teacher` names who teaches a discipline dot that waits on the home troupe."""
    ensure_unlocked(db, character)
    definition, category = find_definition(db, character, category_key, name)
    if rating:
        from horatio.specializations import check_choice  # imports this module

        check_choice(db, character, category, name, detail)

    if not category.rated:
        quote_change(db, character, category_key, name, detail, rating)  # validates
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
    quote, current_rating = quote_change(db, character, category_key, name, detail, rating)
    assert quote is not None and rating is not None and current_rating is not None
    if category.points_limit is not None and rating > current_rating:
        quote = within_points_limit(db, character, category, definition, detail, rating, quote)

    accepted = accepted_ratings(db, character).get((category.key, definition.name, detail), 0)
    if rating < accepted and category.buy_off_factor and rating == 0:
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
    if quote.cost > 0 and xp_balance(db, character) < quote.cost:
        raise conflict(
            f"That costs {quote.cost} XP, and the character has {xp_balance(db, character)}."
        )

    trait = db.scalar(
        select(CharacterTrait).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == definition.id,
            CharacterTrait.detail == detail,
        )
    )
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
    )
    if rating != current_rating and quote.cost != 0:
        db.add(
            XpEntry(
                character_id=character.id,
                kind="purchase",
                amount=-quote.cost,
                reason=f"{name} {current_rating} → {rating}",
                entered_by=player.id,
                trait_definition_id=definition.id,
                detail=detail or None,
                from_rating=current_rating,
                to_rating=rating,
                cost_basis=quote.rule.describe(),
            )
        )
    if rating == 0 and trait.free_rating == 0:
        db.delete(trait)
        trait = None
    else:
        trait.rating = rating
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
        cost=quote.cost,
    )
    if not held and rating > current_rating:
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
                cost=quote.cost,
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
    return Change(quote=quote, trait=trait)


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
) -> Approval:
    if approval.status != "pending":
        raise conflict(f"This request is already {approval.status}.")
    character = lock_character(db, approval.character_id)
    if not approve and approval.kind in ("discipline", "review"):
        undo_discipline(db, staff, character, approval, "declined")
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

        approve_change(db, staff, approval, character, settlement_overrides or {})
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
    )
    return approval


def discipline_details(db: Session, approval: Approval) -> dict[str, Any]:
    """What the log says about a held purchase: which trait, to what rating."""
    if approval.kind not in ("discipline", "review"):
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
    """Take back discipline dots that were not approved, and refund their XP."""
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
    if approval.kind in ("discipline", "review"):
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
