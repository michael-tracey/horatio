"""House merits and flaws: ones a troupe's storytellers make themselves.

A troupe's house merit or flaw is a `HouseTrait`, with its own trait definition
(`TraitDefinition.troupe_id` set) that sheets and purchases hold it through, as
they hold a merit from the book. The troupe's rules (horatio.rules.store) list it
among the rule set's traits, at its points, so it is priced, limited and checked
like a book merit; but only for the troupe's own characters: those whose home
troupe it is, those being built for it, and its NPCs. A character only visiting
plays by its home troupe's rules, which do not have it.

Each is one of two kinds:

- **Staff only.** Players never pick it; the troupe's running staff apply it to a
  character (`apply`), free or charged, and say whether a free merit counts toward
  the merit limit, always with a reason. Only staff remove it (`remove`).
- **Available when building for the troupe.** Picked in the creation wizard and the
  cart like a book merit, optionally at creation only.

Archiving one stops new picks, and those who hold it keep it; deleting one is only
for one nobody holds. Changing one changes it for everyone who holds it, as it is
the troupe's rule; XP already spent stays as it was.

What one does is its description for now: the storytellers rule on it at the
table. `HouseTrait.effects` holds the effect blocks to come, each naming the engine
kind it maps to (a grant, a check, a pool modifier), so that the rules can merge
them with the trait as they merge its points and type.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, notifications, sheets
from horatio.models import (
    AppliedHouseTrait,
    Character,
    CharacterTrait,
    HouseTrait,
    RuleSet,
    TraitCategory,
    TraitDefinition,
    Troupe,
    User,
    XpEntry,
)
from horatio.rules.model import house_label, house_page
from horatio.rules.store import changes_rules, forget_rules, house_properties
from horatio.sheets import conflict, unprocessable

Category = Literal["merits", "flaws"]
Kind = Literal["General", "Clan", "Sabbat"]
Availability = Literal["staff", "building"]


@dataclass(frozen=True)
class Spec:
    """What staff say a house merit or flaw is."""

    category: Category
    name: str
    points: int
    kind: Kind
    availability: Availability
    creation_only: bool = False
    description: str = ""
    requirement: str = ""
    splat: str = "vampire"


@dataclass(frozen=True)
class Mark:
    """How a house trait is marked wherever it shows: whose it is."""

    house_trait_id: uuid.UUID
    troupe_id: uuid.UUID
    troupe_name: str
    label: str
    page: str
    availability: str
    archived: bool


def noun(category: str) -> str:
    return "house flaw" if category == "flaws" else "house merit"


def marked(name: str) -> str:
    """A house trait's name as the logs give it: "★ Lucky"."""
    return f"★ {name}"


def category_row(db: Session, splat: str, category: str) -> TraitCategory:
    found = db.scalar(
        select(TraitCategory)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .where(RuleSet.splat == splat, TraitCategory.key == category)
    )
    if found is None:
        raise unprocessable(f"There are no {category} for {splat}.")
    return found


def check_spec(db: Session, troupe: Troupe, spec: Spec, house: HouseTrait | None) -> None:
    """Refuse a house merit or flaw that is not well made: a name the book or the
    troupe already uses, or points outside 1 to 7."""
    if not spec.name:
        raise unprocessable("Give it a name.")
    if not 1 <= spec.points <= 7:
        raise unprocessable("A merit or flaw is worth 1 to 7 points.")
    if spec.splat != "vampire" and spec.splat not in troupe.allowed_splats:
        raise unprocessable(f"{troupe.name} does not take {spec.splat} characters.")
    categories = [category_row(db, spec.splat, c).id for c in ("merits", "flaws")]
    book = db.scalar(
        select(TraitDefinition.name).where(
            TraitDefinition.category_id.in_(categories),
            TraitDefinition.troupe_id.is_(None),
            func.lower(TraitDefinition.name) == spec.name.lower(),
        )
    )
    if book is not None:
        raise conflict(f"The book already has {book}; give the house one a name of its own.")
    same = db.scalar(
        select(HouseTrait).where(
            HouseTrait.troupe_id == troupe.id,
            HouseTrait.splat == spec.splat,
            func.lower(HouseTrait.name) == spec.name.lower(),
            HouseTrait.id != (house.id if house is not None else uuid.UUID(int=0)),
        )
    )
    if same is not None:
        raise conflict(f"{troupe.name} already has a {noun(same.category)} called {same.name}.")


