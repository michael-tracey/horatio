"""Rule sets in the database: loading the generic rules in, and reading troupe rules out."""

import uuid
from dataclasses import replace

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio.models import CostRule, RuleSet, TraitCategory, TraitDefinition
from horatio.rules.files import check_cost_rule
from horatio.rules.model import (
    CategoryData,
    CostRuleData,
    RuleSetData,
    TraitData,
    TroupeRules,
)


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
    return rule_set


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
    set when `troupe_id` is None (a character with no home troupe)."""
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

    data = RuleSetData(
        key=rule_set.key,
        splat=rule_set.splat,
        name=rule_set.name,
        version=rule_set.version,
        starting_xp=rule_set.starting_xp,
        categories={
            c.key: CategoryData(
                key=c.key,
                name=c.name,
                group=c.group_name,
                rated=c.rated,
                max_rating=c.max_rating,
                house_rules_per_trait=c.house_rules_per_trait,
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
        },
    )
    return TroupeRules(rule_set=data, house_rules=house)
