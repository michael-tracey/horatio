"""Reading rule sets from the TOML files in `horatio/rules/data/`, and checking them."""

import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from horatio.rules.conditions import validate
from horatio.rules.model import (
    DEFAULT_MAX_RATING,
    SCHEMES,
    ActionKindData,
    AllowanceRuleData,
    CategoryData,
    CostRuleData,
    CreationRuleData,
    RuleSetData,
    StartingTraitData,
    TraitData,
)
from horatio.rules.splats import SPLATS

DATA_DIR = Path(__file__).parent / "data"


def cost_rule_from_dict(raw: dict[str, Any], *, house: bool = False) -> CostRuleData:
    table = raw.get("table")
    return CostRuleData(
        category=raw["category"],
        scheme=raw["scheme"],
        trait=raw.get("trait"),
        condition=raw.get("condition"),
        rate=raw.get("rate"),
        table=tuple(table) if table is not None else None,
        text=raw.get("text"),
        house=house,
    )


def allowance_rule_from_dict(raw: dict[str, Any], *, house: bool = False) -> AllowanceRuleData:
    return AllowanceRuleData(
        action_kind=raw["action_kind"],
        scheme=raw["scheme"],
        amount=raw["amount"],
        category=raw.get("category"),
        trait=raw.get("trait"),
        min_rating=raw.get("min_rating", 1),
        house=house,
    )


def check_allowance_rule(
    rule: AllowanceRuleData, rule_set: RuleSetData, extra_kinds: Iterable[str] = ()
) -> None:
    where = f"allowance rule for {rule.action_kind}"
    if rule.action_kind not in rule_set.action_kinds and rule.action_kind not in extra_kinds:
        raise ValueError(f"{where}: unknown action kind")
    if rule.scheme not in ("fixed", "per_dot"):
        raise ValueError(f"{where}: unknown scheme {rule.scheme!r}")
    if (rule.category is None) != (rule.trait is None):
        raise ValueError(f"{where}: name both a category and a trait, or neither")
    if rule.category is not None and (rule.category, rule.trait) not in rule_set.traits:
        raise ValueError(f"{where}: no {rule.category} trait {rule.trait!r}")


def check_creation_rules(rules: Iterable[CreationRuleData], rule_set: RuleSetData) -> None:
    """Refuse creation rules a character could not be built with."""
    seen_picks: set[tuple[str, int]] = set()
    kinds: dict[str, str] = {}
    for rule in rules:
        where = f"creation rule for {rule.category}"
        if (
            rule.restriction is not None
            and rule.restriction not in SPLATS[rule_set.splat].fact_names
        ):
            raise ValueError(f"{where}: unknown restriction {rule.restriction!r}")
        category = rule_set.categories.get(rule.category)
        if category is None or not category.rated:
            raise ValueError(f"{where}: needs a rated category")
        kind = "points" if rule.points is not None else "picks"
        if kinds.setdefault(rule.category, kind) != kind:
            raise ValueError(f"{where}: a category has picks or points, not both")
        if kind == "points":
            if rule.rating is not None or rule.picks is not None or (rule.points or 0) < 1:
                raise ValueError(f"{where}: a points rule gives only a positive number of points")
            if (rule.category, 0) in seen_picks:
                raise ValueError(f"{where}: only one points rule per category")
            seen_picks.add((rule.category, 0))
        else:
            if rule.rating is None or rule.picks is None or rule.rating < 1 or rule.picks < 1:
                raise ValueError(
                    f"{where}: a picks rule needs a positive rating and number of picks"
                )
            if category.max_rating is not None and rule.rating > category.max_rating:
                raise ValueError(f"{where}: rating above the category's maximum")
            if (rule.category, rule.rating) in seen_picks:
                raise ValueError(f"{where}: two rules for picks at {rule.rating}")
            seen_picks.add((rule.category, rule.rating))


def check_starting_trait(trait: StartingTraitData, rule_set: RuleSetData) -> None:
    if (trait.category, trait.name) not in rule_set.traits:
        raise ValueError(f"starting trait: no {trait.category} trait {trait.name!r}")
    rated = rule_set.categories[trait.category].rated
    if rated != (trait.rating is not None):
        raise ValueError(
            f"starting trait {trait.name!r}: rating must match whether the category is rated"
        )


