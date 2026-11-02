"""A troupe's house rules: its settings for checks (switching one off, or changing
how strict it is), its own prices for traits, what new characters start with,
and how many downtime actions characters get; and all that differs from the book,
for its players to read."""

import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import audit, clan_merits, diablerie, feeding, rack, resonance, territories
from horatio.api.downtimes import staff_troupe
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.creation import RESTRICTION_TEXT
from horatio.models import Character, HouseTrait, Troupe, User
from horatio.permissions import TroupeAction
from horatio.rules import checks, conditions, pricing
from horatio.rules.checks import REQUIREMENT_KEY, CheckData
from horatio.rules.files import EVERYWHERE
from horatio.rules.house_checks import is_house_check
from horatio.rules.model import (
    ActionKindData,
    AllowanceRuleData,
    CostRuleData,
    CreationRuleData,
    RuleSetData,
    Scheme,
    house_label,
)
from horatio.rules.splats import SPLATS
from horatio.rules.store import (
    DuplicateHouseRule,
    add_house_allowance_rule,
    add_house_rule,
    change_house_allowance_rule,
    change_house_rule,
    forget_rules,
    house_allowance_rules,
    house_cost_rules,
    read_troupe_rules,
    remove_house_allowance_rule,
    remove_house_rule,
    same_subject,
    set_check_override,
    set_house_creation_rules,
)
from horatio.sheets import apply_grants, playing_by, sync_troupe_fixed_ratings

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["house rules"])

Strength = Literal["refuse", "complete", "review", "note", "off"]


class CheckOut(BaseModel):
    key: str
    # What it is about: a trait, a category, or names starting with a prefix.
    category: str
    # The kind of check it is, as Customise groups them: "Techniques", or "Clan
    # merits, only for their clan or bloodline" (CHECK_GROUPS).
    group: str
    about: str
    message: str
    page: str | None
    # As the rule set has it, and as this troupe plays it.
    strength: str
    house: str | None


class CheckChange(BaseModel):
    # None goes back to the rule set's strength.
    strength: Strength | None


# The groups of checks, in the order Customise shows them: those the rule set
# writes, by what they are about, then those that follow from the catalogue's
# requirements (horatio.rules.files.derived_checks), the most numerous.
CHECK_GROUPS = [
    "Clan",
    "Attributes and skills",
    "Focuses",
    "Specialisations",
    "Backgrounds",
    "Disciplines",
    "Techniques",
    "Rituals",
    "Morality",
    "Merits",
    "Flaws",
    "Clan merits, only for their clan or bloodline",
    "Clan flaws, only for their clan or bloodline",
    "Merits and flaws for one generation",
    "Other",
]
GROUP_OF_CATEGORY = {
    "clan": "Clan",
    "attributes": "Attributes and skills",
    "skills": "Attributes and skills",
    "backgrounds": "Backgrounds",
    "disciplines": "Disciplines",
    "extra_in_clan_disciplines": "Disciplines",
    "elder_disciplines": "Disciplines",
    "techniques": "Techniques",
    "rituals": "Rituals",
    "sabbat_rituals": "Rituals",
    "paths": "Morality",
    "merits": "Merits",
    "flaws": "Flaws",
}


def check_group(check: CheckData) -> str:
    """Which of CHECK_GROUPS a check is in."""
    if check.key.endswith(REQUIREMENT_KEY):
        if "generation" in (check.requires or {}):
            return "Merits and flaws for one generation"
        return f"Clan {check.category}, only for their clan or bloodline"
    if check.category.startswith("focus_"):
        return "Focuses"
    if check.category.endswith("_specializations"):
        return "Specialisations"
    return GROUP_OF_CATEGORY.get(check.category, "Other")


def checks_out(db: DbSession, troupe_id: uuid.UUID) -> list[CheckOut]:
    """The checks of every splat the troupe takes, each once: a vampire's, then those
    only a ghoul's rules have, in CHECK_GROUPS' order. A house strength is the
    troupe's for every splat."""
    troupe = db.get_one(Troupe, troupe_id)
    found: dict[str, CheckOut] = {}
    for splat in ["vampire", *(s for s in troupe.allowed_splats if s != "vampire")]:
        rules = read_troupe_rules(db, splat, troupe_id)
        for c in rules.rule_set.checks:
            # The troupe's own checks are listed apart (horatio.api.house_checks).
            if is_house_check(c.key):
                continue
            found.setdefault(
                c.key,
                CheckOut(
                    key=c.key,
                    category=c.category,
                    group=check_group(c),
                    about=c.name or (f"{c.name_prefix}…" if c.name_prefix else "any"),
                    message=c.message,
                    page=c.page,
                    strength=c.strength,
                    house=rules.check_overrides.get(c.key),
                ),
            )
    return sorted(found.values(), key=lambda c: CHECK_GROUPS.index(c.group))


