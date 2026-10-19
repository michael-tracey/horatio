"""A troupe's house rules: its own prices for traits, and its settings for checks
(switching one off, or changing how strict it is)."""

import uuid
from collections.abc import Mapping
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from horatio import audit
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import User
from horatio.permissions import TroupeAction
from horatio.rules import conditions, pricing
from horatio.rules.model import CostRuleData, RuleSetData, Scheme
from horatio.rules.splats import SPLATS
from horatio.rules.store import (
    DuplicateHouseRule,
    add_house_rule,
    change_house_rule,
    house_cost_rules,
    read_troupe_rules,
    remove_house_rule,
    same_subject,
    set_check_override,
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
    # The rule set's prices, then the troupe's, by category.
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

    def order(cost: CostOut) -> tuple[int, bool, str]:
        return (position[cost.category], cost.trait is not None, cost.trait or "")

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
        costs=sorted(generic, key=order)
        + sorted((cost_out(rules.rule_set, r, i) for i, r in house), key=order),
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