def holders(db: Session, house: HouseTrait) -> list[Character]:
    """The characters whose sheets hold it, by name."""
    return list(
        db.scalars(
            select(Character)
            .join(CharacterTrait, CharacterTrait.character_id == Character.id)
            .where(CharacterTrait.trait_definition_id == house.trait_definition_id)
            .distinct()
            .order_by(Character.name)
        )
    )


def keep_definition(db: Session, house: HouseTrait, troupe: Troupe) -> None:
    """Bring its trait definition into line with it."""
    definition = db.get_one(TraitDefinition, house.trait_definition_id)
    definition.category_id = category_row(db, house.splat, house.category).id
    definition.name = house.name
    definition.description = house.description or None
    definition.page_reference = house_page(troupe.name)
    definition.properties = house_properties(house)
    definition.retired = False


@changes_rules
def create(db: Session, staff: User, troupe: Troupe, spec: Spec) -> HouseTrait:
    check_spec(db, troupe, spec, None)
    category = category_row(db, spec.splat, spec.category)
    # One deleted before keeps its definition for the XP history that names it.
    definition = db.scalar(
        select(TraitDefinition).where(
            TraitDefinition.category_id == category.id,
            TraitDefinition.troupe_id == troupe.id,
            TraitDefinition.name == spec.name,
        )
    )
    if definition is None:
        definition = TraitDefinition(category_id=category.id, name=spec.name, troupe_id=troupe.id)
        db.add(definition)
        db.flush()
    house = HouseTrait(
        troupe_id=troupe.id,
        splat=spec.splat,
        category=spec.category,
        name=spec.name,
        points=spec.points,
        kind=spec.kind,
        availability=spec.availability,
        creation_only=spec.creation_only,
        description=spec.description,
        requirement=spec.requirement,
        trait_definition_id=definition.id,
    )
    db.add(house)
    db.flush()
    keep_definition(db, house, troupe)
    db.flush()
    audit.record(
        db,
        staff,
        "house.trait_added",
        troupe_id=troupe.id,
        what=noun(spec.category),
        name=marked(spec.name),
        points=spec.points,
        availability=AVAILABILITY_WORDS[spec.availability],
    )
    return house


AVAILABILITY_WORDS = {
    "staff": "given by staff only",
    "building": "available when building for the troupe",
}


