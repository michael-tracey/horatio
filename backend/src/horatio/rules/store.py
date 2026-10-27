"""Rule sets in the database: loading the generic rules in, and reading troupe rules out."""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import wraps
from typing import Any, Concatenate

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio.models import (
    ActionKind,
    AllowanceRule,
    CheckOverride,
    CostRule,
    CreationRule,
    EquipmentQuality,
    EquipmentTemplate,
    HouseTrait,
    RuleSet,
    StartingTrait,
    TraitCategory,
    TraitDefinition,
    Troupe,
)
from horatio.rules.checks import check_from_dict, check_to_dict
from horatio.rules.equipment import (
    EquipmentRules,
    GradeData,
    KindData,
    TemplateData,
    equipment_to_dict,
    item_qualities,
    item_qualities_to_list,
    quality_from_dict,
)
from horatio.rules.files import (
    check_allowance_rule,
    check_cost_rule,
    check_creation_rules,
    feeding_modifier_from_dict,
    feeding_modifier_to_dict,
)
from horatio.rules.grants import grant_from_dict, grant_to_dict
from horatio.rules.house_effects import merged
from horatio.rules.model import (
    ActionKindData,
    AllowanceRuleData,
    CategoryData,
    CostRuleData,
    CreationRuleData,
    HouseTraitData,
    RuleSetData,
    StartingTraitData,
    TraitData,
    TroupeRules,
    house_page,
)
from horatio.rules.status import status_rules_from_dict, status_rules_to_dict, titles_from

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
    rule_set.titles = [t.name for t in data.titles]
    rule_set.status_rules = status_rules_to_dict(data.status_rules, data.titles)
    rule_set.checks = [check_to_dict(c) for c in data.checks]
    rule_set.grants = [grant_to_dict(g) for g in data.grants]
    rule_set.feeding_modifiers = [feeding_modifier_to_dict(m) for m in data.feeding_modifiers]
    rule_set.creation_only = [dict(c) for c in data.creation_only]
    rule_set.equipment = equipment_to_dict(data.equipment)
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
            .where(TraitCategory.rule_set_id == rule_set.id, TraitDefinition.troupe_id.is_(None))
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
                actions=[dict(a) for a in kind.actions],
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
    sync_equipment(session, rule_set, data.equipment)
    return rule_set


def sync_equipment(session: Session, rule_set: RuleSet, data: EquipmentRules) -> None:
    """Equipment qualities are added or updated, and retired rather than deleted,
    as trait definitions are: items will refer to them. The book's templates are
    replaced; a troupe's own are left alone."""
    rows = {
        (q.kind, q.name): q
        for q in session.scalars(
            select(EquipmentQuality).where(EquipmentQuality.rule_set_id == rule_set.id)
        )
    }
    for position, ((kind, name), quality) in enumerate(data.qualities.items()):
        row = rows.get((kind, name))
        if row is None:
            row = EquipmentQuality(rule_set_id=rule_set.id, kind=kind, name=name)
            session.add(row)
        row.effect = quality.effect
        row.page = quality.page
        row.properties = quality.properties
        row.position = position
        row.retired = False
    for key, row in rows.items():
        if key not in data.qualities:
            row.retired = True
    session.execute(
        delete(EquipmentTemplate).where(
            EquipmentTemplate.rule_set_id == rule_set.id, EquipmentTemplate.troupe_id.is_(None)
        )
    )
    for position, template in enumerate(data.templates):
        session.add(
            EquipmentTemplate(
                rule_set_id=rule_set.id,
                troupe_id=None,
                name=template.name,
                kind=template.kind,
                grade=template.grade,
                qualities=item_qualities_to_list(template.qualities),
                page=template.page,
                position=position,
            )
        )
    session.flush()