@router.get("/checks")
def list_checks(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[CheckOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return checks_out(db, troupe_id)


@router.put("/checks/{key:path}")
def change_check(
    troupe_id: uuid.UUID, key: str, body: CheckChange, db: DbSession, user: CurrentUser
) -> CheckOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    known = {c.key for c in checks_out(db, troupe_id)}
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


def house_splat(db: DbSession, troupe_id: uuid.UUID, splat: str) -> str:
    """The splat a house rule is for: Vampire, or another the troupe takes. Prices,
    starting points and downtime actions are kept for each splat apart."""
    troupe = db.get_one(Troupe, troupe_id)
    if splat not in SPLATS or (splat != "vampire" and splat not in troupe.allowed_splats):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe has no rules for that splat.")
    return splat


def for_splat(text: str, splat: str) -> str:
    """What a house rule is about, as the troupe log says it: "Merits: Iron Will",
    or for another splat than Vampire, "Merits: Iron Will for ghouls"."""
    return text if splat == "vampire" else f"{text} for {SPLATS[splat].label.lower()}s"


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


def sync_values(db: DbSession, troupe_id: uuid.UUID, splat: str, rule: CostRuleData) -> None:
    """A troupe's fixed price for a fixed-rating merit or flaw is its value: hold
    the troupe's characters' copies at it."""
    rule_set = read_troupe_rules(db, splat, troupe_id).rule_set
    if rule.trait and rule_set.trait_properties(rule.category, rule.trait).get("rating"):
        sync_troupe_fixed_ratings(db, troupe_id)


def log_price(
    db: DbSession, user: User, action: str, troupe_id: uuid.UUID, splat: str, rule: CostRuleData
) -> None:
    """What the troupe log says about a price."""
    rule_set = read_troupe_rules(db, splat, troupe_id).rule_set
    what = rule.trait or rule_set.categories[rule.category].name
    when = conditions.describe(rule.condition, SPLATS[rule_set.splat].fact_words)
    audit.record(
        db,
        user,
        action,
        troupe_id=troupe_id,
        what=for_splat(f"{what} ({when})" if when else what, splat),
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


def house_cost(troupe_id: uuid.UUID, db: DbSession, splat: str, cost_id: uuid.UUID) -> CostRuleData:
    found = dict(house_cost_rules(db, splat, troupe_id)).get(cost_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such price.")
    return found


@router.get("/costs")
def list_costs(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, splat: str = "vampire"
) -> CostsOut:
    """The prices characters of `splat` pay in this troupe."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return costs_out(db, troupe_id, house_splat(db, troupe_id, splat))


@router.post("/costs", status_code=status.HTTP_201_CREATED)
def add_cost(
    troupe_id: uuid.UUID, body: CostIn, db: DbSession, user: CurrentUser, splat: str = "vampire"
) -> CostOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    splat = house_splat(db, troupe.id, splat)
    rule_set = read_troupe_rules(db, splat, troupe.id).rule_set
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
        row = add_house_rule(db, troupe.id, splat, rule)
    except DuplicateHouseRule:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The troupe already has a price for that; change it instead."
        ) from None
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    sync_values(db, troupe.id, splat, rule)
    log_price(db, user, "house.cost_added", troupe.id, splat, rule)
    db.commit()
    return next(c for c in costs_out(db, troupe.id, splat).costs if c.id == row.id)


@router.put("/costs/{cost_id}")
def change_cost(
    troupe_id: uuid.UUID,
    cost_id: uuid.UUID,
    body: CostChange,
    db: DbSession,
    user: CurrentUser,
    splat: str = "vampire",
) -> CostOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    splat = house_splat(db, troupe.id, splat)
    old = house_cost(troupe.id, db, splat, cost_id)
    rule = priced(body, old.category, old.trait, old.condition)
    try:
        change_house_rule(db, troupe.id, splat, cost_id, rule)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    sync_values(db, troupe.id, splat, rule)
    log_price(db, user, "house.cost_changed", troupe.id, splat, rule)
    db.commit()
    return next(c for c in costs_out(db, troupe.id, splat).costs if c.id == cost_id)


@router.delete("/costs/{cost_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_cost(
    troupe_id: uuid.UUID,
    cost_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    splat: str = "vampire",
) -> Response:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    splat = house_splat(db, troupe.id, splat)
    old = house_cost(troupe.id, db, splat, cost_id)
    remove_house_rule(db, troupe.id, cost_id)
    sync_values(db, troupe.id, splat, old)
    log_price(db, user, "house.cost_removed", troupe.id, splat, old)
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


def starting_out(
    db: DbSession, troupe_id: uuid.UUID, splat: str = "vampire"
) -> list[StartingCategoryOut]:
    rules = read_troupe_rules(db, splat, troupe_id)
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


def starting_category(
    db: DbSession, troupe_id: uuid.UUID, splat: str, key: str
) -> StartingCategoryOut:
    found = next((c for c in starting_out(db, troupe_id, splat) if c.key == key), None)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No starting points for that category.")
    return found


@router.get("/creation")
def list_starting(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, splat: str = "vampire"
) -> list[StartingCategoryOut]:
    """What new characters of `splat` start with in this troupe."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return starting_out(db, troupe_id, house_splat(db, troupe_id, splat))


@router.put("/creation/{category}")
def change_starting(
    troupe_id: uuid.UUID,
    category: str,
    body: StartingChange,
    db: DbSession,
    user: CurrentUser,
    splat: str = "vampire",
) -> StartingCategoryOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    splat = house_splat(db, troupe.id, splat)
    current = starting_category(db, troupe.id, splat, category)
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
        set_house_creation_rules(db, troupe.id, splat, category, rules)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    changed = starting_category(db, troupe.id, splat, category)
    audit.record(
        db,
        user,
        "house.creation_set",
        troupe_id=troupe.id,
        category=for_splat(changed.name, splat),
        text=changed.text,
    )
    db.commit()
    return changed


@router.delete("/creation/{category}")
def reset_starting(
    troupe_id: uuid.UUID,
    category: str,
    db: DbSession,
    user: CurrentUser,
    splat: str = "vampire",
) -> StartingCategoryOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    splat = house_splat(db, troupe.id, splat)
    starting_category(db, troupe.id, splat, category)
    set_house_creation_rules(db, troupe.id, splat, category, [])
    changed = starting_category(db, troupe.id, splat, category)
    audit.record(
        db,
        user,
        "house.creation_reset",
        troupe_id=troupe.id,
        category=for_splat(changed.name, splat),
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


def allowances_out(db: DbSession, troupe_id: uuid.UUID, splat: str = "vampire") -> AllowancesOut:
    rules = read_troupe_rules(db, splat, troupe_id)
    kinds = rules.action_kinds()
    house = house_allowance_rules(db, splat, troupe_id)
    house_keys = {r.key for _, r in house}
    order = {key: n for n, key in enumerate(kinds)}

    def by_kind(rule: AllowanceOut) -> tuple[int, bool, str, bool]:
        # A troupe rule right after the rule set rule it replaces.
        kind = order.get(rule.action_kind, len(order))
        return (kind, rule.trait is not None, rule.trait or "", rule.house)

    # The rule set's own: not those of house merits, which say theirs on the merit.
    generic = [
        allowance_out(kinds, r, None, replaced=r.key in house_keys)
        for r in (rules.unmerged or rules.rule_set).allowance_rules
    ]
    return AllowancesOut(
        action_kinds=[ActionKindOut(key=k.key, name=k.name) for k in kinds.values()],
        rules=sorted([*generic, *(allowance_out(kinds, r, i) for i, r in house)], key=by_kind),
    )


def house_allowance(
    db: DbSession, troupe_id: uuid.UUID, splat: str, rule_id: uuid.UUID
) -> AllowanceRuleData:
    found = dict(house_allowance_rules(db, splat, troupe_id)).get(rule_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such rule.")
    return found


def log_allowance(
    db: DbSession,
    user: User,
    action: str,
    troupe_id: uuid.UUID,
    splat: str,
    rule: AllowanceRuleData,
) -> None:
    kinds = read_troupe_rules(db, splat, troupe_id).action_kinds()
    shown = allowance_out(kinds, rule, None)
    audit.record(
        db,
        user,
        action,
        troupe_id=troupe_id,
        who=for_splat(shown.who, splat),
        amount=shown.amount_text,
    )


@router.get("/allowances")
def list_allowances(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, splat: str = "vampire"
) -> AllowancesOut:
    """The downtime actions characters of `splat` get in this troupe."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return allowances_out(db, troupe_id, house_splat(db, troupe_id, splat))


@router.post("/allowances", status_code=status.HTTP_201_CREATED)
def add_allowance(
    troupe_id: uuid.UUID,
    body: AllowanceIn,
    db: DbSession,
    user: CurrentUser,
    splat: str = "vampire",
) -> AllowanceOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    splat = house_splat(db, troupe.id, splat)
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
        row = add_house_allowance_rule(db, troupe.id, splat, rule)
    except DuplicateHouseRule:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The troupe already has a rule for that; change it instead."
        ) from None
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    log_allowance(db, user, "house.allowance_added", troupe.id, splat, rule)
    db.commit()
    return next(r for r in allowances_out(db, troupe.id, splat).rules if r.id == row.id)


@router.put("/allowances/{rule_id}")
def change_allowance(
    troupe_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: AllowanceChange,
    db: DbSession,
    user: CurrentUser,
    splat: str = "vampire",
) -> AllowanceOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    splat = house_splat(db, troupe.id, splat)
    old = house_allowance(db, troupe.id, splat, rule_id)
    rule = replace(old, scheme=body.scheme, amount=body.amount, min_rating=body.min_rating)
    change_house_allowance_rule(db, troupe.id, rule_id, rule)
    log_allowance(db, user, "house.allowance_changed", troupe.id, splat, rule)
    db.commit()
    return next(r for r in allowances_out(db, troupe.id, splat).rules if r.id == rule_id)


@router.delete("/allowances/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_allowance(
    troupe_id: uuid.UUID,
    rule_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    splat: str = "vampire",
) -> Response:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    splat = house_splat(db, troupe.id, splat)
    old = house_allowance(db, troupe.id, splat, rule_id)
    remove_house_allowance_rule(db, troupe.id, rule_id)
    log_allowance(db, user, "house.allowance_removed", troupe.id, splat, old)
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


class GolcondaIn(BaseModel):
    # The troupe's sect recognises the pursuit of Golconda: Golconda Seekers hold the
    # innate status Enlightened (Vol. 2, p. 267).
    on: bool


@router.put("/golconda")
def set_golconda(
    troupe_id: uuid.UUID, body: GolcondaIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """Switch on or off the optional rule that Golconda Seekers are Enlightened. The
    characters playing by the troupe's rules gain or lose it at once."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    if troupe.golconda_enlightened != body.on:
        troupe.golconda_enlightened = body.on
        audit.record(
            db,
            user,
            "house.golconda",
            troupe_id=troupe.id,
            setting="are Enlightened" if body.on else "are not Enlightened",
        )
        db.flush()
        forget_rules(db)
        for character in playing_by(db, troupe.id):
            apply_grants(db, user, character)
    db.commit()
    return troupe_out(db, user, troupe)


# --- Feeding ------------------------------------------------------------------------


class FeedingSettingIn(BaseModel):
    # "book", feeding tracked in downtimes as the core book has it, or "off", left out
    # of Horatio; what was recorded is kept either way (horatio.feeding).
    feeding: Literal["off", "book"]
    # The optional Vol. 2 rules, played while feeding is tracked and kept as set while
    # it is off: Blood Resonance (pp. 294-297), feeding territories (pp. 304-307), and
    # the Rack (pp. 298-303), which needs Blood Resonance.
    resonance: bool = False
    territories: bool = False
    rack: bool = False


@router.put("/feeding")
def set_feeding(
    troupe_id: uuid.UUID, body: FeedingSettingIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """How far Horatio handles feeding for this troupe: not at all, as the book has it,
    or with the optional Vol. 2 rules."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    feeding.set_setting(
        db,
        user,
        troupe,
        feeding.Setting(body.feeding, body.resonance, body.territories, body.rack),
    )
    db.commit()
    return troupe_out(db, user, troupe)


# --- Clan rarity ------------------------------------------------------------------

Rarity = Literal["common", "uncommon", "rare", "restricted"]


class ClanRarityRow(BaseModel):
    # A clan, without its bloodlines, which are as rare as it.
    clan: str
    # Its rarity in each sect's setting, as the book gives it.
    book: dict[str, str]
    # The troupe's own, or None to go by the book.
    house: str | None


class ClanRarityOut(BaseModel):
    # The sects the book gives clan rarities for.
    sects: list[str]
    # The sect whose rarities apply to everyone built here: the troupe's one sect, if it
    # takes characters of one sect only. Otherwise each character's own sect.
    setting: str | None
    clans: list[ClanRarityRow]


class ClanRarityIn(BaseModel):
    # Each clan the troupe rates itself; every other goes by the book.
    rarities: dict[str, Rarity]


def clan_rarity_out(db: DbSession, troupe: Troupe) -> ClanRarityOut:
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    clans = sorted(n for (c, n) in rule_set.traits if c == "clan" and ":" not in n)
    book = {c: dict(rule_set.trait_properties("clan", c).get("rarity", {})) for c in clans}
    sects = sorted({sect for found in book.values() for sect in found} - {EVERYWHERE})
    setting = troupe.allowed_sects[0] if len(troupe.allowed_sects) == 1 else None
    return ClanRarityOut(
        sects=sects,
        setting=setting,
        clans=[
            ClanRarityRow(
                clan=c,
                # An independent bloodline's own rarity holds in every setting.
                book={
                    sect: (book[c].get(EVERYWHERE) or book[c][sect])["rarity"]
                    for sect in sects
                    if EVERYWHERE in book[c] or sect in book[c]
                },
                house=troupe.clan_rarity.get(c),
            )
            for c in clans
        ],
    )


@router.get("/clan-rarity")
def read_clan_rarity(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ClanRarityOut:
    """How rare each clan is in the troupe's setting: the book's for each sect, and
    the troupe's own where it names one (horatio.clan_merits)."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return clan_rarity_out(db, troupe)


@router.put("/clan-rarity")
def set_clan_rarity(
    troupe_id: uuid.UUID, body: ClanRarityIn, db: DbSession, user: CurrentUser
) -> ClanRarityOut:
    """Name how rare clans are here. Characters being built here take the rarity merit
    it names straight away; finished characters keep theirs."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    unknown = [c for c in body.rarities if ("clan", c) not in rule_set.traits or ":" in c]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Not a clan: {', '.join(unknown)}. Name the clan; its bloodlines follow it.",
        )
    troupe.clan_rarity = dict(sorted(body.rarities.items()))
    db.flush()
    clan_merits.resync(
        db,
        db.scalars(
            select(Character).where(
                (Character.home_troupe_id == troupe.id)
                | (
                    Character.home_troupe_id.is_(None) & (Character.building_troupe_id == troupe.id)
                ),
                Character.creation_completed_at.is_(None),
            )
        ).all(),
    )
    audit.record(
        db,
        user,
        "house.clan_rarity",
        troupe_id=troupe.id,
        rarities=", ".join(f"{c} {r}" for c, r in troupe.clan_rarity.items()) or "the book's",
    )
    db.commit()
    return clan_rarity_out(db, troupe)


# --- What players read ------------------------------------------------------------


class HouseCostOut(BaseModel):
    # The category's name, and what the price is about: "All Skills, Generation
    # background 1", or one trait.
    category: str
    subject: str
    price_text: str
    # The rule set's price it replaces, under the same condition; None for a trait the
    # rule set prices only with its whole category.
    book_text: str | None
    # The house rule's own wording.
    text: str | None
    page: str | None


class HouseStartingOut(BaseModel):
    category: str
    text: str
    book_text: str


class HouseActionOut(BaseModel):
    who: str
    amount_text: str
    # The rule set's rule it replaces; None for one the rule set does not have.
    book_text: str | None


class SplatHouseRulesOut(BaseModel):
    """What differs from the book for characters of one splat."""

    splat: str
    label: str
    costs: list[HouseCostOut]
    starting: list[HouseStartingOut]
    actions: list[HouseActionOut]


class HouseCheckOut(BaseModel):
    rule: str
    page: str | None
    # As the rule set has it, and as this troupe plays it: refuse, complete, review,
    # note or off.
    strength: str
    house: str
    # The troupe's own check, not a book one played differently (horatio.house_checks).
    own: bool = False


class HouseMeritOut(BaseModel):
    splat: str
    category: str
    name: str
    points: int
    kind: str
    # "staff": given by staff only; "building": available when building for the troupe.
    availability: str
    creation_only: bool
    description: str
    requirement: str
    label: str
    # What its effects do on the sheet, in plain words.
    summary: str


class HouseSettingOut(BaseModel):
    """Another house rule, in plain words: what it is about, how the troupe plays it,
    and how the book does."""

    name: str
    text: str
    book_text: str


class HouseRulesOut(BaseModel):
    splats: list[SplatHouseRulesOut]
    checks: list[HouseCheckOut]
    house_traits: list[HouseMeritOut]
    other: list[HouseSettingOut]
    # How its backstories are written (free | either | wizard), and whether one must be
    # approved before a character is accepted here.
    backstory_mode: str
    backstory_required: bool


def splat_house_rules(db: DbSession, troupe_id: uuid.UUID, splat: str) -> SplatHouseRulesOut:
    """The troupe's own prices, starting points and downtime actions for `splat`, each
    beside the rule set's it replaces. Read from the rules already loaded."""
    rules = read_troupe_rules(db, splat, troupe_id)
    rule_set = rules.rule_set
    position = {key: n for n, key in enumerate(rule_set.categories)}
    costs: list[HouseCostOut] = []
    for rule in sorted(rules.house_rules, key=lambda r: (position[r.category], r.trait or "")):
        category = rule_set.categories[rule.category].name
        trait = rule_set.traits.get((rule.category, rule.trait)) if rule.trait else None
        when = conditions.describe(rule.condition, SPLATS[splat].fact_words)
        what = rule.trait or f"All {category}"
        book = next((r for r in rule_set.cost_rules if same_subject(rule, r)), None)
        costs.append(
            HouseCostOut(
                category=category,
                subject=f"{what}, {when}" if when else what,
                price_text=pricing.describe(rule, unit(rule_set, rule.category)),
                book_text=pricing.describe(book, unit(rule_set, book.category)) if book else None,
                text=rule.text,
                page=trait.page_reference if trait else None,
            )
        )
    kinds = rules.action_kinds()
    book_actions = {r.key: r for r in (rules.unmerged or rule_set).allowance_rules}
    actions: list[HouseActionOut] = []
    for rule in rules.house_allowance_rules:
        shown = allowance_out(kinds, rule, None)
        book = book_actions.get(rule.key)
        actions.append(
            HouseActionOut(
                who=shown.who,
                amount_text=shown.amount_text,
                book_text=allowance_out(kinds, book, None).amount_text if book else None,
            )
        )
    return SplatHouseRulesOut(
        splat=splat,
        label=SPLATS[splat].label,
        costs=costs,
        starting=[
            HouseStartingOut(category=c.name, text=c.text, book_text=c.book_text)
            for c in starting_out(db, troupe_id, splat)
            if c.house
        ],
        actions=actions,
    )


def other_settings(db: DbSession, troupe: Troupe) -> list[HouseSettingOut]:
    """The troupe's other house rules that differ from the book."""
    found: list[HouseSettingOut] = []
    if troupe.starting_blood is not None:
        found.append(
            HouseSettingOut(
                name="Blood at the start of a game",
                text=f"{troupe.starting_blood} Blood",
                book_text="Full",
            )
        )
    if troupe.diablerie_flaws != "leave":
        found.append(
            HouseSettingOut(
                name="Diablerie and the Lesser Generation or Thin Blooded flaw",
                text=f"Diablerie {diablerie.SETTING_TEXT[troupe.diablerie_flaws]}",
                book_text=f"Diablerie {diablerie.SETTING_TEXT['leave']}",
            )
        )
    if troupe.golconda_enlightened:
        found.append(
            HouseSettingOut(
                name="Golconda and Enlightened",
                text="Golconda Seekers hold the innate status Enlightened (Vol. 2, p. 267)",
                book_text="An optional rule, off unless the troupe's sect recognises Golconda",
            )
        )
    if not feeding.tracked(troupe):
        found.append(
            HouseSettingOut(
                name="Feeding",
                text=feeding.SETTING_TEXT["off"],
                book_text=feeding.SETTING_TEXT["book"],
            )
        )
    else:
        show = feeding.shown(troupe)
        optional = "An optional rule, off unless the troupe switches it on"
        if show.resonance:
            found.append(
                HouseSettingOut(
                    name="Blood Resonance",
                    text="Played: a character hunts for blood of one humor, and its feeding"
                    f" answer gives the Resonance and any Dyscrasia ({resonance.PAGES})",
                    book_text=optional,
                )
            )
        if show.territories:
            found.append(
                HouseSettingOut(
                    name="Feeding territories",
                    text="Played: areas only the vampires the domain's Authority names may feed"
                    f" in, which their holders patrol against poachers ({territories.PAGES})",
                    book_text=optional,
                )
            )
        if show.rack:
            found.append(
                HouseSettingOut(
                    name="Advanced feeding: the Rack",
                    text="Played: each character takes one vessel, a Feeding Card, from the"
                    f" cycle's Rack instead of spending feeding actions ({rack.PAGES})",
                    book_text=optional,
                )
            )
    if troupe.influence_lookback_days != 90:
        found.append(
            HouseSettingOut(
                name="How far influence lookups look back",
                text=f"{troupe.influence_lookback_days} days",
                book_text="The last 3 months",
            )
        )
    if troupe.clan_rarity:
        rarity = clan_rarity_out(db, troupe)
        for row in rarity.clans:
            if row.house is None:
                continue
            if rarity.setting and rarity.setting in row.book:
                book = row.book[rarity.setting].capitalize()
            else:
                book = ", ".join(f"{r} for the {sect}" for sect, r in row.book.items()).capitalize()
            found.append(
                HouseSettingOut(
                    name=f"How rare the {row.clan} are",
                    text=row.house.capitalize(),
                    book_text=book or "Not given",
                )
            )
    return found


def own_checks(db: DbSession, troupe: Troupe) -> list[HouseCheckOut]:
    """The troupe's own checks the rules can run, for its players: the message each
    gives, and how strictly it holds."""
    found: list[HouseCheckOut] = []
    for splat in ["vampire", *(s for s in troupe.allowed_splats if s != "vampire")]:
        for c in read_troupe_rules(db, splat, troupe.id).rule_set.checks:
            if is_house_check(c.key):
                found.append(
                    HouseCheckOut(
                        rule=c.message, page=None, strength=c.strength, house=c.strength, own=True
                    )
                )
    return found


@router.get("/house-rules")
def read_house_rules(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> HouseRulesOut:
    """What the troupe plays differently from the book, for its players to read before
    they build or buy: its own prices, starting points, checks, merits and flaws,
    downtime actions and other house rules, and how its backstories are written.
    Anyone signed in may read it, as anyone may build a character for the troupe and
    pay its prices; never its staff's notes, log or connectors."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or (troupe.archived_at is not None and not user.is_custodian):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    splats = ["vampire", *(s for s in troupe.allowed_splats if s != "vampire" and s in SPLATS)]
    house_traits = db.scalars(
        select(HouseTrait)
        .where(HouseTrait.troupe_id == troupe.id, HouseTrait.archived_at.is_(None))
        .order_by(HouseTrait.category.desc(), HouseTrait.name)
    ).all()
    merits: list[HouseMeritOut] = []
    for h in house_traits:
        read = read_troupe_rules(db, h.splat, troupe.id).house_trait(h.category, h.name)
        merits.append(
            HouseMeritOut(
                splat=h.splat,
                category=h.category,
                name=h.name,
                points=h.points,
                kind=h.kind,
                availability=h.availability,
                creation_only=h.creation_only,
                description=h.description,
                requirement=h.requirement,
                label=house_label(h.category, troupe.name),
                summary=read.summary if read is not None and h.effects else "",
            )
        )
    return HouseRulesOut(
        splats=[splat_house_rules(db, troupe.id, s) for s in splats],
        checks=[
            *own_checks(db, troupe),
            *(
                HouseCheckOut(
                    rule=c.message or c.about, page=c.page, strength=c.strength, house=c.house
                )
                for c in checks_out(db, troupe.id)
                if c.house
            ),
        ],
        house_traits=merits,
        other=other_settings(db, troupe),
        backstory_mode=troupe.backstory_mode,
        backstory_required=troupe.backstory_required,
    )
