"""Joining troupes, and moving a character to a new home troupe.

A home troupe change compares what the character actually paid for each trait
(its purchases, and any earlier settlements) with what the new troupe's rules
charge. Each difference is settled one by one: the player proposes how, the
new troupe's storytellers or assistant storytellers confirm or change it, and
a character with any difference unsettled is not let in (CONTEXT.md:
Reconciliation).

Approval moves the home troupe, applies the settlements as XP entries, and
freezes the sheet as approved. For a character's first home troupe, that is
also the sheet's first approval.

Creation-rule differences are not reconciled yet; creation rules do not exist.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import (
    Approval,
    Character,
    HomeTroupeChange,
    ReconciliationItem,
    Troupe,
    TroupeMembership,
    User,
    XpEntry,
)
from horatio.rules.pricing import NotAllowed, PricingError, trait_cost
from horatio.rules.store import read_troupe_rules
from horatio.sheets import (
    conflict,
    ensure_unlocked,
    freeze_sheet,
    sheet_rows,
    unprocessable,
    xp_balance,
)

ItemKey = tuple[str, str, str]  # category, name, detail


@dataclass
class Difference:
    category: str
    name: str
    detail: str
    trait_definition_id: uuid.UUID
    difference: str  # cost_differs | not_allowed
    rating: int
    old_cost: int
    new_cost: int | None

    @property
    def key(self) -> ItemKey:
        return (self.category, self.name, self.detail)

    def allowed_settlements(self) -> tuple[str, ...]:
        if self.difference == "not_allowed":
            return ("remove_and_refund", "keep_price")
        assert self.new_cost is not None
        change = "pay_difference" if self.new_cost > self.old_cost else "refund_difference"
        return (change, "keep_price", "remove_and_refund")

    def xp_delta(self, settlement: str) -> int:
        """XP gained (positive) or spent (negative) by settling this way."""
        if settlement == "keep_price":
            return 0
        if settlement == "remove_and_refund":
            return self.old_cost
        assert self.new_cost is not None
        return self.old_cost - self.new_cost


# --- membership ---------------------------------------------------------------------


def current_membership(
    db: Session, character: Character, troupe: Troupe
) -> TroupeMembership | None:
    return db.scalar(
        select(TroupeMembership).where(
            TroupeMembership.character_id == character.id,
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
        )
    )


def join(db: Session, player: User, character: Character, troupe: Troupe) -> TroupeMembership:
    if troupe.archived_at is not None:
        raise conflict("That troupe is archived.")
    if character.status == "retired":
        raise conflict("This character is retired.")
    membership = current_membership(db, character, troupe)
    if membership is None:
        membership = TroupeMembership(troupe_id=troupe.id, character_id=character.id)
        db.add(membership)
        db.flush()
        audit.record(db, player, "troupe.join", troupe_id=troupe.id, character_id=character.id)
    return membership


def leave(db: Session, player: User, character: Character, troupe: Troupe) -> None:
    membership = current_membership(db, character, troupe)
    if membership is None:
        raise conflict("The character is not in that troupe.")
    pending = pending_change(db, character)
    if pending is not None and pending[1].to_troupe_id == troupe.id:
        raise conflict("Withdraw the request to make this the home troupe first.")
    membership.left_at = datetime.now(UTC)
    if character.home_troupe_id == troupe.id:
        character.home_troupe_id = None
    db.flush()
    audit.record(db, player, "troupe.leave", troupe_id=troupe.id, character_id=character.id)


# --- finding differences ----------------------------------------------------------------


def paid_for(db: Session, character: Character) -> Mapping[tuple[uuid.UUID, str], int]:
    """XP the character has paid for each (trait, detail), net of refunds and settlements."""
    purchases = db.execute(
        select(XpEntry.trait_definition_id, XpEntry.detail, func.sum(XpEntry.amount))
        .where(XpEntry.character_id == character.id, XpEntry.kind == "purchase")
        .group_by(XpEntry.trait_definition_id, XpEntry.detail)
    )
    settlements = db.execute(
        select(
            ReconciliationItem.trait_definition_id,
            ReconciliationItem.detail,
            func.sum(XpEntry.amount),
        )
        .join(XpEntry, XpEntry.reconciliation_item_id == ReconciliationItem.id)
        .where(XpEntry.character_id == character.id)
        .group_by(ReconciliationItem.trait_definition_id, ReconciliationItem.detail)
    )
    paid: dict[tuple[uuid.UUID, str], int] = {}
    for definition_id, detail, amount in purchases:
        assert definition_id is not None
        key = (definition_id, detail or "")
        paid[key] = paid.get(key, 0) - amount
    for definition_id, detail, amount in settlements:
        key = (definition_id, detail or "")
        # A settlement that refunded XP lowered what was effectively paid.
        paid[key] = paid.get(key, 0) - amount
    return paid


def find_differences(db: Session, character: Character, troupe: Troupe) -> list[Difference]:
    rules = read_troupe_rules(db, character.splat, troupe.id)
    rows = sheet_rows(db, character)
    sheet = [r.as_rules_trait() for r in rows]
    paid = paid_for(db, character)
    differences: list[Difference] = []
    for row in rows:
        if not row.category.rated or not row.trait.rating:
            continue
        old_cost = paid.get((row.definition.id, row.trait.detail), 0)
        base = Difference(
            category=row.category.key,
            name=row.definition.name,
            detail=row.trait.detail,
            trait_definition_id=row.definition.id,
            difference="cost_differs",
            rating=row.trait.rating,
            old_cost=old_cost,
            new_cost=None,
        )
        try:
            new_cost = trait_cost(rules, sheet, row.as_rules_trait()).cost
        except NotAllowed:
            base.difference = "not_allowed"
            differences.append(base)
            continue
        except PricingError as error:
            raise unprocessable(f"{row.definition.name}: {error}") from error
        if new_cost != old_cost:
            base.new_cost = new_cost
            differences.append(base)
    return differences


# --- requesting and deciding ----------------------------------------------------------


def pending_change(db: Session, character: Character) -> tuple[Approval, HomeTroupeChange] | None:
    found = db.execute(
        select(Approval, HomeTroupeChange)
        .join(HomeTroupeChange, HomeTroupeChange.approval_id == Approval.id)
        .where(
            Approval.character_id == character.id,
            Approval.kind == "home_troupe_change",
            Approval.status == "pending",
        )
    ).first()
    return (found[0], found[1]) if found else None


def check_settlements(
    differences: list[Difference], settlements: Mapping[ItemKey, str], xp: int
) -> None:
    missing = [d.name for d in differences if d.key not in settlements]
    if missing:
        raise unprocessable(
            "Every difference needs a settlement before the character can join: "
            + ", ".join(missing)
        )
    for d in differences:
        if settlements[d.key] not in d.allowed_settlements():
            raise unprocessable(f"{d.name} cannot be settled with {settlements[d.key]!r}.")
    if xp + sum(d.xp_delta(settlements[d.key]) for d in differences) < 0:
        raise conflict("Those settlements cost more XP than the character has.")


def request_change(
    db: Session,
    player: User,
    character: Character,
    troupe: Troupe,
    settlements: Mapping[ItemKey, str],
    note: str,
) -> Approval:
    if character.home_troupe_id == troupe.id:
        raise conflict("That is already the character's home troupe.")
    ensure_unlocked(db, character)
    join(db, player, character, troupe)

    differences = find_differences(db, character, troupe)
    check_settlements(differences, settlements, xp_balance(db, character))

    approval = Approval(
        character_id=character.id,
        troupe_id=troupe.id,
        kind="home_troupe_change",
        requested_by=player.id,
        player_note=note,
    )
    db.add(approval)
    db.flush()
    change = HomeTroupeChange(
        approval_id=approval.id, from_troupe_id=character.home_troupe_id, to_troupe_id=troupe.id
    )
    db.add(change)
    db.flush()
    for d in differences:
        db.add(
            ReconciliationItem(
                home_troupe_change_id=change.id,
                trait_definition_id=d.trait_definition_id,
                detail=d.detail,
                difference=d.difference,
                rating=d.rating,
                old_cost=d.old_cost,
                new_cost=d.new_cost,
                proposed_settlement=settlements[d.key],
            )
        )
    db.flush()
    audit.record(
        db,
        player,
        "approval.request",
        troupe_id=troupe.id,
        character_id=character.id,
        approval_id=approval.id,
        kind=approval.kind,
        differences=len(differences),
    )
    return approval


def items_for(db: Session, approval: Approval) -> list[ReconciliationItem]:
    return list(
        db.scalars(
            select(ReconciliationItem)
            .join(HomeTroupeChange, ReconciliationItem.home_troupe_change_id == HomeTroupeChange.id)
            .where(HomeTroupeChange.approval_id == approval.id)
            .order_by(ReconciliationItem.id)
        )
    )


def as_difference(item: ReconciliationItem) -> Difference:
    return Difference(
        category="",
        name=str(item.id),
        detail=item.detail,
        trait_definition_id=item.trait_definition_id,
        difference=item.difference,
        rating=item.rating,
        old_cost=item.old_cost,
        new_cost=item.new_cost,
    )


def approve_change(
    db: Session,
    staff: User,
    approval: Approval,
    character: Character,
    overrides: Mapping[uuid.UUID, str],
) -> None:
    """Settle every difference (the player's proposal unless staff override it),
    move the home troupe, and approve the sheet as it now stands."""
    change = db.scalars(
        select(HomeTroupeChange).where(HomeTroupeChange.approval_id == approval.id)
    ).one()
    items = items_for(db, approval)
    unknown = set(overrides) - {i.id for i in items}
    if unknown:
        raise unprocessable("Settlements were given for differences this request does not have.")

    total = 0
    for item in items:
        settlement = overrides.get(item.id, item.proposed_settlement)
        difference = as_difference(item)
        if settlement not in difference.allowed_settlements():
            raise unprocessable(f"That difference cannot be settled with {settlement!r}.")
        delta = difference.xp_delta(settlement)
        item.settlement = settlement
        item.xp_delta = delta
        total += delta
    if xp_balance(db, character) + total < 0:
        raise conflict("Those settlements cost more XP than the character has.")

    rows = {(r.definition.id, r.trait.detail): r for r in sheet_rows(db, character)}
    for item in items:
        assert item.xp_delta is not None
        if item.xp_delta:
            db.add(
                XpEntry(
                    character_id=character.id,
                    kind="settlement",
                    amount=item.xp_delta,
                    reason=f"Joining a new home troupe: {item.settlement.replace('_', ' ')}"
                    if item.settlement
                    else "Joining a new home troupe",
                    entered_by=staff.id,
                    reconciliation_item_id=item.id,
                )
            )
        if item.settlement == "remove_and_refund":
            row = rows.get((item.trait_definition_id, item.detail))
            if row is not None:
                if row.trait.free_rating:
                    row.trait.rating = row.trait.free_rating
                else:
                    db.delete(row.trait)
    db.flush()

    old_troupe = change.from_troupe_id
    character.home_troupe_id = change.to_troupe_id
    character.status = "active"
    freeze_sheet(db, staff, character)
    if old_troupe is not None:
        # So the old troupe's staff can see their character has moved.
        audit.record(
            db,
            staff,
            "home_troupe.moved_away",
            troupe_id=old_troupe,
            character_id=character.id,
            to_troupe_id=change.to_troupe_id,
        )