def load_equipment(session: Session, rule_set: RuleSet) -> EquipmentRules:
    """The rule set's equipment rules, as `sync_equipment` wrote them."""
    qualities = session.scalars(
        select(EquipmentQuality)
        .where(EquipmentQuality.rule_set_id == rule_set.id, EquipmentQuality.retired.is_(False))
        .order_by(EquipmentQuality.position)
    )
    templates = session.scalars(
        select(EquipmentTemplate)
        .where(EquipmentTemplate.rule_set_id == rule_set.id, EquipmentTemplate.troupe_id.is_(None))
        .order_by(EquipmentTemplate.position)
    )
    return EquipmentRules(
        kinds={k["key"]: KindData(**k) for k in rule_set.equipment.get("kinds", [])},
        grades={g["key"]: GradeData(**g) for g in rule_set.equipment.get("grades", [])},
        qualities={
            (q.kind, q.name): replace(
                quality_from_dict(q.kind, q.name, q.properties), effect=q.effect, page=q.page
            )
            for q in qualities
        },
        templates=tuple(
            TemplateData(
                name=t.name,
                kind=t.kind,
                grade=t.grade,
                qualities=item_qualities(t.qualities),
                page=t.page,
            )
            for t in templates
        ),
    )


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
    if any(r.key == rule.key for r in rules.house_allowance_rules):
        raise DuplicateHouseRule("the troupe already has a rule for that")
    rule_set = session.scalars(select(RuleSet).where(RuleSet.splat == splat)).one()
    definitions = {
        (key, d.name): d
        for d, key in session.execute(
            select(TraitDefinition, TraitCategory.key)
            .join(TraitCategory)
            .where(
                TraitCategory.rule_set_id == rule_set.id,
                TraitDefinition.troupe_id.is_(None) | (TraitDefinition.troupe_id == troupe_id),
            )
        )
    }
    row = allowance_row(rule_set, troupe_id, rule, definitions_by_key=definitions)
    session.add(row)
    session.flush()
    return row


def house_allowance_rules(
    session: Session, splat: str, troupe_id: uuid.UUID
) -> list[tuple[uuid.UUID, AllowanceRuleData]]:
    """A troupe's own allowance rules, each with its id, oldest first."""
    rules = read_troupe_rules(session, splat, troupe_id)
    ids = session.scalars(
        select(AllowanceRule.id)
        .join(RuleSet, AllowanceRule.rule_set_id == RuleSet.id)
        .where(RuleSet.splat == splat, AllowanceRule.troupe_id == troupe_id)
        .order_by(AllowanceRule.id)
    ).all()
    # read_troupe_rules reads them in the same order.
    return list(zip(ids, rules.house_allowance_rules, strict=True))


@changes_rules
def change_house_allowance_rule(
    session: Session, troupe_id: uuid.UUID, rule_id: uuid.UUID, rule: AllowanceRuleData
) -> None:
    """Change how much a troupe's allowance rule gives; what it is about stays."""
    row = session.get(AllowanceRule, rule_id)
    if row is None or row.troupe_id != troupe_id:
        raise LookupError("no such house rule")
    if rule.scheme not in ("fixed", "per_dot"):
        raise ValueError(f"unknown scheme {rule.scheme!r}")
    row.scheme = rule.scheme
    row.amount = rule.amount
    row.min_rating = rule.min_rating
    session.flush()


@changes_rules
def remove_house_allowance_rule(session: Session, troupe_id: uuid.UUID, rule_id: uuid.UUID) -> None:
    row = session.get(AllowanceRule, rule_id)
    if row is None or row.troupe_id != troupe_id:
        raise LookupError("no such house rule")
    session.delete(row)
    session.flush()


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
        actions=[dict(a) for a in kind.actions],
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
    """Add one house rule, after checking the pricing code could apply it. A
    troupe has at most one price for each trait (or category) and condition."""
    rules = read_troupe_rules(session, splat, troupe_id)
    house = replace(rule, house=True)
    check_cost_rule(house, rules.rule_set)
    if any(same_subject(r, house) for r in rules.house_rules):
        raise DuplicateHouseRule("the troupe already has a price for that")

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
                TraitDefinition.category_id == category.id,
                TraitDefinition.name == rule.trait,
                TraitDefinition.troupe_id.is_(None) | (TraitDefinition.troupe_id == troupe_id),
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


