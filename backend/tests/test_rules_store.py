"""Rule sets loaded into the database, and house rules read back out."""

import json
from collections.abc import Sequence
from dataclasses import asdict

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from horatio.models import CostRule, TraitCategory, TraitDefinition, Troupe, User
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.model import CostRuleData, SheetTrait
from horatio.rules.pricing import trait_cost
from horatio.rules.store import add_house_rule, read_troupe_rules, sync_rule_set

VAMPIRE = load_rule_set(DATA_DIR / "bns_met_vampire.toml")


def normalised(rules: Sequence[CostRuleData]) -> list[str]:
    """Cost rules as sorted JSON; Postgres does not keep a condition's key order."""
    return sorted(json.dumps(asdict(r), sort_keys=True) for r in rules)


def make_troupe(session: Session, name: str) -> Troupe:
    lead = User(email=f"lead-{name}@example.com", display_name=name)
    session.add(lead)
    session.flush()
    troupe = Troupe(name=name, lead_user_id=lead.id)
    session.add(troupe)
    session.flush()
    return troupe


def merit(name: str, rating: int) -> SheetTrait:
    return SheetTrait(category="merits", name=name, rating=rating)


def test_the_rule_set_reads_back_as_it_was_loaded(session: Session) -> None:
    sync_rule_set(session, VAMPIRE)

    stored = read_troupe_rules(session, "vampire", None)

    assert stored.house_rules == []
    assert stored.rule_set.categories == VAMPIRE.categories
    assert stored.rule_set.traits == VAMPIRE.traits
    assert normalised(stored.rule_set.cost_rules) == normalised(VAMPIRE.cost_rules)


def test_loading_twice_changes_nothing(session: Session) -> None:
    sync_rule_set(session, VAMPIRE)
    counts = [
        session.scalar(select(func.count()).select_from(t))
        for t in (TraitCategory, TraitDefinition, CostRule)
    ]

    sync_rule_set(session, VAMPIRE)

    assert counts == [
        session.scalar(select(func.count()).select_from(t))
        for t in (TraitCategory, TraitDefinition, CostRule)
    ]


def test_house_rules_apply_only_to_their_troupe(session: Session) -> None:
    sync_rule_set(session, VAMPIRE)  # the catalogue includes Iron Will
    ours, theirs = make_troupe(session, "ours"), make_troupe(session, "theirs")
    add_house_rule(
        session,
        ours.id,
        "vampire",
        CostRuleData("merits", "fixed", rate=5, trait="Iron Will", text="Rarer in our city"),
    )
    iron_will = merit("Iron Will", 3)

    ours_rules = read_troupe_rules(session, "vampire", ours.id)
    assert trait_cost(ours_rules, [iron_will], iron_will).cost == 5
    assert ours_rules.house_rules[0].text == "Rarer in our city"
    for rules in (
        read_troupe_rules(session, "vampire", theirs.id),
        read_troupe_rules(session, "vampire", None),
    ):
        assert trait_cost(rules, [iron_will], iron_will).cost == 3


def test_reloading_the_rule_set_keeps_house_rules(session: Session) -> None:
    sync_rule_set(session, VAMPIRE)  # the catalogue includes Iron Will
    troupe = make_troupe(session, "ours")
    add_house_rule(
        session, troupe.id, "vampire", CostRuleData("merits", "fixed", rate=5, trait="Iron Will")
    )

    sync_rule_set(session, VAMPIRE)

    assert len(read_troupe_rules(session, "vampire", troupe.id).house_rules) == 1


def test_a_house_rule_for_all_merits_is_refused(session: Session) -> None:
    sync_rule_set(session, VAMPIRE)
    troupe = make_troupe(session, "ours")

    with pytest.raises(ValueError, match="must name one trait"):
        add_house_rule(session, troupe.id, "vampire", CostRuleData("merits", "per_dot", rate=2))


def test_the_database_refuses_a_cost_rule_without_its_rate(session: Session) -> None:
    rule_set = sync_rule_set(session, VAMPIRE)
    skills = session.scalars(
        select(TraitCategory).where(
            TraitCategory.rule_set_id == rule_set.id, TraitCategory.key == "skills"
        )
    ).one()
    session.add(CostRule(rule_set_id=rule_set.id, category_id=skills.id, scheme="per_dot"))

    with pytest.raises(IntegrityError):
        session.flush()
