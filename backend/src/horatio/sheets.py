"""Character sheets: traits, purchases, XP and approval.

The sheet as it stands lives in `character_traits`; each approval freezes a
copy as a `sheet_version`. Whatever differs from the latest frozen copy is
waiting for approval. Every rated change is a purchase in the XP history,
priced by the character's troupe rules (its home troupe's, or the plain rule
set before it has one).

A player may raise any rating, and may lower one only as far as its approved
rating: that undoes an unapproved purchase and refunds it. Taking away
approved dots is a storyteller's business, not the player's. While a change is
waiting for approval the sheet is locked, so what staff approve is what they
looked at.
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


def highest_approved_ratings(db: Session, character: Character) -> dict[TraitKey, int]:
    """For each trait, the highest rating any of the character's troupes has approved.
    A player cannot lower a trait below it."""
    highest: dict[TraitKey, int] = {}
    for m in memberships(db, character):
        for key, rating in approved_ratings(db, character, m.troupe_id).items():
            highest[key] = max(highest.get(key, 0), rating or 0)
    return highest


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
    if pending_approvals(db, character):
        raise conflict("Changes are waiting for approval. Withdraw them to edit the sheet.")


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
        for row in sheet_rows(db, character):
            if row.category.id == category.id:
                db.delete(row.trait)
        db.flush()
        trait = CharacterTrait(
            character_id=character.id, trait_definition_id=definition.id, rating=None, detail=detail
        )
        if note is not None:
            trait.note = note
        db.add(trait)
        db.flush()
        audit.record(
            db, player, "sheet.choose", character_id=character.id, category=category.key, name=name
        )
        return Change(quote=None, trait=trait)

    quote, current_rating = quote_change(db, character, category_key, name, detail, rating)
    assert quote is not None and rating is not None and current_rating is not None

    approved = highest_approved_ratings(db, character).get(
        (category.key, definition.name, detail), 0
    )
    if rating < approved:
        raise conflict(
            f"{name} is approved at {approved}. Only storytellers can take approved dots away."
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
    return Change(quote=quote, trait=trait)


def pending_changes(
    db: Session, character: Character, troupe_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    """How the sheet differs from the version `troupe_id` approved (everything, if none)."""
    approved = {
        (t["category"], t["name"], t["detail"]): t
        for t in approved_snapshot(db, character, troupe_id)
    }
    current = {r.key: r.snapshot() for r in sheet_rows(db, character)}
    changes: list[dict[str, Any]] = []
    for key in sorted(approved.keys() | current.keys()):
        before, after = approved.get(key), current.get(key)
        if before == after:
            continue
        changes.append(
            {
                "category": key[0],
                "name": key[1],
                "detail": key[2],
                "approved_rating": before["rating"] if before else None,
                "rating": after["rating"] if after else None,
                "added": before is None,
                "removed": after is None,
            }
        )
    return changes


def freeze_sheet(
    db: Session, approver: User, character: Character, troupe_id: uuid.UUID
) -> SheetVersion:
    """Freeze the sheet as it stands as `troupe_id`'s approved version, and make the
    character approved there."""
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
    found.standing = "approved"
    found.standing_note = ""
    return version


def needs_approval(db: Session, character: Character, m: TroupeMembership) -> bool:
    return m.standing == "draft" or bool(pending_changes(db, character, m.troupe_id))


def request_approval(db: Session, player: User, character: Character, note: str) -> list[Approval]:
    """Put the sheet to every troupe the character is in that has not approved it as
    it stands: drafts, and troupes whose approved sheet is out of date."""
    if character.creation_completed_at is None:
        raise conflict("Finish character creation before asking for approval.")
    ensure_unlocked(db, character)
    troupes = [m for m in memberships(db, character) if needs_approval(db, character, m)]
    if not troupes:
        raise conflict("Every troupe the character is in has approved the sheet as it stands.")
    approvals: list[Approval] = []
    for m in troupes:
        approval = Approval(
            character_id=character.id,
            troupe_id=m.troupe_id,
            kind="sheet_change",
            requested_by=player.id,
            player_note=note,
        )
        db.add(approval)
        db.flush()
        audit.record(
            db,
            player,
            "approval.request",
            troupe_id=approval.troupe_id,
            character_id=character.id,
            approval_id=approval.id,
            kind=approval.kind,
        )
        approvals.append(approval)
    return approvals


def return_to_draft(
    db: Session, staff: User, character: Character, troupe_id: uuid.UUID, reason: str
) -> TroupeMembership:
    found = membership(db, character, troupe_id)
    if found is None:
        raise conflict("The character is not in that troupe.")
    if found.standing == "draft":
        raise conflict("The character is already a draft in this troupe.")
    found.standing = "draft"
    found.standing_note = reason
    db.flush()
    audit.record(
        db, staff, "standing.draft", troupe_id=troupe_id, character_id=character.id, reason=reason
    )
    return found


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
    if approve and approval.kind == "sheet_change":
        freeze_sheet(db, staff, character, approval.troupe_id)
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
    )
    return approval


def withdraw(db: Session, player: User, approval: Approval) -> Approval:
    if approval.status != "pending":
        raise conflict(f"This request is already {approval.status}.")
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
