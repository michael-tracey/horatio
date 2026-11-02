"""Merits and flaws changed once a home troupe has accepted the character (MET: VTM
p. 236; CONTEXT.md: Approval).

After acceptance, adding a merit or flaw, or removing one, is for the storytellers to
allow. The player asks from the cart (`sheets.set_trait` hands the change here), and
it waits in the home troupe's approvals queue as a `merit_flaw` approval, with a
`DisciplinePurchase` saying what it changes. Unlike a discipline dot it is not on the
sheet while it waits: the sheet shows it as awaiting approval.

- **The XP.** A merit's cost, or a flaw's buy-off (twice its points, p. 236), is
  spent when asked and refunded if staff decline or the player withdraws. Removing a
  merit gives nothing back (p. 236). A flaw taken on gives its XP once approved.
- **Checks.** The change is tried on the sheet when asked, and refused then if the
  sheet couldn't hold it; approving makes it on the sheet as it is by then, and is
  refused if that sheet can't.
- **Approving** makes the change: a merit's effects begin, a flaw's end. Gaining a
  merit, or removing one, takes a downtime action (p. 236).
- **Free changes** (horatio.free_changes): while the character's are open, removing a
  merit refunds what its dots cost once approved, buying off a flaw costs what it gave
  rather than twice that, and neither takes a downtime action; as during creation.
- **Integral** merits and flaws, which stand for the character's Embrace, clan or
  bloodline (the rules' `creation_only`), can't be asked away, nor taken on.
- **A quest** (horatio.quests): staff may answer with one instead of a yes or no. The
  request is then tied to it: completing it approves the change, failing or closing it
  declines it. For a flaw the quest suggested is Complex at its points, or Epic 2 for a
  5-point flaw (Vol. II Issue 1, pp. 104-105).

Staff still give and take house merits and flaws directly (horatio.house_traits), and
before acceptance the player changes merits and flaws freely.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, free_changes, free_choices, notifications, quests, sheets, xp_debt
from horatio.models import (
    Approval,
    Character,
    CharacterTrait,
    DisciplinePurchase,
    Quest,
    TraitCategory,
    TraitDefinition,
    User,
    XpEntry,
)
from horatio.rules.model import FreeChoice, SheetTrait
from horatio.rules.pricing import PricingError, points, trait_cost

OPEN_QUEST = ("draft", "active")


@dataclass(frozen=True)
class Asked:
    """A merit or flaw change: which, from what rating to what, and for a merit the
    free traits chosen with it."""

    category: TraitCategory
    definition: TraitDefinition
    detail: str
    from_rating: int
    to_rating: int
    choices: tuple[FreeChoice, ...] = ()
    # A removal made as a free change (horatio.free_changes).
    free: bool = False

    @property
    def key(self) -> sheets.TraitKey:
        return (self.category.key, self.definition.name, self.detail)

    @property
    def label(self) -> str:
        name = self.definition.name
        return f"{name}: {self.detail}" if self.detail else name

    @property
    def adding(self) -> bool:
        return self.to_rating > self.from_rating

    @property
    def flaw(self) -> bool:
        return self.category.buy_off_factor is not None


def integral(name: str, adding: bool) -> str:
    if adding:
        return f"{name} can only be chosen during character creation."
    return (
        f"{name} is part of the character's history (its Embrace, clan or bloodline), "
        "so it can't be removed (MET: VTM p. 236)."
    )


def what_happens(asked: Asked, cost: int) -> str:
    """What asking does with the XP, in words, for the cart to say before it is asked."""
    if asked.free and asked.flaw:
        return (
            f"Asked of the home troupe as a free change: buying it off costs {cost} XP, "
            "what it gave, held until they decide."
        )
    if asked.free:
        return f"Asked of the home troupe as a free change: {-cost} XP back once they approve."
    if asked.adding and cost < 0:
        return f"Asked of the home troupe: it gives {-cost} XP once they approve."
    if asked.adding:
        return f"Asked of the home troupe: {cost} XP held until they decide."
    if asked.flaw:
        return (
            f"Asked of the home troupe: buying it off costs {cost} XP, twice what it gave, "
            "held until they decide."
        )
    return "Asked of the home troupe: removing a merit gives no XP back (MET: VTM p. 236)."


def ask(
    db: Session,
    player: User,
    character: Character,
    category: TraitCategory,
    definition: TraitDefinition,
    detail: str,
    rating: int,
    existing: CharacterTrait | None,
    picks: Sequence[FreeChoice] = (),
) -> sheets.Change:
    """Ask the home troupe's staff to add, change or remove a merit or flaw: price it,
    try it on the sheet, hold its XP, and put it in their queue."""
    name = definition.name
    current = (existing.rating or 0) if existing is not None else 0
    if rating == current:
        return sheets.Change(quote=None, trait=existing)
    asked = Asked(category, definition, detail, current, rating, tuple(picks))
    rule_set = sheets.rules_for(db, character).rule_set
    if sheets.locks_at(rule_set, category.key, name) is not None:
        raise sheets.conflict(integral(name, asked.adding))
    if any(
        d.trait_definition_id == definition.id and d.detail == detail
        for _, d in sheets.pending_purchases(db, character)
    ):
        raise sheets.conflict(
            f"{name} is waiting for the home troupe's approval. Withdraw that to change it."
        )
    quote = None
    if asked.adding:
        quote, _ = sheets.quote_change(db, character, category.key, name, detail, rating)
        assert quote is not None
        if category.points_limit is not None:
            quote = sheets.within_points_limit(
                db, character, category, definition, detail, rating, quote
            )
        cost = quote.cost
    else:
        assert existing is not None
        if existing.granted_rating and existing.granted_rating >= current:
            raise sheets.conflict(
                f"{name} comes from another trait on the sheet; it goes only with that."
            )
        if asked.flaw and rating:
            raise sheets.conflict(f"{name} is bought off whole, not in part.")
        asked = replace(asked, free=free_changes.refunds(db, character, category.key, name))
        cost = removal_cost(db, character, asked, existing)
    if cost > 0:
        balance = sheets.xp_balance(db, character)
        if balance < cost:
            raise sheets.conflict(xp_debt.short_of(balance, cost))
    reviewed = try_on(db, player, character, asked)

    assert character.home_troupe_id is not None
    if cost > 0:
        db.add(xp_line(character, player, asked, -cost, quote.rule.describe() if quote else {}))
    approval = Approval(
        character_id=character.id,
        troupe_id=character.home_troupe_id,
        kind=sheets.ASKED_KIND,
        requested_by=player.id,
        # As for a change held for review: the checks it breaks, for staff to weigh.
        player_note=" ".join(dict.fromkeys(reviewed)),
    )
    db.add(approval)
    db.flush()
    db.add(
        DisciplinePurchase(
            approval_id=approval.id,
            trait_definition_id=definition.id,
            detail=detail,
            from_rating=current,
            to_rating=rating,
            cost=cost,
            choices=[
                {"grant": p.grant, "name": p.name, "detail": p.detail, "amount": p.amount}
                for p in picks
            ],
            free_change=asked.free,
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
        **sheets.discipline_details(db, approval),
    )
    notifications.approval_waiting(db, approval)
    return sheets.Change(quote=quote, trait=existing, asked=what_happens(asked, cost))


def would_cost(
    db: Session, character: Character, category: str, name: str, detail: str, rating: int
) -> int | None:
    """What asking to lower or remove a merit or flaw would hold, for a refused cart
    line: nothing for a merit, twice its points for a flaw. None for anything else."""
    if not sheets.asks_home(character, category, by_staff=False, by_exception=None):
        return None
    row = next(
        (r for r in sheets.sheet_rows(db, character) if r.key == (category, name, detail)), None
    )
    current = (row.trait.rating or 0) if row is not None else 0
    if row is None or rating >= current:
        return None
    asked = Asked(row.category, row.definition, detail, current, rating)
    asked = replace(asked, free=free_changes.refunds(db, character, category, name))
    return removal_cost(db, character, asked, row.trait)


def removal_cost(db: Session, character: Character, asked: Asked, existing: CharacterTrait) -> int:
    """What asking to remove a merit or flaw holds: nothing for a merit, and twice its
    points to buy off a flaw. As a free change, a merit's dots refunded (negative) and
    a flaw's points once."""
    if not asked.free:
        return buy_off(db, character, asked) if asked.flaw else 0
    rules = sheets.rules_for(db, character)
    sheet = [r.as_rules_trait() for r in sheets.sheet_rows(db, character)]
    if asked.flaw:
        held = SheetTrait(asked.category.key, asked.definition.name, asked.from_rating, 0)
        return points(rules, sheet, held)
    held = SheetTrait(
        asked.category.key,
        asked.definition.name,
        asked.from_rating,
        min(existing.free_rating, asked.from_rating),
        asked.detail,
    )
    try:
        return -trait_cost(rules, sheet, held).cost
    except PricingError:
        return 0


