"""A troupe's house rules: its settings for checks (switching one off, or changing
how strict it is), its own prices for traits, what new characters start with,
and how many downtime actions characters get."""

import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from horatio import audit, diablerie
from horatio.api.downtimes import staff_troupe
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.creation import RESTRICTION_TEXT
from horatio.models import User
from horatio.permissions import TroupeAction
from horatio.rules import checks, conditions, pricing
from horatio.rules.model import (
    ActionKindData,
    AllowanceRuleData,
    CostRuleData,
    CreationRuleData,
    RuleSetData,
    Scheme,
)
from horatio.rules.splats import SPLATS
from horatio.rules.store import (
    DuplicateHouseRule,
    add_house_allowance_rule,
    add_house_rule,
    change_house_allowance_rule,
    change_house_rule,
    house_allowance_rules,
    house_cost_rules,
    read_troupe_rules,
    remove_house_allowance_rule,
    remove_house_rule,
    same_subject,
    set_check_override,
    set_house_creation_rules,
)
from horatio.sheets import sync_troupe_fixed_ratings

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["house rules"])

Strength = Literal["refuse", "complete", "review", "note", "off"]


class CheckOut(BaseModel):
    key: str
    # What it is about: a trait, a category, or names starting with a prefix.
    category: str
    about: str
    message: str
    page: str | None
    # As the rule set has it, and as this troupe plays it.
    strength: str
    house: str | None


class CheckChange(BaseModel):
    # None goes back to the rule set's strength.
    strength: Strength | None


def checks_out(db: DbSession, troupe_id: uuid.UUID, splat: str = "vampire") -> list[CheckOut]:
    rules = read_troupe_rules(db, splat, troupe_id)
    return [
        CheckOut(
            key=c.key,
            category=c.category,
            about=c.name or (f"{c.name_prefix}…" if c.name_prefix else "any"),
            message=c.message,
            page=c.page,
            strength=c.strength,
            house=rules.check_overrides.get(c.key),
        )
        for c in rules.rule_set.checks
    ]


