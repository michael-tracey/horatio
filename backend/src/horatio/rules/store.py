"""Rule sets in the database: loading the generic rules in, and reading troupe rules out."""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import wraps
from typing import Concatenate

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio.models import (
    ActionKind,
    AllowanceRule,
    CheckOverride,
    CostRule,
    CreationRule,
    RuleSet,
    StartingTrait,
    TraitCategory,
    TraitDefinition,
)
from horatio.rules.checks import check_from_dict, check_to_dict
from horatio.rules.files import check_allowance_rule, check_cost_rule, check_creation_rules
from horatio.rules.grants import grant_from_dict, grant_to_dict
from horatio.rules.model import (
    ActionKindData,
    AllowanceRuleData,
    CategoryData,
    CostRuleData,
    CreationRuleData,
    RuleSetData,
    StartingTraitData,
    TraitData,
    TroupeRules,
)

RULES_CACHE = "horatio.troupe_rules"


def forget_rules(session: Session) -> None:
    """Drop the rules cached on this session, after changing them."""
    session.info.pop(RULES_CACHE, None)


def changes_rules[**P, R](
    fn: Callable[Concatenate[Session, P], R],
) -> Callable[Concatenate[Session, P], R]:
    """Mark a function that writes rules: the session's cached rules are dropped
    once it is done, so the next read sees the change."""

    @wraps(fn)
    def wrapper(session: Session, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(session, *args, **kwargs)
        finally:
            forget_rules(session)

    return wrapper


@changes_rules
def sync_rule_set(session: Session, data: RuleSetData) -> RuleSet:
    """Make the database's generic rules match `data`.

    Categories and trait definitions are added or updated, never deleted:
    sheets and purchases refer to them. The generic cost rules are replaced
    wholesale. Troupes' house rules are left exactly as they are (ADR 0004).
    """
    rule_set = session.scalar(select(RuleSet).where(RuleSet.key == data.key))
    if rule_set is None:
        rule_set = RuleSet(key=data.key, splat=data.splat, name=data.name, version=data.version)
        session.add(rule_set)
    else:
        rule_set.splat, rule_set.name, rule_set.version = data.splat, data.name, data.version
    rule_set.starting_xp = data.starting_xp
    rule_set.banked_xp = data.banked_xp
    rule_set.titles = list(data.titles)
    rule_set.checks = [check_to_dict(c) for c in data.checks]
    rule_set.grants = [grant_to_dict(g) for g in data.grants]
    rule_set.creation_only = [dict(c) for c in data.creation_only]
    session.flush()

    categories = {
        c.key: c
        for c in session.scalars(
            select(TraitCategory).where(TraitCategory.rule_set_id == rule_set.id)
        )
    }
    for position, category in enumerate(data.categories.values()):
        row = categories.get(category.key)
        if row is None:
            row = TraitCategory(rule_set_id=rule_set.id, key=category.key)
            session.add(row)
            categories[category.key] = row
        row.name = category.name
        row.group_name = category.group
        row.position = position
        row.rated = category.rated
        row.max_rating = category.max_rating
        row.house_rules_per_trait = category.house_rules_per_trait
        row.requires = dict(category.requires) if category.requires else None
        row.change_cost = category.change_cost
        row.points_limit = category.points_limit
        row.usual_max = category.usual_max
        row.max_held = category.max_held
        row.derived = category.derived
        row.buy_off_factor = category.buy_off_factor
        row.downtime_actions = category.downtime_actions
        row.downtime_waived_by = [dict(w) for w in category.downtime_waived_by]
        row.specializes = dict(category.specializes) if category.specializes else None
    session.flush()

    definitions = {
        (category_key, d.name): d
        for d, category_key in session.execute(
            select(TraitDefinition, TraitCategory.key)
            .join(TraitCategory)
            .where(TraitCategory.rule_set_id == rule_set.id)
        )
    }
    for (category_key, name), trait in data.traits.items():
        row = definitions.get((category_key, name))
        if row is None:
            row = TraitDefinition(category_id=categories[category_key].id, name=name)
            session.add(row)
            definitions[(category_key, name)] = row
        row.description = trait.description
        row.page_reference = trait.page_reference
        row.properties = dict(trait.properties)
        row.retired = False
    for key, row in definitions.items():
        if key not in data.traits:
            row.retired = True
    session.flush()

    session.execute(
        delete(CostRule).where(CostRule.rule_set_id == rule_set.id, CostRule.troupe_id.is_(None))
    )
    for rule in data.cost_rules:
        session.add(
            CostRule(
                rule_set_id=rule_set.id,
                troupe_id=None,
                category_id=categories[rule.category].id,
                trait_definition_id=(
                    definitions[(rule.category, rule.trait)].id if rule.trait else None
                ),
                condition=dict(rule.condition) if rule.condition else None,
                scheme=rule.scheme,
                rate=rule.rate,
                cost_table=list(rule.table) if rule.table else None,
                text=rule.text,
            )
        )
    session.flush()

    session.execute(
        delete(ActionKind).where(
            ActionKind.rule_set_id == rule_set.id, ActionKind.troupe_id.is_(None)
        )
    )
    for kind in data.action_kinds.values():
        session.add(
            ActionKind(
                rule_set_id=rule_set.id,
                troupe_id=None,
                key=kind.key,
                name=kind.name,
                fields=[dict(f) for f in kind.fields],
            )
        )
    session.execute(
        delete(AllowanceRule).where(
            AllowanceRule.rule_set_id == rule_set.id, AllowanceRule.troupe_id.is_(None)
        )
    )
    for allowance_rule in data.allowance_rules:
        session.add(allowance_row(rule_set, None, allowance_rule, definitions_by_key=definitions))
    session.execute(
        delete(CreationRule).where(
            CreationRule.rule_set_id == rule_set.id, CreationRule.troupe_id.is_(None)
        )
    )
    for creation_rule in data.creation_rules:
        session.add(
            creation_row(rule_set.id, None, categories[creation_rule.category].id, creation_rule)
        )
    session.execute(
        delete(StartingTrait).where(
            StartingTrait.rule_set_id == rule_set.id, StartingTrait.troupe_id.is_(None)
        )
    )
    for starting in data.starting_traits:
        session.add(
            StartingTrait(
                rule_set_id=rule_set.id,
                troupe_id=None,
                trait_definition_id=definitions[(starting.category, starting.name)].id,
                rating=starting.rating,
            )
        )
    session.flush()
    return rule_set


def creation_row(
    rule_set_id: uuid.UUID,
    troupe_id: uuid.UUID | None,
    category_id: uuid.UUID,
    rule: CreationRuleData,
) -> CreationRule:
    return CreationRule(
        rule_set_id=rule_set_id,
        troupe_id=troupe_id,
        category_id=category_id,
        rating=rule.rating,
        picks=rule.picks,
        points=rule.points,
        restriction=rule.restriction,
        when=dict(rule.when) if rule.when else None,
    )


@changes_rules
def set_house_creation_rules(
    session: Session,
    troupe_id: uuid.UUID,
    splat: str,
    category: str,
    rules: list[CreationRuleData],
) -> None:
    """Replace a troupe's creation rules for one category. An empty list goes back
    to the generic rules for it."""
    if any(r.category != category for r in rules):
        raise ValueError("every rule must be for the category being set")
    check_creation_rules(rules, read_troupe_rules(session, splat, troupe_id).rule_set)
    rule_set = session.scalars(select(RuleSet).where(RuleSet.splat == splat)).one()
    category_id = session.scalars(
        select(TraitCategory.id).where(
            TraitCategory.rule_set_id == rule_set.id, TraitCategory.key == category
        )
    ).one()
    session.execute(
        delete(CreationRule).where(
            CreationRule.rule_set_id == rule_set.id,
            CreationRule.troupe_id == troupe_id,
            CreationRule.category_id == category_id,
        )
    )
    for rule in rules:
        session.add(creation_row(rule_set.id, troupe_id, category_id, rule))
    session.flush()


def allowance_row(
    rule_set: RuleSet,
    troupe_id: uuid.UUID | None,
    rule: AllowanceRuleData,
    *,
    definitions_by_key: Mapping[tuple[str, str], TraitDefinition],
) -> AllowanceRule:
    definition_id = None
    if rule.category is not None and rule.trait is not None:
        definition_id = definitions_by_key[(rule.category, rule.trait)].id
    return AllowanceRule(
        rule_set_id=rule_set.id,
        troupe_id=troupe_id,
        action_kind=rule.action_kind,
        trait_definition_id=definition_id,
        min_rating=rule.min_rating,
        scheme=rule.scheme,
        amount=rule.amount,
    )


@changes_rules
def add_house_allowance_rule(
    session: Session, troupe_id: uuid.UUID, splat: str, rule: AllowanceRuleData
) -> AllowanceRule:
    """Add a troupe's allowance rule. One with the same action kind and trait as a
    generic rule replaces it for that troupe."""
    rules = read_troupe_rules(session, splat, troupe_id)
    check_allowance_rule(
        rule, rules.rule_set, extra_kinds=[k.key for k in rules.house_action_kinds]
    )
    rule_set = session.scalars(select(RuleSet).where(RuleSet.splat == splat)).one()
    definitions = {
        (key, d.name): d
        for d, key in session.execute(
            select(TraitDefinition, TraitCategory.key)
            .join(TraitCategory)
            .where(TraitCategory.rule_set_id == rule_set.id)
        )
    }
    row = allowance_row(rule_set, troupe_id, rule, definitions_by_key=definitions)
    session.add(row)
    session.flush()
    return row


@changes_rules
def add_house_action_kind(
    session: Session, troupe_id: uuid.UUID, splat: str, kind: ActionKindData
) -> ActionKind:
    rule_set = session.scalars(select(RuleSet).where(RuleSet.splat == splat)).one()
    row = ActionKind(
        rule_set_id=rule_set.id,
        troupe_id=troupe_id,
        key=kind.key,
        name=kind.name,
        fields=[dict(f) for f in kind.fields],
    )
    session.add(row)
    session.flush()
    return row


@changes_rules
def set_check_override(
    session: Session, troupe_id: uuid.UUID, check_key: str, strength: str | None
) -> None:
    """Give a check a house strength in a troupe, or (None) go back to the rule set's."""
    row = session.scalar(
        select(CheckOverride).where(
            CheckOverride.troupe_id == troupe_id, CheckOverride.check_key == check_key
        )
    )
    if strength is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(CheckOverride(troupe_id=troupe_id, check_key=check_key, strength=strength))
    else:
        row.strength = strength
    session.flush()


@changes_rules
def add_house_rule(
    session: Session, troupe_id: uuid.UUID, splat: str, rule: CostRuleData
) -> CostRule:
    """Add one house rule, after checking the pricing code could apply it."""
    rules = read_troupe_rules(session, splat, None)
    house = replace(rule, house=True)
    check_cost_rule(house, rules.rule_set)

    rule_set = session.scalars(select(RuleSet).where(RuleSet.splat == splat)).one()
    category = session.scalars(
        select(TraitCategory).where(
            TraitCategory.rule_set_id == rule_set.id, TraitCategory.key == rule.category
        )
    ).one()
    definition_id = None
    if rule.trait is not None:
        definition_id = session.scalars(
            select(TraitDefinition.id).where(
                TraitDefinition.category_id == category.id, TraitDefinition.name == rule.trait
            )
        ).one()
    row = CostRule(
        rule_set_id=rule_set.id,
        troupe_id=troupe_id,
        category_id=category.id,
        trait_definition_id=definition_id,
        condition=dict(rule.condition) if rule.condition else None,
        scheme=rule.scheme,
        rate=rule.rate,
        cost_table=list(rule.table) if rule.table else None,
        text=rule.text,
    )
    session.add(row)
    session.flush()
    return row


def read_troupe_rules(session: Session, splat: str, troupe_id: uuid.UUID | None) -> TroupeRules:
    """The rules a character of `splat` plays by in `troupe_id`, or the plain rule
    set when `troupe_id` is None (a character with no home troupe). Read once per
    session: rules change only through this module, which forgets them."""
    cache: dict[tuple[str, uuid.UUID | None], TroupeRules] = session.info.setdefault(
        RULES_CACHE, {}
    )
    if (splat, troupe_id) not in cache:
        cache[(splat, troupe_id)] = load_troupe_rules(session, splat, troupe_id)
    return cache[(splat, troupe_id)]


def load_troupe_rules(session: Session, splat: str, troupe_id: uuid.UUID | None) -> TroupeRules:
    rule_set = session.scalars(select(RuleSet).where(RuleSet.splat == splat)).one()
    categories = list(
        session.scalars(
            select(TraitCategory)
            .where(TraitCategory.rule_set_id == rule_set.id)
            .order_by(TraitCategory.position)
        )
    )
    category_keys = {c.id: c.key for c in categories}
    definitions = list(
        session.scalars(
            select(TraitDefinition).where(TraitDefinition.category_id.in_(category_keys))
        )
    )
    definition_names = {d.id: d.name for d in definitions}

    def to_data(row: CostRule) -> CostRuleData:
        return CostRuleData(
            category=category_keys[row.category_id],
            scheme=row.scheme,  # type: ignore[arg-type]  # checked by the database
            trait=definition_names[row.trait_definition_id] if row.trait_definition_id else None,
            condition=row.condition,
            rate=row.rate,
            table=tuple(row.cost_table) if row.cost_table else None,
            text=row.text,
            house=row.troupe_id is not None,
        )

    query = select(CostRule).where(CostRule.rule_set_id == rule_set.id).order_by(CostRule.id)
    generic = [to_data(r) for r in session.scalars(query.where(CostRule.troupe_id.is_(None)))]
    house: list[CostRuleData] = []
    if troupe_id is not None:
        house = [to_data(r) for r in session.scalars(query.where(CostRule.troupe_id == troupe_id))]

    kind_rows = list(
        session.scalars(
            select(ActionKind)
            .where(ActionKind.rule_set_id == rule_set.id)
            .where(ActionKind.troupe_id.is_(None) | (ActionKind.troupe_id == troupe_id))
            .order_by(ActionKind.id)
        )
    )

    def kind_data(row: ActionKind) -> ActionKindData:
        return ActionKindData(
            key=row.key, name=row.name, fields=tuple(row.fields), house=row.troupe_id is not None
        )

    allowance_rows = list(
        session.scalars(
            select(AllowanceRule)
            .where(AllowanceRule.rule_set_id == rule_set.id)
            .where(AllowanceRule.troupe_id.is_(None) | (AllowanceRule.troupe_id == troupe_id))
            .order_by(AllowanceRule.id)
        )
    )
    definition_keys = {d.id: (category_keys[d.category_id], d.name) for d in definitions}

    def allowance_data(row: AllowanceRule) -> AllowanceRuleData:
        category, trait = (
            definition_keys[row.trait_definition_id] if row.trait_definition_id else (None, None)
        )
        return AllowanceRuleData(
            action_kind=row.action_kind,
            scheme=row.scheme,  # type: ignore[arg-type]  # checked by the database
            amount=row.amount,
            category=category,
            trait=trait,
            min_rating=row.min_rating,
            house=row.troupe_id is not None,
        )

    creation_rows = list(
        session.scalars(
            select(CreationRule)
            .where(CreationRule.rule_set_id == rule_set.id)
            .where(CreationRule.troupe_id.is_(None) | (CreationRule.troupe_id == troupe_id))
            .order_by(CreationRule.id)
        )
    )

    def creation_data(row: CreationRule) -> CreationRuleData:
        return CreationRuleData(
            category=category_keys[row.category_id],
            rating=row.rating,
            picks=row.picks,
            points=row.points,
            restriction=row.restriction,
            house=row.troupe_id is not None,
            when=row.when,
        )

    starting_rows = list(
        session.scalars(
            select(StartingTrait)
            .where(StartingTrait.rule_set_id == rule_set.id)
            .where(StartingTrait.troupe_id.is_(None) | (StartingTrait.troupe_id == troupe_id))
            .order_by(StartingTrait.id)
        )
    )

    def starting_data(row: StartingTrait) -> StartingTraitData:
        category, name = definition_keys[row.trait_definition_id]
        return StartingTraitData(
            category=category, name=name, rating=row.rating, house=row.troupe_id is not None
        )

    data = RuleSetData(
        key=rule_set.key,
        splat=rule_set.splat,
        name=rule_set.name,
        version=rule_set.version,
        starting_xp=rule_set.starting_xp,
        titles=tuple(rule_set.titles),
        checks=tuple(check_from_dict(c) for c in rule_set.checks),
        grants=tuple(grant_from_dict(g) for g in rule_set.grants),
        creation_only=tuple(rule_set.creation_only),
        banked_xp=rule_set.banked_xp,
        categories={
            c.key: CategoryData(
                key=c.key,
                name=c.name,
                group=c.group_name,
                rated=c.rated,
                max_rating=c.max_rating,
                house_rules_per_trait=c.house_rules_per_trait,
                requires=c.requires,
                change_cost=c.change_cost,
                points_limit=c.points_limit,
                usual_max=c.usual_max,
                max_held=c.max_held,
                derived=c.derived,
                buy_off_factor=c.buy_off_factor,
                downtime_actions=c.downtime_actions,
                downtime_waived_by=tuple(c.downtime_waived_by),
                specializes=c.specializes,
            )
            for c in categories
        },
        cost_rules=generic,
        traits={
            (category_keys[d.category_id], d.name): TraitData(
                category=category_keys[d.category_id],
                name=d.name,
                description=d.description,
                page_reference=d.page_reference,
                properties=d.properties,
            )
            for d in definitions
            if not d.retired
        },
        action_kinds={r.key: kind_data(r) for r in kind_rows if r.troupe_id is None},
        allowance_rules=[allowance_data(r) for r in allowance_rows if r.troupe_id is None],
        creation_rules=[creation_data(r) for r in creation_rows if r.troupe_id is None],
        starting_traits=[starting_data(r) for r in starting_rows if r.troupe_id is None],
    )
    return TroupeRules(
        rule_set=data,
        house_rules=house,
        house_action_kinds=[kind_data(r) for r in kind_rows if r.troupe_id is not None],
        house_allowance_rules=[
            allowance_data(r) for r in allowance_rows if r.troupe_id is not None
        ],
        house_creation_rules=[creation_data(r) for r in creation_rows if r.troupe_id is not None],
        house_starting_traits=[starting_data(r) for r in starting_rows if r.troupe_id is not None],
        check_overrides={
            o.check_key: o.strength
            for o in session.scalars(
                select(CheckOverride).where(CheckOverride.troupe_id == troupe_id)
            )
        }
        if troupe_id is not None
        else {},
    )