def buy_off(db: Session, character: Character, asked: Asked) -> int:
    """What buying off a flaw costs: twice what it gave (MET: VTM p. 236)."""
    assert asked.category.buy_off_factor is not None
    rules = sheets.rules_for(db, character)
    sheet = [r.as_rules_trait() for r in sheets.sheet_rows(db, character)]
    held = SheetTrait(asked.category.key, asked.definition.name, asked.from_rating, 0, asked.detail)
    return asked.category.buy_off_factor * points(rules, sheet, held)


def xp_line(
    character: Character, user: User, asked: Asked, amount: int, basis: dict[str, object]
) -> XpEntry:
    return XpEntry(
        character_id=character.id,
        kind="purchase",
        amount=amount,
        reason=f"{asked.label} {asked.from_rating} → {asked.to_rating}",
        entered_by=user.id,
        trait_definition_id=asked.definition.id,
        detail=asked.detail or None,
        from_rating=asked.from_rating,
        to_rating=asked.to_rating,
        cost_basis=basis,
    )


def make(db: Session, actor: User, character: Character, asked: Asked) -> list[str]:
    """Make the change on the sheet, with no XP, and bring its grants into line;
    refused if the sheet then breaks a check it did not before. Says which checks the
    troupe has set to review it now breaks: staff decide it anyway."""
    before = sheets.sheet_state(db, character)
    trait = db.scalar(
        select(CharacterTrait).where(
            CharacterTrait.character_id == character.id,
            CharacterTrait.trait_definition_id == asked.definition.id,
            CharacterTrait.detail == asked.detail,
        )
    )
    if asked.adding:
        if trait is None:
            trait = CharacterTrait(
                character_id=character.id,
                trait_definition_id=asked.definition.id,
                rating=asked.to_rating,
                detail=asked.detail,
            )
            db.add(trait)
        else:
            trait.rating = asked.to_rating
        db.flush()
        if asked.choices:
            free_choices.set_choices(db, character, *asked.key, asked.choices)
    elif trait is not None:
        # What it opened goes with it, and the XP spent on that is lost (p. 236), but
        # for a free change.
        sheets.lose_opened(db, actor, character, asked.key, refund=asked.free)
        if asked.to_rating == 0:
            sheets.forget_opened(db, character, asked.key)
            db.delete(trait)
        else:
            trait.rating = asked.to_rating
            trait.free_rating = min(trait.free_rating, asked.to_rating)
            if trait.creation_pick is not None:
                trait.creation_pick = min(trait.creation_pick, trait.free_rating) or None
    db.flush()
    sheets.apply_grants(db, actor, character)
    sheets.lower_on_taking(db, character, before)
    refused = sheets.broken_since(db, None, character, before, creation_only=False).refused
    if refused:
        raise sheets.conflict(sheets.refusal(refused))
    reviewed = [
        v.message
        for v in sheets.sheet_violations(db, character)
        if v.key not in before.broken and v.check.strength == "review"
    ]
    limit = asked.category.points_limit
    if asked.adding and not asked.flaw and limit is not None:
        # Judged again here, as other requests may have been approved since it was asked.
        held = sheets.held_points(db, character, asked.category.key)
        if held > limit:
            raise sheets.conflict(
                f"That would bring {asked.category.name.lower()} to {held} points; "
                f"a character can hold at most {limit}."
            )
    return reviewed