@changes_rules
def change(db: Session, staff: User, troupe: Troupe, house: HouseTrait, spec: Spec) -> HouseTrait:
    """Change it for everyone who holds it. Their ratings follow its points; what
    they spent on it stays as it was."""
    check_spec(db, troupe, spec, house)
    held = holders(db, house)
    if held and (spec.category, spec.splat) != (house.category, house.splat):
        raise conflict(
            f"{len(held)} characters hold {house.name}; "
            "it stays a " + noun(house.category) + " while anyone does."
        )
    before = house.name
    changed = [
        field
        for field, value in (
            ("name", spec.name),
            ("category", spec.category),
            ("points", spec.points),
            ("kind", spec.kind),
            ("availability", spec.availability),
            ("creation_only", spec.creation_only),
            ("description", spec.description),
            ("requirement", spec.requirement),
            ("splat", spec.splat),
        )
        if getattr(house, field) != value
    ]
    house.name = spec.name
    house.category = spec.category
    house.points = spec.points
    house.kind = spec.kind
    house.availability = spec.availability
    house.creation_only = spec.creation_only
    house.description = spec.description
    house.requirement = spec.requirement
    house.splat = spec.splat
    keep_definition(db, house, troupe)
    db.flush()
    if "points" in changed:
        # Rules read afresh, so holders are held at the new points.
        forget_rules(db)
        for character in held:
            sheets.sync_fixed_ratings(db, character)
        # One staff gave free stays all free dots.
        for trait in db.scalars(
            select(CharacterTrait)
            .join(AppliedHouseTrait, AppliedHouseTrait.character_trait_id == CharacterTrait.id)
            .where(AppliedHouseTrait.house_trait_id == house.id, AppliedHouseTrait.free)
        ):
            trait.free_rating = trait.rating or 0
        db.flush()
    if changed:
        audit.record(
            db,
            staff,
            "house.trait_changed",
            troupe_id=troupe.id,
            what=noun(house.category),
            name=marked(before),
            fields=", ".join(f.replace("_", " ") for f in changed),
            holders=len(held),
        )
    return house


@changes_rules
def archive(db: Session, staff: User, troupe: Troupe, house: HouseTrait, archived: bool) -> None:
    """Archive it, so no one new takes it, or bring it back."""
    if (house.archived_at is not None) == archived:
        return
    house.archived_at = datetime.now(UTC) if archived else None
    keep_definition(db, house, troupe)
    db.flush()
    audit.record(
        db,
        staff,
        "house.trait_archived" if archived else "house.trait_restored",
        troupe_id=troupe.id,
        what=noun(house.category),
        name=marked(house.name),
    )


@changes_rules
def delete(db: Session, staff: User, troupe: Troupe, house: HouseTrait) -> None:
    """Delete one nobody holds. Its trait definition stays, retired, for the XP
    history and logs that name it."""
    held = holders(db, house)
    if held:
        raise conflict(
            f"{', '.join(c.name for c in held)} "
            + ("holds" if len(held) == 1 else "hold")
            + f" {house.name}; archive it instead, so no one new takes it."
        )
    definition = db.get_one(TraitDefinition, house.trait_definition_id)
    definition.retired = True
    db.delete(house)
    db.flush()
    audit.record(
        db,
        staff,
        "house.trait_deleted",
        troupe_id=troupe.id,
        what=noun(house.category),
        name=marked(house.name),
    )


def marks(db: Session, definition_ids: list[uuid.UUID]) -> dict[uuid.UUID, Mark]:
    """The house marks of whichever of these trait definitions are house traits."""
    if not definition_ids:
        return {}
    return {
        h.trait_definition_id: mark(h, name)
        for h, name in db.execute(
            select(HouseTrait, Troupe.name)
            .join(Troupe, HouseTrait.troupe_id == Troupe.id)
            .where(HouseTrait.trait_definition_id.in_(definition_ids))
        )
    }


def mark(house: HouseTrait, troupe_name: str) -> Mark:
    return Mark(
        house_trait_id=house.id,
        troupe_id=house.troupe_id,
        troupe_name=troupe_name,
        label=house_label(house.category, troupe_name),
        page=house_page(troupe_name),
        availability=house.availability,
        archived=house.archived_at is not None,
    )


# --- Staff apply and remove ------------------------------------------------------


def ensure_theirs(character: Character, house: HouseTrait, troupe: Troupe) -> None:
    """Only the troupe's own characters hold its house traits: its home characters,
    those being built for it, and its NPCs; never one only visiting."""
    if sheets.rules_troupe(character) != house.troupe_id:
        raise conflict(
            f"{house.name} is {troupe.name}'s own: only for characters whose home troupe "
            "it is, or that are being built for it."
        )
    if character.splat != house.splat:
        raise conflict(f"{house.name} is for {house.splat} characters.")


