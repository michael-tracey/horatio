"""Joining troupes, and moving a character to a new home troupe.

A home troupe change finds two kinds of difference between the character and
the new troupe's rules (CONTEXT.md: Reconciliation):

- **Purchases.** What the character actually paid for each trait (purchases,
  and earlier settlements) against what the new rules charge.
- **Starting dots.** The character's creation picks against the new troupe's
  creation rules. Where the troupe gives fewer picks at a rating (or fewer
  points), enough of the character's picks there must be paid for at the new
  prices or removed. Where it gives more, the character may take them, which
  reopens character creation to place just those.

Each difference is settled one by one: the player proposes how, the new
troupe's storytellers or assistant storytellers confirm or change it, and a
character with any difference unsettled is not let in.

The character's XP is also set against the troupe's XP floor and ceiling
(horatio.xp_range): topped up below the floor if the player asks, and above the
ceiling or self-entered, kept or taken away as staff decide.

Approval moves the home troupe, applies the settlements, and freezes the sheet
as approved. For a character's first home troupe, that is also the sheet's
first approval.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, notifications, titles, xp_range
from horatio.creation import Pool, pools_for
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
from horatio.rules.model import SheetTrait, TroupeRules
from horatio.rules.pricing import NotAllowed, PricingError, trait_cost
from horatio.rules.splats import SPLATS
from horatio.rules.store import read_troupe_rules
from horatio.sheets import (
    HELD_KINDS,
    SheetRow,
    conflict,
    ensure_house_traits_fit,
    ensure_unlocked,
    freeze_sheet,
    pending_disciplines,
    rules_troupe,
    sheet_rows,
    sync_fixed_ratings,
    undo_discipline,
    unprocessable,
    xp_balance,
)

# Which group a difference belongs to, category, name, detail. A trait can have
# both a purchase difference and a starting-dot difference, settled separately.
ItemKey = tuple[str, str, str, str]

COST = "cost"
CREATION = "creation"


@dataclass
class Difference:
    category: str
    name: str
    detail: str
    trait_definition_id: uuid.UUID | None
    difference: str  # cost_differs | not_allowed | creation_differs
    rating: int
    old_cost: int
    new_cost: int | None
    # Starting-dot differences: the pool, and how much of it must be paid for or
    # removed across all its traits (picks, or points). Extra picks have no trait.
    pool_category: str | None = None
    pool_rating: int | None = None
    excess: int = 0
    extra_picks: int = 0
    can_remove: bool = False

    @property
    def group(self) -> str:
        return CREATION if self.difference == "creation_differs" else COST

    @property
    def key(self) -> ItemKey:
        return (self.group, self.category, self.name, self.detail)

    def allowed_settlements(self) -> tuple[str, ...]:
        if self.difference == "not_allowed":
            return ("remove_and_refund", "keep_price")
        if self.difference == "creation_differs":
            if self.extra_picks:
                return ("add_free_dots", "keep_price")
            choices = ["pay_for_dots"] if self.new_cost is not None else []
            if self.can_remove:
                choices.append("remove_dots")
            return (*choices, "keep_price")
        assert self.new_cost is not None
        change = "pay_difference" if self.new_cost > self.old_cost else "refund_difference"
        return (change, "keep_price", "remove_and_refund")

    def xp_delta(self, settlement: str) -> int:
        """XP gained (positive) or spent (negative) by settling this way."""
        if settlement in ("keep_price", "remove_dots", "add_free_dots"):
            return 0
        if settlement == "remove_and_refund":
            return self.old_cost
        assert self.new_cost is not None
        if settlement == "pay_for_dots":
            return -self.new_cost
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


def check_sect(db: Session, character: Character, troupe: Troupe) -> None:
    """A troupe can take player characters from only some sects. NPCs are its own."""
    if character.kind != "pc" or not troupe.allowed_sects:
        return
    sect = next(
        (r.definition.name for r in sheet_rows(db, character) if r.category.key == "sect"), None
    )
    if sect is None:
        raise conflict(
            f"{troupe.name} takes only {', '.join(troupe.allowed_sects)} characters. "
            "Choose a sect first."
        )
    if sect not in troupe.allowed_sects:
        raise conflict(f"{troupe.name} does not take {sect} characters.")


def check_splat(character: Character, troupe: Troupe) -> None:
    """A troupe takes player characters of only the splats it allows. NPCs are its own."""
    if character.kind == "pc" and character.splat not in troupe.allowed_splats:
        label = SPLATS[character.splat].label.lower() if character.splat in SPLATS else ""
        raise conflict(f"{troupe.name} does not take {label or character.splat} characters.")


def join(db: Session, player: User, character: Character, troupe: Troupe) -> TroupeMembership:
    if character.kind == "npc" and character.owner_troupe_id != troupe.id:
        raise conflict("An NPC belongs to its own troupe and cannot join others.")
    if troupe.archived_at is not None:
        raise conflict("That troupe is archived.")
    if character.status == "retired":
        raise conflict("This character is retired.")
    membership = current_membership(db, character, troupe)
    if membership is None:
        check_splat(character, troupe)
        check_sect(db, character, troupe)
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
    if character.kind == "npc":
        raise conflict("An NPC stays in its troupe until it is deleted.")
    end_membership(db, player, character, troupe, membership)
    audit.record(db, player, "troupe.leave", troupe_id=troupe.id, character_id=character.id)


def end_membership(
    db: Session, actor: User, character: Character, troupe: Troupe, membership: TroupeMembership
) -> None:
    """Take the character out of the troupe: its titles there end, it has no home
    troupe if this was it, and its requests waiting there are withdrawn. Its sheet,
    XP and history stay as they are. The caller logs why."""
    membership.left_at = datetime.now(UTC)
    # Its titles and who spoke for it at court were this troupe's.
    titles.drop_all(db, troupe.id, character.id)
    membership.represented_by = None
    if character.home_troupe_id == troupe.id:
        character.home_troupe_id = None
        sync_fixed_ratings(db, character)
    # Requests waiting in a troupe the character has left are moot.
    for approval in db.scalars(
        select(Approval).where(
            Approval.character_id == character.id,
            Approval.troupe_id == troupe.id,
            Approval.status == "pending",
        )
    ):
        if approval.kind in HELD_KINDS:
            undo_discipline(db, actor, character, approval, "withdrawn")
        approval.status = "withdrawn"
        approval.decided_at = datetime.now(UTC)
    db.flush()


# --- finding differences ----------------------------------------------------------------


def paid_for(db: Session, character: Character) -> Mapping[tuple[uuid.UUID, str], int]:
    """XP the character has paid for each (trait, detail), net of refunds, repricing
    and settlements."""
    purchases = db.execute(
        select(XpEntry.trait_definition_id, XpEntry.detail, func.sum(XpEntry.amount))
        .where(XpEntry.character_id == character.id, XpEntry.kind.in_(("purchase", "reprice")))
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
        if definition_id is None:
            continue
        key = (definition_id, detail or "")
        # A settlement that refunded XP lowered what was effectively paid.
        paid[key] = paid.get(key, 0) - amount
    return paid


def cost_differences(
    db: Session, character: Character, rules: TroupeRules, rows: Sequence[SheetRow]
) -> list[Difference]:
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


def cost_of_pick(rules: TroupeRules, rows: Sequence[SheetRow], row: SheetRow) -> int | None:
    """What a pick's free dots cost to buy under `rules`, or None if they cannot be bought."""
    sheet = [r.as_rules_trait() for r in rows]
    pick = row.trait.creation_pick or 0
    current = row.as_rules_trait()
    bought = SheetTrait(
        category=current.category,
        name=current.name,
        rating=current.rating,
        free_rating=current.free_rating - pick,
        detail=current.detail,
    )
    try:
        return trait_cost(rules, sheet, bought).cost - trait_cost(rules, sheet, current).cost
    except NotAllowed:
        return None
    except PricingError as error:
        raise unprocessable(f"{row.definition.name}: {error}") from error


