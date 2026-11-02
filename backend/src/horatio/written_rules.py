"""A troupe's written house rules (issue #434): rules in words alone, which its
players read and nothing is built from, such as how Crafts difficulties work there,
what holding a location allows, or its FAQ.

Each has a title, a body in Markdown, an optional section to read it under, and an
optional link to the book trait or page it is about. They are read by section, the
sections in alphabetical order after the rules with none, and within a section in the
order staff put them. Players read them on the troupe's House rules tab, in the rules
browser, and on a trait's details where one is linked to it; and on the troupe's
profile when staff choose (Troupe.written_rules_public).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio.models import RuleSet, TraitCategory, TraitDefinition, WrittenRule


@dataclass(frozen=True)
class LinkedTrait:
    """The trait a written rule is about."""

    splat: str
    category: str
    name: str


def section_order(section: str) -> tuple[bool, str]:
    """Where a section is read: the rules with none first, then by name."""
    return (section != "", section.casefold())


def listed(db: Session, troupe_id: uuid.UUID) -> list[WrittenRule]:
    """The troupe's written rules in reading order."""
    found = db.scalars(select(WrittenRule).where(WrittenRule.troupe_id == troupe_id)).all()
    return sorted(found, key=lambda r: (section_order(r.section), r.position, r.created_at))


def linked_traits(db: Session, rules: list[WrittenRule]) -> dict[uuid.UUID, LinkedTrait]:
    """The trait each rule linked to one is about, by the trait definition's id."""
    ids = {r.trait_definition_id for r in rules if r.trait_definition_id is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(TraitDefinition.id, RuleSet.splat, TraitCategory.key, TraitDefinition.name)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .where(TraitDefinition.id.in_(ids))
    ).all()
    return {row[0]: LinkedTrait(row[1], row[2], row[3]) for row in rows}


def find_trait(
    db: Session, troupe_id: uuid.UUID, splat: str, category: str, name: str
) -> TraitDefinition | None:
    """A trait of the rule set, or one of the troupe's own merits and flaws."""
    return db.scalars(
        select(TraitDefinition)
        .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
        .join(RuleSet, TraitCategory.rule_set_id == RuleSet.id)
        .where(
            RuleSet.splat == splat,
            TraitCategory.key == category,
            TraitDefinition.name == name,
            TraitDefinition.troupe_id.is_(None) | (TraitDefinition.troupe_id == troupe_id),
        )
        .order_by(TraitDefinition.troupe_id.nulls_first())
        .limit(1)
    ).first()


def last_in(db: Session, troupe_id: uuid.UUID, section: str) -> int:
    """The position after the last rule in the section."""
    found = db.scalar(
        select(func.max(WrittenRule.position)).where(
            WrittenRule.troupe_id == troupe_id, WrittenRule.section == section
        )
    )
    return (found or 0) + 1


def move(db: Session, rule: WrittenRule, up: bool) -> bool:
    """Swap a rule with its neighbour in its section. Whether it moved."""
    in_section = [r for r in listed(db, rule.troupe_id) if r.section == rule.section]
    at = in_section.index(rule)
    other = at - 1 if up else at + 1
    if not 0 <= other < len(in_section):
        return False
    # Numbered afresh, so rules that once shared a position swap cleanly.
    in_section[at], in_section[other] = in_section[other], in_section[at]
    for n, r in enumerate(in_section, start=1):
        r.position = n
    db.flush()
    return True


def by_trait(
    db: Session, troupe_id: uuid.UUID, splat: str
) -> dict[tuple[str, str], list[WrittenRule]]:
    """The troupe's written rules about each of the splat's traits, by category and name."""
    found = listed(db, troupe_id)
    traits = linked_traits(db, found)
    about: dict[tuple[str, str], list[WrittenRule]] = {}
    for rule in found:
        trait = traits.get(rule.trait_definition_id) if rule.trait_definition_id else None
        if trait is not None and trait.splat == splat:
            about.setdefault((trait.category, trait.name), []).append(rule)
    return about