def try_on(db: Session, actor: User, character: Character, asked: Asked) -> list[str]:
    """Whether the sheet could take the change now: made and taken back again. Says
    which review checks it would break."""
    savepoint = db.begin_nested()
    try:
        return make(db, actor, character, asked)
    finally:
        savepoint.rollback()
        db.expire_all()


def asked_of(db: Session, approval: Approval) -> tuple[Asked, DisciplinePurchase]:
    bought = db.scalars(
        select(DisciplinePurchase).where(DisciplinePurchase.approval_id == approval.id)
    ).one()
    definition = db.get_one(TraitDefinition, bought.trait_definition_id)
    category = db.get_one(TraitCategory, definition.category_id)
    asked = Asked(
        category,
        definition,
        bought.detail,
        bought.from_rating,
        bought.to_rating,
        tuple(FreeChoice(**c) for c in bought.choices),
        bought.free_change,
    )
    return asked, bought


def ensure_not_questing(db: Session, approval: Approval) -> None:
    quest = db.get(Quest, approval.quest_id) if approval.quest_id else None
    if quest is not None and quest.status in OPEN_QUEST:
        raise sheets.conflict(
            f"This request waits on the quest {quest.name}: completing it approves the "
            "change, and failing or closing it declines it."
        )


def decided(
    db: Session, staff: User, character: Character, approval: Approval, approve: bool
) -> None:
    """Approving makes the change and takes its downtime action; declining refunds."""
    if not approve:
        refund(db, staff, character, approval, "declined")
        return
    asked, bought = asked_of(db, approval)
    savepoint = db.begin_nested()
    try:
        make(db, staff, character, asked)
    except BaseException:
        savepoint.rollback()
        raise
    savepoint.commit()
    name = asked.definition.name
    if asked.adding:
        owed = sheets.owed_for(
            db, character, asked.category, asked.to_rating - asked.from_rating, True, name
        )
        sheets.owe(db, staff, character, owed.actions, owed.reason(f"Gaining {name}"))
    elif (
        asked.category.downtime_actions and character.home_troupe_id is not None and not asked.free
    ):
        # Removing a merit takes a downtime action too (p. 236), but not as a free change.
        sheets.owe(db, staff, character, asked.category.downtime_actions, f"Removing {name}")
    if bought.cost < 0:
        db.add(xp_line(character, staff, asked, -bought.cost, {"approved": True}))
    if asked.free:
        audit.record(
            db,
            staff,
            "sheet.free_change",
            troupe_id=approval.troupe_id,
            character_id=character.id,
            name=asked.label,
            from_rating=asked.from_rating,
            to_rating=asked.to_rating,
            refund=-bought.cost,
        )
    db.flush()