def check_cost_rule(rule: CostRuleData, rule_set: RuleSetData) -> None:
    """Refuse a cost rule the pricing code could not apply."""
    where = f"cost rule for {rule.category} {rule.trait or ''}".rstrip()
    category = rule_set.categories.get(rule.category)
    if category is None:
        raise ValueError(f"{where}: unknown category")
    if not category.rated:
        raise ValueError(f"{where}: {rule.category} has no ratings to price")
    if rule.scheme not in SCHEMES:
        raise ValueError(f"{where}: unknown scheme {rule.scheme!r}")
    if rule.scheme in ("per_dot", "progressive", "fixed") and rule.rate is None:
        raise ValueError(f"{where}: {rule.scheme} needs a rate")
    if rule.scheme == "table" and not rule.table:
        raise ValueError(f"{where}: table needs a table")
    if rule.house and category.house_rules_per_trait and rule.trait is None:
        raise ValueError(f"{where}: house rules for {rule.category} must name one trait")
    validate(rule.condition, SPLATS[rule_set.splat].fact_names)


def load_rule_set(path: Path) -> RuleSetData:
    with path.open("rb") as f:
        raw = tomllib.load(f)

    if raw["splat"] not in SPLATS:
        raise ValueError(f"{path.name}: no splat {raw['splat']!r} in horatio.rules.splats")

    categories = {
        c["key"]: CategoryData(
            key=c["key"],
            name=c["name"],
            group=c["group"],
            rated=c.get("rated", True),
            max_rating=c.get("max_rating", DEFAULT_MAX_RATING) if c.get("rated", True) else None,
            house_rules_per_trait=c.get("house_rules_per_trait", False),
        )
        for c in raw["categories"]
    }
    raw_traits = list(raw.get("traits", []))
    for trait_file in raw.get("trait_files", []):
        with (path.parent / trait_file).open("rb") as f:
            raw_traits += tomllib.load(f).get("traits", [])
    traits: dict[tuple[str, str], TraitData] = {}
    for t in raw_traits:
        if (t["category"], t["name"]) in traits:
            raise ValueError(f"{path.name}: {t['category']} {t['name']!r} is defined twice")
        traits[(t["category"], t["name"])] = TraitData(
            category=t["category"],
            name=t["name"],
            description=t.get("description"),
            page_reference=t.get("page_reference"),
            properties=t.get("properties", {}),
        )
    action_kinds = {
        k["key"]: ActionKindData(key=k["key"], name=k["name"], fields=tuple(k.get("fields", [])))
        for k in raw.get("action_kinds", [])
    }
    allowance_rules = [allowance_rule_from_dict(r) for r in raw.get("allowance_rules", [])]
    rule_set = RuleSetData(
        key=raw["key"],
        splat=raw["splat"],
        name=raw["name"],
        version=raw["version"],
        starting_xp=raw.get("starting_xp", 0),
        categories=categories,
        cost_rules=[cost_rule_from_dict(r) for r in raw["cost_rules"]],
        traits=traits,
        action_kinds=action_kinds,
        allowance_rules=allowance_rules,
        creation_rules=[
            CreationRuleData(
                category=r["category"],
                rating=r.get("rating"),
                picks=r.get("picks"),
                points=r.get("points"),
                restriction=r.get("restriction"),
            )
            for r in raw.get("creation_rules", [])
        ],
        starting_traits=[
            StartingTraitData(category=t["category"], name=t["name"], rating=t.get("rating"))
            for t in raw.get("starting_traits", [])
        ],
    )
    for allowance_rule in allowance_rules:
        check_allowance_rule(allowance_rule, rule_set)
    check_creation_rules(rule_set.creation_rules, rule_set)
    for starting in rule_set.starting_traits:
        check_starting_trait(starting, rule_set)

    for rule in rule_set.cost_rules:
        check_cost_rule(rule, rule_set)
        if rule.trait is not None and (rule.category, rule.trait) not in traits:
            raise ValueError(f"{path.name}: cost rule names undefined trait {rule.trait!r}")
    for category, _name in traits:
        if category not in categories:
            raise ValueError(f"{path.name}: trait in unknown category {category!r}")
    return rule_set


def all_rule_set_files() -> Iterable[Path]:
    """Rule set files; `*_traits.toml` files are catalogues they include."""
    return sorted(p for p in DATA_DIR.glob("*.toml") if not p.name.endswith("_traits.toml"))