def creation_differences(
    rules: TroupeRules, current_rules: TroupeRules, rows: Sequence[SheetRow], character: Character
) -> list[Difference]:
    """Picks the new troupe gives fewer of than the character placed (each trait
    in that pool, needing enough of them paid for or removed), and picks it gives
    more of than the character's current rules did."""
    if character.creation_completed_at is None:
        return []
    target = pools_for(rules.creation_rules(), rows)
    current = pools_for(current_rules.creation_rules(), rows)
    picked = [r for r in rows if r.trait.creation_pick is not None]
    placed = {id(r) for pool in target.values() for r in pool.traits}

    differences: list[Difference] = []

    def excess_items(rows_in_pool: Sequence[SheetRow], pool: Pool | None, excess: int) -> None:
        for row in rows_in_pool:
            pick = row.trait.creation_pick or 0
            differences.append(
                Difference(
                    category=row.category.key,
                    name=row.definition.name,
                    detail=row.trait.detail,
                    trait_definition_id=row.definition.id,
                    difference="creation_differs",
                    rating=pick,
                    old_cost=0,
                    new_cost=cost_of_pick(rules, rows, row),
                    pool_category=row.category.key,
                    pool_rating=pool.rating if pool else pick,
                    excess=excess,
                    can_remove=(row.trait.rating or 0) == row.trait.free_rating,
                )
            )

    # Picks that fit no pool in the new troupe's rules: every one is excess.
    strays: dict[tuple[str, int], list[SheetRow]] = {}
    for row in picked:
        if id(row) not in placed:
            strays.setdefault((row.category.key, row.trait.creation_pick or 0), []).append(row)
    for group in strays.values():
        points = all(r.category.house_rules_per_trait for r in group)
        excess_items(
            group, None, sum(r.trait.creation_pick or 0 for r in group) if points else len(group)
        )

    for pool in target.values():
        if pool.remaining < 0:
            excess_items(pool.traits, pool, -pool.remaining)
            continue
        before = current.get((pool.category, pool.rating))
        extra = pool.allowed - (before.allowed if before and before.kind == pool.kind else 0)
        if extra > 0 and pool.kind == "picks":
            unit = "pick" if extra == 1 else "picks"
            label = pool.category.replace("_", " ")
            differences.append(
                Difference(
                    category=pool.category,
                    name=f"{extra} more {label} {unit} at {pool.rating}",
                    detail="",
                    trait_definition_id=None,
                    difference="creation_differs",
                    rating=pool.rating,
                    old_cost=0,
                    new_cost=None,
                    pool_category=pool.category,
                    pool_rating=pool.rating,
                    extra_picks=extra,
                )
            )
    return differences