def refund(db: Session, user: User, character: Character, approval: Approval, why: str) -> None:
    """Give back the XP a request held. The sheet was never changed."""
    asked, bought = asked_of(db, approval)
    if bought.cost > 0:
        db.add(
            XpEntry(
                character_id=character.id,
                kind="purchase",
                amount=bought.cost,
                reason=f"{asked.label} {asked.to_rating} → {asked.from_rating} ({why})",
                entered_by=user.id,
                trait_definition_id=asked.definition.id,
                detail=asked.detail or None,
                from_rating=asked.to_rating,
                to_rating=asked.from_rating,
                cost_basis={"refund": why},
            )
        )
        db.flush()


# --- answered with a quest ------------------------------------------------------------


def describe(db: Session, approval: Approval) -> str:
    """What the request asks, as "Agnes buys off Dark Fate"."""
    asked, _ = asked_of(db, approval)
    character = db.get_one(Character, approval.character_id)
    if asked.adding:
        verb = "takes on" if asked.flaw else "gains"
    else:
        verb = "buys off" if asked.flaw else "loses"
    return f"{character.name} {verb} {asked.label}"


@dataclass(frozen=True)
class Suggestion:
    """The quest the builder starts from, for a request answered with one."""

    name: str
    objective: str
    category: Literal["simple", "complex", "epic"]
    difficulty: int