@router.get("/checks")
def list_checks(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[CheckOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return checks_out(db, troupe_id)


@router.put("/checks/{key:path}")
def change_check(
    troupe_id: uuid.UUID, key: str, body: CheckChange, db: DbSession, user: CurrentUser
) -> CheckOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    known = {c.key for c in read_troupe_rules(db, "vampire", troupe_id).rule_set.checks}
    if key not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such check.")
    set_check_override(db, troupe.id, key, body.strength)
    audit.record(
        db,
        user,
        "house.check",
        troupe_id=troupe.id,
        check=key,
        strength=body.strength or "as the rules say",
    )
    db.commit()
    return next(c for c in checks_out(db, troupe_id) if c.key == key)


# --- Costs -----------------------------------------------------------------


class CostCategoryOut(BaseModel):
    key: str
    name: str
    group: str
    max_rating: int | None
    # Merits and flaws: a troupe prices them one trait at a time.
    per_trait: bool
    # What a rating counts: "point" for merits and flaws, "dot" otherwise.
    unit: str


class CostOut(BaseModel):
    # Set for the troupe's own prices; None for the rule set's.
    id: uuid.UUID | None
    category: str
    trait: str | None
    condition: dict[str, Any] | None
    # The condition and the price in plain words.
    condition_text: str | None
    price_text: str
    scheme: Scheme
    rate: int | None
    table: list[int] | None
    # A house rule's own wording, shown to players.
    text: str | None
    page: str | None
    # For a merit or flaw always held at one rating: that rating, by the book. A
    # troupe's fixed price for it is its value instead.
    fixed_rating: int | None = None
    house: bool
    # A rule set price this troupe has its own price for, under the same condition.
    replaced: bool = False


class CostsOut(BaseModel):
    categories: list[CostCategoryOut]
    # By category, each troupe price after the rule set price it replaces.
    costs: list[CostOut]


class CostChange(BaseModel):
    scheme: Scheme
    rate: int | None = None
    table: list[int] | None = None
    text: str | None = None


class CostIn(CostChange):
    category: str
    trait: str | None = None
    # Only a rule set price's own condition, to give that price a new amount here.
    condition: dict[str, Any] | None = None


def unit(rule_set: RuleSetData, category: str) -> str:
    return "point" if rule_set.categories[category].points_limit is not None else "dot"


def cost_out(
    rule_set: RuleSetData, rule: CostRuleData, rule_id: uuid.UUID | None, *, replaced: bool = False
) -> CostOut:
    trait = rule_set.traits.get((rule.category, rule.trait)) if rule.trait else None
    return CostOut(
        id=rule_id,
        category=rule.category,
        trait=rule.trait,
        condition=dict(rule.condition) if rule.condition else None,
        condition_text=conditions.describe(rule.condition, SPLATS[rule_set.splat].fact_words),
        price_text=pricing.describe(rule, unit(rule_set, rule.category)),
        scheme=rule.scheme,
        rate=rule.rate,
        table=list(rule.table) if rule.table is not None else None,
        text=rule.text,
        page=trait.page_reference if trait else None,
        fixed_rating=trait.properties.get("rating") if trait else None,
        house=rule.house,
        replaced=replaced,
    )


def costs_out(db: DbSession, troupe_id: uuid.UUID, splat: str = "vampire") -> CostsOut:
    rules = read_troupe_rules(db, splat, troupe_id)
    house = house_cost_rules(db, splat, troupe_id)
    position = {key: n for n, key in enumerate(rules.rule_set.categories)}

    def order(cost: CostOut) -> tuple[int, bool, str, str, bool]:
        # A troupe price right after the rule set price it replaces.
        when = cost.condition_text or ""
        return (position[cost.category], cost.trait is not None, cost.trait or "", when, cost.house)

    generic = [
        cost_out(rules.rule_set, r, None, replaced=any(same_subject(h, r) for _, h in house))
        for r in rules.rule_set.cost_rules
    ]
    return CostsOut(
        categories=[
            CostCategoryOut(
                key=c.key,
                name=c.name,
                group=c.group,
                max_rating=c.max_rating,
                per_trait=c.house_rules_per_trait,
                unit=unit(rules.rule_set, c.key),
            )
            for c in rules.rule_set.categories.values()
            if c.rated and not c.derived
        ],
        costs=sorted([*generic, *(cost_out(rules.rule_set, r, i) for i, r in house)], key=order),
    )


def sync_values(db: DbSession, troupe_id: uuid.UUID, rule: CostRuleData) -> None:
    """A troupe's fixed price for a fixed-rating merit or flaw is its value: hold
    the troupe's characters' copies at it."""
    rule_set = read_troupe_rules(db, "vampire", troupe_id).rule_set
    if rule.trait and rule_set.trait_properties(rule.category, rule.trait).get("rating"):
        sync_troupe_fixed_ratings(db, troupe_id)


def log_price(
    db: DbSession, user: User, action: str, troupe_id: uuid.UUID, rule: CostRuleData
) -> None:
    """What the troupe log says about a price."""
    rule_set = read_troupe_rules(db, "vampire", troupe_id).rule_set
    what = rule.trait or rule_set.categories[rule.category].name
    when = conditions.describe(rule.condition, SPLATS[rule_set.splat].fact_words)
    audit.record(
        db,
        user,
        action,
        troupe_id=troupe_id,
        what=f"{what} ({when})" if when else what,
        price=pricing.describe(rule, unit(rule_set, rule.category)),
    )


def priced(
    body: CostChange, category: str, trait: str | None, condition: Mapping[str, Any] | None
) -> CostRuleData:
    """A house rule pricing `trait` (or the category) as `body` says, keeping only
    the amount or table its scheme uses."""
    return CostRuleData(
        category=category,
        trait=trait,
        condition=condition,
        scheme=body.scheme,
        rate=body.rate if body.scheme in ("per_dot", "progressive", "fixed") else None,
        table=tuple(body.table) if body.scheme == "table" and body.table is not None else None,
        text=(body.text or "").strip() or None,
        house=True,
    )


def house_cost(troupe_id: uuid.UUID, db: DbSession, cost_id: uuid.UUID) -> CostRuleData:
    found = dict(house_cost_rules(db, "vampire", troupe_id)).get(cost_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such price.")
    return found


@router.get("/costs")
def list_costs(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CostsOut:
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return costs_out(db, troupe_id)


@router.post("/costs", status_code=status.HTTP_201_CREATED)
def add_cost(troupe_id: uuid.UUID, body: CostIn, db: DbSession, user: CurrentUser) -> CostOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    if body.category not in rule_set.categories:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such category.")
    if body.trait is not None and (body.category, body.trait) not in rule_set.traits:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such trait.")
    rule = priced(body, body.category, body.trait, body.condition or None)
    if rule.condition and not any(same_subject(r, rule) for r in rule_set.cost_rules):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A troupe price can only have the condition of a rule set price it replaces.",
        )
    try:
        row = add_house_rule(db, troupe.id, "vampire", rule)
    except DuplicateHouseRule:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The troupe already has a price for that; change it instead."
        ) from None
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    sync_values(db, troupe.id, rule)
    log_price(db, user, "house.cost_added", troupe.id, rule)
    db.commit()
    return next(c for c in costs_out(db, troupe.id).costs if c.id == row.id)


@router.put("/costs/{cost_id}")
def change_cost(
    troupe_id: uuid.UUID, cost_id: uuid.UUID, body: CostChange, db: DbSession, user: CurrentUser
) -> CostOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    old = house_cost(troupe.id, db, cost_id)
    rule = priced(body, old.category, old.trait, old.condition)
    try:
        change_house_rule(db, troupe.id, "vampire", cost_id, rule)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    sync_values(db, troupe.id, rule)
    log_price(db, user, "house.cost_changed", troupe.id, rule)
    db.commit()
    return next(c for c in costs_out(db, troupe.id).costs if c.id == cost_id)


@router.delete("/costs/{cost_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_cost(
    troupe_id: uuid.UUID, cost_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    old = house_cost(troupe.id, db, cost_id)
    remove_house_rule(db, troupe.id, cost_id)
    sync_values(db, troupe.id, old)
    log_price(db, user, "house.cost_removed", troupe.id, old)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Starting points ---------------------------------------------------------


class StartingRule(BaseModel):
    """Picks at a rating (`picks` and `rating`), or a budget of `points`."""

    rating: int | None = None
    picks: int | None = None
    points: int | None = None
    # A fact the trait must have to take a pick: "in_clan".
    restriction: str | None = None
    # Only while the sheet meets this; only a rule set rule's own condition.
    when: dict[str, Any] | None = None
    when_text: str | None = None


class StartingCategoryOut(BaseModel):
    key: str
    name: str
    max_rating: int | None
    # As this troupe plays it, and as the rule set has it.
    rules: list[StartingRule]
    book: list[StartingRule]
    text: str
    book_text: str
    house: bool


class StartingChange(BaseModel):
    rules: list[StartingRule]


def starting_rule(rule: CreationRuleData) -> StartingRule:
    return StartingRule(
        rating=rule.rating,
        picks=rule.picks,
        points=rule.points,
        restriction=rule.restriction,
        when=dict(rule.when) if rule.when else None,
        when_text=checks.describe(rule.when) if rule.when else None,
    )


def describe_starting(rules: list[CreationRuleData]) -> str:
    """A category's starting picks or points in plain words: "1 at 4, 2 at 3"."""
    if not rules:
        return "none"
    parts: list[str] = []
    for rule in sorted(rules, key=lambda r: -(r.rating or 0)):
        part = (
            f"{rule.points} points" if rule.points is not None else f"{rule.picks} at {rule.rating}"
        )
        if rule.restriction:
            part += f" {RESTRICTION_TEXT.get(rule.restriction, rule.restriction)}"
        if rule.when:
            part += f" ({checks.describe(rule.when)})"
        parts.append(part)
    qualified = any(r.restriction or r.when for r in rules)
    return ("; " if qualified else ", ").join(parts)


def starting_out(db: DbSession, troupe_id: uuid.UUID) -> list[StartingCategoryOut]:
    rules = read_troupe_rules(db, "vampire", troupe_id)
    played = rules.creation_rules()
    found: list[StartingCategoryOut] = []
    for category in rules.rule_set.categories.values():
        book = [r for r in rules.rule_set.creation_rules if r.category == category.key]
        if not book:
            continue
        mine = [r for r in played if r.category == category.key]
        found.append(
            StartingCategoryOut(
                key=category.key,
                name=category.name,
                max_rating=category.max_rating,
                rules=[starting_rule(r) for r in mine],
                book=[starting_rule(r) for r in book],
                text=describe_starting(mine),
                book_text=describe_starting(book),
                house=any(r.house for r in mine),
            )
        )
    return found


def starting_category(db: DbSession, troupe_id: uuid.UUID, key: str) -> StartingCategoryOut:
    found = next((c for c in starting_out(db, troupe_id) if c.key == key), None)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No starting points for that category.")
    return found


@router.get("/creation")
def list_starting(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[StartingCategoryOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return starting_out(db, troupe_id)


@router.put("/creation/{category}")
def change_starting(
    troupe_id: uuid.UUID, category: str, body: StartingChange, db: DbSession, user: CurrentUser
) -> StartingCategoryOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    current = starting_category(db, troupe.id, category)
    if not body.rules:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Give at least one pick or a budget; go back to the rule set's to undo a change.",
        )
    conditions_allowed = [r.when for r in current.book if r.when]
    if any(r.when and r.when not in conditions_allowed for r in body.rules):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A starting rule can only have the condition of one of the rule set's.",
        )
    rules = [
        CreationRuleData(
            category=category,
            rating=r.rating,
            picks=r.picks,
            points=r.points,
            restriction=r.restriction or None,
            when=r.when or None,
            house=True,
        )
        for r in body.rules
    ]
    try:
        set_house_creation_rules(db, troupe.id, "vampire", category, rules)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    changed = starting_category(db, troupe.id, category)
    audit.record(
        db,
        user,
        "house.creation_set",
        troupe_id=troupe.id,
        category=changed.name,
        text=changed.text,
    )
    db.commit()
    return changed


@router.delete("/creation/{category}")
def reset_starting(
    troupe_id: uuid.UUID, category: str, db: DbSession, user: CurrentUser
) -> StartingCategoryOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    starting_category(db, troupe.id, category)
    set_house_creation_rules(db, troupe.id, "vampire", category, [])
    changed = starting_category(db, troupe.id, category)
    audit.record(
        db,
        user,
        "house.creation_reset",
        troupe_id=troupe.id,
        category=changed.name,
        text=changed.text,
    )
    db.commit()
    return changed


# --- Downtime actions ----------------------------------------------------------


class ActionKindOut(BaseModel):
    key: str
    name: str


class AllowanceOut(BaseModel):
    # Set for the troupe's own rules; None for the rule set's.
    id: uuid.UUID | None
    action_kind: str
    # None for the base allowance everyone gets.
    category: str | None
    trait: str | None
    min_rating: int
    scheme: Literal["fixed", "per_dot"]
    amount: int
    # Who gets it and how much, in plain words: "Hunted", "−2 downtime actions".
    who: str
    amount_text: str
    house: bool
    # A rule set rule this troupe has its own rule for.
    replaced: bool = False


class AllowancesOut(BaseModel):
    action_kinds: list[ActionKindOut]
    rules: list[AllowanceOut]


class AllowanceChange(BaseModel):
    scheme: Literal["fixed", "per_dot"] = "fixed"
    amount: int
    min_rating: int = Field(default=1, ge=1)


class AllowanceIn(AllowanceChange):
    action_kind: str
    category: str | None = None
    trait: str | None = None


def allowance_out(
    kinds: Mapping[str, ActionKindData],
    rule: AllowanceRuleData,
    rule_id: uuid.UUID | None,
    *,
    replaced: bool = False,
) -> AllowanceOut:
    kind = kinds[rule.action_kind].name if rule.action_kind in kinds else rule.action_kind
    plural = kind if abs(rule.amount) == 1 else f"{kind}s"
    sign = "−" if rule.amount < 0 else "+" if rule.trait else ""
    amount_text = f"{sign}{abs(rule.amount)} {plural[0].lower()}{plural[1:]}"
    if rule.scheme == "per_dot":
        amount_text += " per dot"
    who = rule.trait or "Everyone"
    if rule.trait and rule.min_rating > 1:
        who += f" at {rule.min_rating} or more"
    return AllowanceOut(
        id=rule_id,
        action_kind=rule.action_kind,
        category=rule.category,
        trait=rule.trait,
        min_rating=rule.min_rating,
        scheme=rule.scheme,
        amount=rule.amount,
        who=who,
        amount_text=amount_text,
        house=rule.house,
        replaced=replaced,
    )


def allowances_out(db: DbSession, troupe_id: uuid.UUID) -> AllowancesOut:
    rules = read_troupe_rules(db, "vampire", troupe_id)
    kinds = rules.action_kinds()
    house = house_allowance_rules(db, "vampire", troupe_id)
    house_keys = {r.key for _, r in house}
    order = {key: n for n, key in enumerate(kinds)}

    def by_kind(rule: AllowanceOut) -> tuple[int, bool, str, bool]:
        # A troupe rule right after the rule set rule it replaces.
        kind = order.get(rule.action_kind, len(order))
        return (kind, rule.trait is not None, rule.trait or "", rule.house)

    generic = [
        allowance_out(kinds, r, None, replaced=r.key in house_keys)
        for r in rules.rule_set.allowance_rules
    ]
    return AllowancesOut(
        action_kinds=[ActionKindOut(key=k.key, name=k.name) for k in kinds.values()],
        rules=sorted([*generic, *(allowance_out(kinds, r, i) for i, r in house)], key=by_kind),
    )


def house_allowance(db: DbSession, troupe_id: uuid.UUID, rule_id: uuid.UUID) -> AllowanceRuleData:
    found = dict(house_allowance_rules(db, "vampire", troupe_id)).get(rule_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such rule.")
    return found


def log_allowance(
    db: DbSession, user: User, action: str, troupe_id: uuid.UUID, rule: AllowanceRuleData
) -> None:
    kinds = read_troupe_rules(db, "vampire", troupe_id).action_kinds()
    shown = allowance_out(kinds, rule, None)
    audit.record(db, user, action, troupe_id=troupe_id, who=shown.who, amount=shown.amount_text)


@router.get("/allowances")
def list_allowances(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> AllowancesOut:
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return allowances_out(db, troupe_id)


@router.post("/allowances", status_code=status.HTTP_201_CREATED)
def add_allowance(
    troupe_id: uuid.UUID, body: AllowanceIn, db: DbSession, user: CurrentUser
) -> AllowanceOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    rule = AllowanceRuleData(
        action_kind=body.action_kind,
        scheme=body.scheme,
        amount=body.amount,
        category=body.category or None,
        trait=body.trait or None,
        min_rating=body.min_rating,
        house=True,
    )
    try:
        row = add_house_allowance_rule(db, troupe.id, "vampire", rule)
    except DuplicateHouseRule:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The troupe already has a rule for that; change it instead."
        ) from None
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    log_allowance(db, user, "house.allowance_added", troupe.id, rule)
    db.commit()
    return next(r for r in allowances_out(db, troupe.id).rules if r.id == row.id)


@router.put("/allowances/{rule_id}")
def change_allowance(
    troupe_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: AllowanceChange,
    db: DbSession,
    user: CurrentUser,
) -> AllowanceOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    old = house_allowance(db, troupe.id, rule_id)
    rule = replace(old, scheme=body.scheme, amount=body.amount, min_rating=body.min_rating)
    change_house_allowance_rule(db, troupe.id, rule_id, rule)
    log_allowance(db, user, "house.allowance_changed", troupe.id, rule)
    db.commit()
    return next(r for r in allowances_out(db, troupe.id).rules if r.id == rule_id)


@router.delete("/allowances/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_allowance(
    troupe_id: uuid.UUID, rule_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    old = house_allowance(db, troupe.id, rule_id)
    remove_house_allowance_rule(db, troupe.id, rule_id)
    log_allowance(db, user, "house.allowance_removed", troupe.id, old)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Starting blood ----------------------------------------------------------


class StartingBlood(BaseModel):
    # The blood characters start a game with, no more than their generation's
    # most; None starts them full.
    blood: int | None = Field(default=None, ge=0, le=30)


@router.put("/starting-blood")
def set_starting_blood(
    troupe_id: uuid.UUID, body: StartingBlood, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """What a reset for the next game puts each character's blood back to."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    troupe.starting_blood = body.blood
    audit.record(
        db,
        user,
        "house.starting_blood",
        troupe_id=troupe.id,
        blood="full" if body.blood is None else str(body.blood),
    )
    db.commit()
    return troupe_out(db, user, troupe)


# --- Diablerie ----------------------------------------------------------------


class DiablerieFlaws(BaseModel):
    # What recording a diablerie does to a Lesser Generation or Thin Blooded flaw the
    # character holds: leave it, remove it with the XP it gave, or remove it and keep
    # that XP (horatio.diablerie).
    setting: Literal["leave", "remove", "keep_xp"]


@router.put("/diablerie-flaws")
def set_diablerie_flaws(
    troupe_id: uuid.UUID, body: DiablerieFlaws, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """How this troupe handles a Lesser Generation or Thin Blooded flaw when a holder
    commits diablerie."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    troupe.diablerie_flaws = body.setting
    audit.record(
        db,
        user,
        "house.diablerie_flaws",
        troupe_id=troupe.id,
        setting=diablerie.SETTING_TEXT[body.setting],
    )
    db.commit()
    return troupe_out(db, user, troupe)