def find_differences(db: Session, character: Character, troupe: Troupe) -> list[Difference]:
    rules = read_troupe_rules(db, character.splat, troupe.id)
    current_rules = read_troupe_rules(db, character.splat, rules_troupe(character))
    rows = sheet_rows(db, character)
    return cost_differences(db, character, rules, rows) + creation_differences(
        rules, current_rules, rows, character
    )


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

    # Where the new troupe gives fewer starting dots, enough must be paid for or removed.
    covered: dict[tuple[str, int], int] = {}
    needed: dict[tuple[str, int], int] = {}
    for d in differences:
        if d.difference != "creation_differs" or not d.excess or d.pool_category is None:
            continue
        pool = (d.pool_category, d.pool_rating or 0)
        needed[pool] = d.excess
        if settlements[d.key] in ("pay_for_dots", "remove_dots"):
            points = d.pool_rating == 0
            covered[pool] = covered.get(pool, 0) + (d.rating if points else 1)
    short = [
        f"{c.replace('_', ' ')} at {r}"
        for (c, r), n in needed.items()
        if covered.get((c, r), 0) < n
    ]
    if short:
        raise unprocessable(
            "This troupe gives fewer starting dots: pay for or remove enough of these picks: "
            + ", ".join(short)
        )

    # A character in XP debt (horatio.xp_debt) can move, but not deeper into it.
    if xp + sum(d.xp_delta(settlements[d.key]) for d in differences) < min(0, xp):
        raise conflict("Those settlements cost more XP than the character has.")