def suggestion(db: Session, approval: Approval) -> Suggestion:
    """Buying off a flaw is a Complex quest at its points, and a 5-point flaw an Epic
    one at difficulty 2 (Vol. II Issue 1, pp. 104-105). The book suggests nothing for
    a merit, so the builder starts as it always does."""
    asked, _ = asked_of(db, approval)
    objective = f"{describe(db, approval)}."
    if asked.flaw and not asked.adding:
        name = f"Buy off {asked.label}"
        if asked.from_rating >= 5:
            return Suggestion(name, objective, "epic", 2)
        return Suggestion(name, objective, "complex", max(1, asked.from_rating))
    if asked.adding:
        name = f"{'Take on' if asked.flaw else 'Gain'} {asked.label}"
    else:
        name = f"Lose {asked.label}"
    return Suggestion(name, objective, "simple", 1)


def can_answer_with_quest(db: Session, approval: Approval) -> str | None:
    """Why a request can't be answered with a quest, if it can't."""
    if approval.kind != sheets.ASKED_KIND:
        return "Only a merit or flaw request is answered with a quest."
    if approval.status != "pending":
        return f"This request is already {approval.status}."
    quest = db.get(Quest, approval.quest_id) if approval.quest_id else None
    if quest is not None and quest.status in OPEN_QUEST:
        return f"This request is already answered with the quest {quest.name}."
    return None


def tie(db: Session, staff: User, approval: Approval, quest: Quest) -> None:
    """Tie a request to the quest built to answer it."""
    refusal = can_answer_with_quest(db, approval)
    if refusal is not None:
        raise sheets.conflict(refusal)
    approval.quest_id = quest.id
    quests.log(db, quest, staff, f"built it to answer a request: {describe(db, approval)}")
    db.flush()
    audit.record(
        db,
        staff,
        "approval.quest",
        troupe_id=approval.troupe_id,
        character_id=approval.character_id,
        approval_id=approval.id,
        kind=approval.kind,
        quest=quest.name,
        **sheets.discipline_details(db, approval),
    )


def quest_ended(db: Session, staff: User, quest: Quest, approve: bool, note: str = "") -> None:
    """A quest that answers requests has ended: completed, it approves them; failed or
    closed, it declines them. One the sheet can no longer take stays in the approvals
    queue, for staff to decide, and the quest's log says why."""
    waiting = db.scalars(
        select(Approval).where(Approval.quest_id == quest.id, Approval.status == "pending")
    )
    said = note or f"The quest {quest.name} was {quest.status}."
    for approval in list(waiting):
        savepoint = db.begin_nested()
        try:
            sheets.decide(db, staff, approval, approve, said, by_quest=True)
        except HTTPException as error:
            savepoint.rollback()
            db.expire_all()
            quests.log(
                db,
                quest,
                staff,
                f"couldn't approve the request ({describe(db, approval)}): {error.detail} "
                "It waits in the approvals queue.",
            )
            continue
        savepoint.commit()
        verb = "approved" if approve else "declined"
        quests.log(db, quest, staff, f"{verb} the request: {describe(db, approval)}")