class DuplicateHouseRule(ValueError):
    pass


def same_subject(a: CostRuleData, b: CostRuleData) -> bool:
    """Whether two cost rules price the same thing under the same condition, so
    that a house rule would replace the other."""
    return (a.category, a.trait, dict(a.condition or {})) == (
        b.category,
        b.trait,
        dict(b.condition or {}),
    )


def house_cost_rules(
    session: Session, splat: str, troupe_id: uuid.UUID
) -> list[tuple[uuid.UUID, CostRuleData]]:
    """A troupe's own cost rules, each with its id, oldest first."""
    rules = read_troupe_rules(session, splat, troupe_id)
    ids = session.scalars(
        select(CostRule.id)
        .join(RuleSet, CostRule.rule_set_id == RuleSet.id)
        .where(RuleSet.splat == splat, CostRule.troupe_id == troupe_id)
        .order_by(CostRule.id)
    ).all()
    # read_troupe_rules reads them in the same order.
    return list(zip(ids, rules.house_rules, strict=True))


@changes_rules
def change_house_rule(
    session: Session, troupe_id: uuid.UUID, splat: str, rule_id: uuid.UUID, rule: CostRuleData
) -> CostRule:
    """Change how a troupe's cost rule prices its trait or category; what it
    prices, and when, stay as they are."""
    row = session.get(CostRule, rule_id)
    if row is None or row.troupe_id != troupe_id:
        raise LookupError("no such house rule")
    rules = read_troupe_rules(session, splat, troupe_id)
    check_cost_rule(replace(rule, house=True), rules.rule_set)
    row.scheme = rule.scheme
    row.rate = rule.rate
    row.cost_table = list(rule.table) if rule.table else None
    row.text = rule.text
    session.flush()
    return row