@contextmanager
def staff_change(db: Session, staff: User, character: Character) -> Iterator[None]:
    """Make a change staff make to a sheet, then bring its grants into line and
    refuse it if it breaks a check the sheet did not already break; as
    `sheets.checked`, but staff may apply or remove a merit chosen at creation only
    whenever they like, and nothing waits on approval, as they are the approvers."""
    before = sheets.sheet_state(db, character)
    savepoint = db.begin_nested()
    try:
        yield
        db.flush()
        sheets.apply_grants(db, staff, character)
        if character.kind == "pc":
            refused = sheets.broken_since(db, None, character, before, creation_only=False).refused
            if refused:
                raise conflict(sheets.refusal(refused))
    except BaseException:
        savepoint.rollback()
        raise
    savepoint.commit()


def applied_to(db: Session, character: Character, house: HouseTrait) -> CharacterTrait | None:
    return db.scalar(
        select(CharacterTrait).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == house.trait_definition_id,
        )
    )


def apply(
    db: Session,
    staff: User,
    character: Character,
    house: HouseTrait,
    *,
    free: bool,
    counts_toward_limit: bool,
    reason: str,
) -> AppliedHouseTrait:
    """Staff put a house merit or flaw on a character: `free`, costing no XP (a
    free merit counting toward the merit limit unless `counts_toward_limit` is
    False), or charged at its points as a purchase is. The reason goes in the
    character's log and the troupe's, and the player is told."""
    troupe = db.get_one(Troupe, house.troupe_id)
    ensure_theirs(character, house, troupe)
    sheets.ensure_unlocked(db, character)
    if house.archived_at is not None:
        raise conflict(f"{house.name} is archived; bring it back to apply it.")
    if applied_to(db, character, house) is not None:
        raise conflict(f"{character.name} already has {house.name}.")
    npc = character.kind == "npc"
    if npc:
        free = True
    if not free and character.creation_completed_at is None:
        raise conflict("Charge it once the character's creation is finished, or give it free.")
    balance = sheets.xp_balance(db, character)
    with staff_change(db, staff, character):
        if free:
            give_free(db, staff, character, house, counts_toward_limit and not npc, reason)
        else:
            sheets.set_trait(
                db,
                staff,
                character,
                house.category,
                house.name,
                "",
                house.points,
                by_staff=True,
                because=f"applied by staff: {reason}",
            )
    trait = applied_to(db, character, house)
    assert trait is not None
    cost = balance - sheets.xp_balance(db, character)
    applied = AppliedHouseTrait(
        character_id=character.id,
        character_trait_id=trait.id,
        house_trait_id=house.id,
        free=free,
        counts_toward_limit=counts_toward_limit or not free,
        cost=cost,
        reason=reason,
        applied_by=staff.id,
    )
    db.add(applied)
    db.flush()
    how = (
        "free"
        + ("" if counts_toward_limit or house.category == "flaws" else ", outside the merit limit")
        if free
        else f"{cost} XP"
        if cost >= 0
        else f"{-cost} XP back"
    )
    audit.record(
        db,
        staff,
        "house.trait_applied",
        troupe_id=troupe.id,
        character_id=character.id,
        what=f"{noun(house.category)} of {troupe.name}",
        name=marked(house.name),
        how=how,
        reason=reason,
    )
    if not npc:
        notifications.notify(
            db,
            [character.player_id],
            "sheet.given",
            f"{staff.display_name} gave {character.name} {troupe.name}'s {noun(house.category)}"
            f" {house.name} ({how}): {reason}",
            f"/characters/{character.id}",
            troupe_id=troupe.id,
            character_id=character.id,
        )
    return applied


