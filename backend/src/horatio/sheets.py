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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
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
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import PricingError, Quote, purchase_cost
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


def rules_for(db: Session, character: Character) -> TroupeRules:
    return read_troupe_rules(db, character.splat, character.home_troupe_id)


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

    if rating is None:
        raise unprocessable(f"{category.name} needs a rating.")
    fixed = definition.properties.get("rating")
    if fixed is not None and rating not in (0, fixed):
        raise unprocessable(f"{name} is always rated {fixed}.")

    current_rating = (current.trait.rating or 0) if current else 0
    current_free = current.trait.free_rating if current else 0
    if rating < current_free:
        raise unprocessable("A rating cannot go below its free dots.")

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


def set_trait(
    db: Session,
    player: User,
    character: Character,
    category_key: str,
    name: str,
    detail: str,
    rating: int | None,
    note: str | None = None,
) -> Change:
    """Add a trait, change its rating, or (at rating 0) remove it, buying or
    refunding the difference. Unrated traits replace the category's choice."""
    ensure_unlocked(db, character)
    definition, category = find_definition(db, character, category_key, name)

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
    if character.creation_completed_at is None:
        raise conflict(FINISH_CREATION_FIRST)
    quote, current_rating = quote_change(db, character, category_key, name, detail, rating)
    assert quote is not None and rating is not None and current_rating is not None

    accepted = accepted_ratings(db, character).get((category.key, definition.name, detail), 0)
    if rating < accepted:
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
    if rating != current_rating:
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
    if not approve and approval.kind == "discipline":
        undo_discipline(db, staff, character, approval, "declined")
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
    """What the log says about a discipline request: which discipline, to what rating."""
    if approval.kind != "discipline":
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
    if approval.kind == "discipline":
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