@changes_rules
def remove_house_rule(session: Session, troupe_id: uuid.UUID, rule_id: uuid.UUID) -> None:
    row = session.get(CostRule, rule_id)
    if row is None or row.troupe_id != troupe_id:
        raise LookupError("no such house rule")
    session.delete(row)
    session.flush()


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
    # The rule set's traits, and this troupe's own merits and flaws.
    definitions = list(
        session.scalars(
            select(TraitDefinition)
            .where(TraitDefinition.category_id.in_(category_keys))
            .where(TraitDefinition.troupe_id.is_(None) | (TraitDefinition.troupe_id == troupe_id))
            .order_by(TraitDefinition.troupe_id.nulls_first())
        )
    )
    definition_names = {d.id: d.name for d in definitions}
    house = house_traits_of(session, splat, troupe_id)
    house_by_definition = {h.trait_definition_id: h for h, _ in house}

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
    house_costs: list[CostRuleData] = []
    if troupe_id is not None:
        house_costs = [
            to_data(r) for r in session.scalars(query.where(CostRule.troupe_id == troupe_id))
        ]

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
            key=row.key,
            name=row.name,
            fields=tuple(row.fields),
            actions=tuple(row.actions),
            house=row.troupe_id is not None,
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

    troupe_name = house[0][1] if house else ""
    traits: dict[tuple[str, str], TraitData] = {}
    taken: set[uuid.UUID] = set()
    for d in definitions:
        key = (category_keys[d.category_id], d.name)
        # The book's own come first: one the book gained after a troupe used its
        # name keeps the name, and the house one is left out.
        if d.retired or key in traits:
            continue
        own = house_by_definition.get(d.id)
        traits[key] = (
            TraitData(
                category=key[0],
                name=d.name,
                description=d.description,
                page_reference=d.page_reference,
                properties=d.properties,
            )
            if own is None
            else TraitData(
                category=key[0],
                name=own.name,
                description=own.description or None,
                page_reference=house_page(troupe_name),
                properties=house_properties(own),
            )
        )
        taken.add(d.id)
    house_data = [house_trait_data(h, name) for h, name in house if h.trait_definition_id in taken]
    creation_only = tuple(rule_set.creation_only) + tuple(
        {"category": h.category, "name": h.name} for h in house_data if h.creation_only
    )

    data = RuleSetData(
        key=rule_set.key,
        splat=rule_set.splat,
        name=rule_set.name,
        version=rule_set.version,
        starting_xp=rule_set.starting_xp,
        titles=titles_from([*rule_set.titles, *rule_set.status_rules.get("titles", [])]),
        status_rules=status_rules_from_dict(rule_set.status_rules),
        checks=tuple(check_from_dict(c) for c in rule_set.checks),
        grants=tuple(grant_from_dict(g) for g in rule_set.grants),
        feeding_modifiers=tuple(feeding_modifier_from_dict(m) for m in rule_set.feeding_modifiers),
        creation_only=creation_only,
        banked_xp=rule_set.banked_xp,
        equipment=load_equipment(session, rule_set),
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
        traits=traits,
        action_kinds={r.key: kind_data(r) for r in kind_rows if r.troupe_id is None},
        allowance_rules=[allowance_data(r) for r in allowance_rows if r.troupe_id is None],
        creation_rules=[creation_data(r) for r in creation_rows if r.troupe_id is None],
        starting_traits=[starting_data(r) for r in starting_rows if r.troupe_id is None],
    )
    # The house traits' effects, as grants, checks, play properties, allowance rules
    # and feeding modifiers beside the book's.
    unmerged = data
    house_kinds = [kind_data(r) for r in kind_rows if r.troupe_id is not None]
    kinds = {**data.action_kinds, **{k.key: k for k in house_kinds}}
    data, house_data = merged(data, house_data, kinds)
    return TroupeRules(
        rule_set=data,
        house_rules=house_costs,
        house_action_kinds=house_kinds,
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
        house_traits=house_data,
        unmerged=unmerged if data is not unmerged else None,
    )


def house_traits_of(
    session: Session, splat: str, troupe_id: uuid.UUID | None
) -> list[tuple[HouseTrait, str]]:
    """A troupe's own merits and flaws for a splat, each with the troupe's name."""
    if troupe_id is None:
        return []
    return [
        (h, name)
        for h, name in session.execute(
            select(HouseTrait, Troupe.name)
            .join(Troupe, HouseTrait.troupe_id == Troupe.id)
            .where(HouseTrait.troupe_id == troupe_id, HouseTrait.splat == splat)
            .order_by(HouseTrait.category, HouseTrait.name)
        )
    ]


def house_properties(row: HouseTrait) -> dict[str, Any]:
    """What the rules read of a house merit or flaw, as they would a book one's:
    its rating (its points), its type and requirement. `offered` False keeps it
    out of what a player can pick (horatio.house_traits)."""
    found: dict[str, Any] = {
        "rating": row.points,
        "type": row.kind,
        "house": True,
        "offered": row.availability == "building" and row.archived_at is None,
    }
    if row.requirement:
        found["requirement"] = row.requirement
    return found


def house_trait_data(row: HouseTrait, troupe_name: str) -> HouseTraitData:
    return HouseTraitData(
        id=row.id,
        troupe_id=row.troupe_id,
        troupe_name=troupe_name,
        category=row.category,
        name=row.name,
        points=row.points,
        kind=row.kind,
        availability=row.availability,  # type: ignore[arg-type]  # checked by the database
        creation_only=row.creation_only,
        archived=row.archived_at is not None,
        description=row.description,
        requirement=row.requirement,
        effects=tuple(row.effects),
    )