def give_free(
    db: Session,
    staff: User,
    character: Character,
    house: HouseTrait,
    counts: bool,
    reason: str,
) -> None:
    """The trait at its points, all of them free dots, with a 0 XP line in the
    XP history saying why."""
    definition = db.get_one(TraitDefinition, house.trait_definition_id)
    category = db.get_one(TraitCategory, definition.category_id)
    if counts and category.points_limit is not None and house.category == "merits":
        held = sheets.held_points(db, character, category.key)
        if held + house.points > category.points_limit:
            raise conflict(
                f"That would bring {category.name.lower()} to {held + house.points} points; "
                f"a character can hold at most {category.points_limit}. "
                "Give it outside the merit limit, or not at all."
            )
    db.add(
        CharacterTrait(
            character_id=character.id,
            trait_definition_id=definition.id,
            rating=house.points,
            free_rating=house.points,
        )
    )
    if character.kind == "pc":
        db.add(
            XpEntry(
                character_id=character.id,
                kind="purchase",
                amount=0,
                reason=f"{house.name} 0 → {house.points}, given free by staff: {reason}",
                entered_by=staff.id,
                trait_definition_id=definition.id,
                from_rating=0,
                to_rating=house.points,
                cost_basis={"free": reason, "house_trait": str(house.id)},
            )
        )
    db.flush()


def remove(db: Session, staff: User, character: Character, house: HouseTrait, reason: str) -> int:
    """Staff take a house merit or flaw off a character, with a reason. Before a
    home troupe has accepted the character, what was paid for it comes back, as
    when a player takes back a purchase; after, as for a merit from the book
    (MET: VTM p. 236), nothing is refunded and a flaw's XP is kept. Returns the XP
    it gave back (negative for XP taken back)."""
    troupe = db.get_one(Troupe, house.troupe_id)
    sheets.ensure_unlocked(db, character)
    trait = applied_to(db, character, house)
    if trait is None:
        raise conflict(f"{character.name} does not have {house.name}.")
    if sheets.rules_troupe(character) != house.troupe_id:
        raise conflict(f"Only {troupe.name}'s staff, at home, remove its {noun(house.category)}.")
    refund = 0
    if character.kind == "pc" and not sheets.ever_accepted(db, character):
        refund = -sum(
            db.scalars(
                select(XpEntry.amount).where(
                    XpEntry.character_id == character.id,
                    XpEntry.trait_definition_id == house.trait_definition_id,
                )
            )
        )
    rating = trait.rating or 0
    with staff_change(db, staff, character):
        db.delete(trait)
        if character.kind == "pc":
            db.add(
                XpEntry(
                    character_id=character.id,
                    kind="purchase",
                    amount=refund,
                    reason=f"{house.name} {rating} → 0, removed by staff: {reason}",
                    entered_by=staff.id,
                    trait_definition_id=house.trait_definition_id,
                    from_rating=rating,
                    to_rating=0,
                    cost_basis={"removed": reason, "house_trait": str(house.id)},
                )
            )
    audit.record(
        db,
        staff,
        "house.trait_removed",
        troupe_id=troupe.id,
        character_id=character.id,
        what=f"{noun(house.category)} of {troupe.name}",
        name=marked(house.name),
        refund=refund,
        reason=reason,
    )
    if character.kind == "pc":
        notifications.notify(
            db,
            [character.player_id],
            "sheet.given",
            f"{staff.display_name} removed {troupe.name}'s {noun(house.category)}"
            f" {house.name} from {character.name}: {reason}",
            f"/characters/{character.id}",
            troupe_id=troupe.id,
            character_id=character.id,
        )
    return refund


def offered_to(db: Session, character: Character) -> list[HouseTrait]:
    """The house traits staff can apply to the character: its troupe's, not archived."""
    troupe_id = sheets.rules_troupe(character)
    if troupe_id is None:
        return []
    return list(
        db.scalars(
            select(HouseTrait)
            .where(
                HouseTrait.troupe_id == troupe_id,
                HouseTrait.splat == character.splat,
                HouseTrait.archived_at.is_(None),
            )
            .order_by(HouseTrait.category, HouseTrait.name)
        )
    )