def request_change(
    db: Session,
    player: User,
    character: Character,
    troupe: Troupe,
    settlements: Mapping[ItemKey, str],
    note: str,
    top_up: bool = True,
) -> Approval:
    if character.home_troupe_id == troupe.id:
        raise conflict("That is already the character's home troupe.")
    ensure_unlocked(db, character)
    if character.creation_completed_at is None:
        raise conflict("Finish character creation before choosing a home troupe.")
    if pending_disciplines(db, character):
        raise conflict(
            "Discipline dots are waiting for the home troupe's approval. "
            "Wait for its decision, or withdraw them, before moving."
        )
    ensure_house_traits_fit(db, character, troupe.id)
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
        approval_id=approval.id,
        from_troupe_id=character.home_troupe_id,
        to_troupe_id=troupe.id,
        top_up=top_up,
    )
    db.add(change)
    db.flush()
    for d in differences:
        db.add(
            ReconciliationItem(
                home_troupe_change_id=change.id,
                trait_definition_id=d.trait_definition_id,
                detail=d.detail if d.trait_definition_id else d.name,
                difference=d.difference,
                rating=d.rating,
                old_cost=d.old_cost,
                new_cost=d.new_cost,
                pool_category=d.pool_category,
                pool_rating=d.pool_rating,
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
    notifications.approval_waiting(db, approval)
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


def as_difference(
    item: ReconciliationItem, rows: Mapping[tuple[uuid.UUID, str], SheetRow]
) -> Difference:
    row = rows.get((item.trait_definition_id, item.detail)) if item.trait_definition_id else None
    return Difference(
        category=item.pool_category or "",
        name=item.detail if item.trait_definition_id is None else str(item.id),
        detail=item.detail,
        trait_definition_id=item.trait_definition_id,
        difference=item.difference,
        rating=item.rating,
        old_cost=item.old_cost,
        new_cost=item.new_cost,
        pool_category=item.pool_category,
        pool_rating=item.pool_rating,
        extra_picks=1
        if item.difference == "creation_differs" and item.trait_definition_id is None
        else 0,
        can_remove=row is not None and (row.trait.rating or 0) == row.trait.free_rating,
    )


def allowed_settlements(
    db: Session, approval: Approval, item: ReconciliationItem, character: Character
) -> tuple[str, ...]:
    rows = {(r.definition.id, r.trait.detail): r for r in sheet_rows(db, character)}
    return as_difference(item, rows).allowed_settlements()


def unbanked_xp(db: Session, character: Character) -> int:
    """Creation XP the character would lose on its first acceptance: everything
    unspent past the rule set's bank."""
    if character.home_troupe_id is not None:
        return 0
    limit = read_troupe_rules(db, character.splat, None).rule_set.banked_xp
    if limit is None:
        return 0
    return max(0, xp_balance(db, character) - limit)


def bank_creation_xp(db: Session, staff: User, character: Character) -> None:
    """On a first acceptance, unspent creation XP past the bank is lost (MET: VTM p. 107)."""
    lost = unbanked_xp(db, character)
    if lost:
        db.add(
            XpEntry(
                character_id=character.id,
                kind="fee",
                amount=-lost,
                reason="Unspent creation XP past the bank is lost on acceptance",
                entered_by=staff.id,
            )
        )
        db.flush()


def approve_change(
    db: Session,
    staff: User,
    approval: Approval,
    character: Character,
    overrides: Mapping[uuid.UUID, str],
    xp: xp_range.Decision | None = None,
) -> None:
    """Settle every difference (the player's proposal unless staff override it),
    settle the character's XP against the troupe's floor and ceiling, move the
    home troupe, and approve the sheet as it now stands."""
    change = db.scalars(
        select(HomeTroupeChange).where(HomeTroupeChange.approval_id == approval.id)
    ).one()
    items = items_for(db, approval)
    unknown = set(overrides) - {i.id for i in items}
    if unknown:
        raise unprocessable("Settlements were given for differences this request does not have.")

    rows = {(r.definition.id, r.trait.detail): r for r in sheet_rows(db, character)}
    total = 0
    for item in items:
        settlement = overrides.get(item.id, item.proposed_settlement)
        difference = as_difference(item, rows)
        if settlement not in difference.allowed_settlements():
            raise unprocessable(f"That difference cannot be settled with {settlement!r}.")
        delta = difference.xp_delta(settlement)
        item.settlement = settlement
        item.xp_delta = delta
        total += delta
    # A player character's XP against the troupe's floor and ceiling (horatio.xp_range).
    troupe = db.get_one(Troupe, change.to_troupe_id)
    decision = xp or xp_range.Decision()
    review = xp_range.review(db, character, troupe, change.top_up)
    plan = xp_range.plan(review, decision) if character.kind == "pc" else xp_range.Plan()
    balance = xp_balance(db, character)
    if balance + total + plan.delta < min(0, balance):
        raise conflict(
            "Those settlements cost more XP than the character has."
            if balance + total < min(0, balance)
            else f"{character.name} has spent that XP: taking it away would leave"
            " less than nothing. Keep it instead."
        )

    reopen = False
    for item in items:
        assert item.xp_delta is not None
        if item.xp_delta:
            db.add(
                XpEntry(
                    character_id=character.id,
                    kind="settlement",
                    amount=item.xp_delta,
                    reason="Joining a new home troupe: "
                    + (item.settlement or "").replace("_", " "),
                    entered_by=staff.id,
                    reconciliation_item_id=item.id,
                )
            )
        row = (
            rows.get((item.trait_definition_id, item.detail)) if item.trait_definition_id else None
        )
        if item.settlement == "remove_and_refund" and row is not None:
            if row.trait.free_rating:
                row.trait.rating = row.trait.free_rating
            else:
                db.delete(row.trait)
        elif item.settlement == "pay_for_dots" and row is not None:
            row.trait.free_rating -= row.trait.creation_pick or 0
            row.trait.creation_pick = None
        elif item.settlement == "remove_dots" and row is not None:
            db.delete(row.trait)
        elif item.settlement == "add_free_dots":
            reopen = True
    db.flush()

    # Self-entered XP and XP above the ceiling go before the bank, the top-up
    # after it, so none of the top-up is lost.
    if plan.self_entered_removed:
        xp_range.remove_self_entered(db, staff, character, troupe)
    xp_range.remove_above_ceiling(
        db, staff, character, troupe, plan.above_ceiling_removed, review.ceiling
    )
    old_troupe = change.from_troupe_id
    if old_troupe is None:
        bank_creation_xp(db, staff, character)
    xp_range.top_up(db, staff, character, troupe, plan.topped_up, review.floor)
    xp_range.give_extra(db, staff, character, troupe, plan.extra, decision.extra_reason)
    if character.kind == "pc":
        review.self_entered_removed = plan.self_entered_removed
        review.topped_up = plan.topped_up
        review.above_ceiling_removed = plan.above_ceiling_removed
        review.extra = plan.extra
        change.xp_review = review.as_record()
    if plan.delta or plan.self_entered_removed:
        audit.record(
            db,
            staff,
            "xp.joining",
            troupe_id=troupe.id,
            character_id=character.id,
            topped_up=plan.topped_up,
            extra=plan.extra,
            self_entered_removed=plan.self_entered_removed,
            above_ceiling_removed=plan.above_ceiling_removed,
        )
    character.home_troupe_id = change.to_troupe_id
    sync_fixed_ratings(db, character)
    # The sheet as the new home troupe accepted it: the floor for lowering ratings.
    freeze_sheet(db, staff, character, change.to_troupe_id)
    if reopen:
        # The new troupe gives more starting dots: let the player place them.
        character.creation_completed_at = None
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
