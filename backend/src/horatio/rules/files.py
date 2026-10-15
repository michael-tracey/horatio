"""Reading rule sets from the TOML files in `horatio/rules/data/`, and checking them."""

import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from horatio.rules.checks import CheckData, check_from_dict, validate_condition
from horatio.rules.conditions import validate
from horatio.rules.grants import GrantData, grant_from_dict, validate_grant
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


# What Yorick's `requirement` column says about generation, as a condition on the
# Generation background.
GENERATION_REQUIREMENTS: dict[str, dict[str, int]] = {
    "Neonate": {"lte": 1},
    "Neonate or Ancilla": {"lte": 2},
    "Master or Luminary Elder": {"gte": 4},
}


def derived_checks(traits: Mapping[tuple[str, str], TraitData]) -> list[dict[str, Any]]:
    """Checks that follow from the catalogue itself: a merit or flaw whose
    requirement names a clan or bloodline is only for that clan (MET: VTM p. 238),
    and one whose requirement names a generation only for that generation."""
    clans = {name for (category, name) in traits if category == "clan"}
    families = {name.split(":")[0].strip() for name in clans}
    found: list[dict[str, Any]] = []
    for (category, name), trait in sorted(traits.items()):
        requirement = trait.properties.get("requirement")
        if category not in ("merits", "flaws") or not requirement:
            continue
        page = trait.page_reference
        if requirement in clans and ":" in requirement:
            requires: dict[str, Any] = {"clan": [requirement]}
        elif requirement in families:
            requires = {"clan_family": [requirement]}
        elif requirement in GENERATION_REQUIREMENTS:
            requires = {"generation": GENERATION_REQUIREMENTS[requirement]}
        else:
            continue
        found.append(
            {
                "key": f"{category}/{name}/requirement",
                "category": category,
                "name": name,
                "requires": requires,
                "message": f"{name} is only for {requirement}"
                + (" characters." if requirement in GENERATION_REQUIREMENTS else "."),
                **({"page": page} if page else {}),
            }
        )
    return found


def load_checks(
    where: str,
    raw_checks: list[dict[str, Any]],
    traits: Mapping[tuple[str, str], TraitData],
    categories: Mapping[str, CategoryData],
) -> list[CheckData]:
    """The rule set's checks, written and derived, each with a key and validated."""
    known = set(traits)
    checks: list[CheckData] = []
    seen: dict[str, int] = {}
    for raw in derived_checks(traits) + raw_checks:
        subject = raw.get("name") or raw.get("name_prefix") or "*"
        if "key" not in raw:
            base = f"{raw['category']}/{subject}"
            seen[base] = seen.get(base, 0) + 1
            raw = {**raw, "key": f"{base}/{seen[base]}"}
        if raw["category"] not in categories:
            raise ValueError(
                f"{where}: check {raw['key']} is about unknown category {raw['category']!r}"
            )
        if raw.get("name") and (raw["category"], raw["name"]) not in known:
            raise ValueError(f"{where}: check {raw['key']} is about an unknown trait")
        if not (raw.get("requires") or raw.get("forbids")):
            raise ValueError(f"{where}: check {raw['key']} neither requires nor forbids anything")
        for condition in (raw.get("requires"), raw.get("forbids")):
            if condition:
                validate_condition(condition, known)
        checks.append(check_from_dict(raw))
    keys = [c.key for c in checks]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{where}: two checks share a key")
    return checks


def load_grants(
    where: str,
    raw_grants: list[dict[str, Any]],
    traits: Mapping[tuple[str, str], TraitData],
    categories: Mapping[str, CategoryData],
) -> list[GrantData]:
    grants: list[GrantData] = []
    seen: dict[str, int] = {}
    for raw in raw_grants:
        if "key" not in raw:
            base = f"{raw['source']['category']}/{raw['source']['name']}"
            seen[base] = seen.get(base, 0) + 1
            raw = {**raw, "key": f"{base}/{seen[base]}"}
        grant = grant_from_dict(raw)
        try:
            validate_grant(grant, set(traits), set(categories))
            if grant.when:
                validate_condition(grant.when, set(traits))
        except ValueError as error:
            raise ValueError(f"{where}: {error}") from error
        grants.append(grant)
    return grants


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
            requires=c.get("requires"),
            change_cost=c.get("change_cost"),
            points_limit=c.get("points_limit"),
            usual_max=c.get("usual_max"),
            max_held=c.get("max_held"),
            derived=c.get("derived", False),
            buy_off_factor=c.get("buy_off_factor"),
            downtime_actions=c.get("downtime_actions"),
            downtime_waived_by=tuple(c.get("downtime_waived_by", [])),
            specializes=c.get("specializes"),
        )
        for c in raw["categories"]
    }
    raw_traits = list(raw.get("traits", []))
    titles = list(raw.get("titles", []))
    for trait_file in raw.get("trait_files", []):
        with (path.parent / trait_file).open("rb") as f:
            included = tomllib.load(f)
        raw_traits += included.get("traits", [])
        titles += included.get("titles", [])
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
    raw_checks = list(raw.get("checks", []))
    creation_only = list(raw.get("creation_only", []))
    for check_file in raw.get("check_files", []):
        with (path.parent / check_file).open("rb") as f:
            included_checks = tomllib.load(f)
        raw_checks += included_checks.get("checks", [])
        creation_only += included_checks.get("creation_only", [])
    for selector in creation_only:
        if selector["category"] not in categories:
            raise ValueError(f"{path.name}: creation_only names unknown category")
        if selector.get("name") and (selector["category"], selector["name"]) not in traits:
            raise ValueError(f"{path.name}: creation_only names unknown trait {selector['name']!r}")
    checks = load_checks(path.name, raw_checks, traits, categories)
    raw_grants = list(raw.get("grants", []))
    for grant_file in raw.get("grant_files", []):
        with (path.parent / grant_file).open("rb") as f:
            raw_grants += tomllib.load(f).get("grants", [])
    grants = load_grants(path.name, raw_grants, traits, categories)
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
                when=r.get("when"),
            )
            for r in raw.get("creation_rules", [])
        ],
        starting_traits=[
            StartingTraitData(category=t["category"], name=t["name"], rating=t.get("rating"))
            for t in raw.get("starting_traits", [])
        ],
        titles=tuple(sorted(set(titles))),
        checks=checks,
        grants=grants,
        creation_only=tuple(creation_only),
        banked_xp=raw.get("banked_xp"),
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
    for category in categories.values():
        if (
            category.requires is not None
            and (
                category.requires.get("category"),
                category.requires.get("name"),
            )
            not in traits
        ):
            raise ValueError(f"{path.name}: {category.key} requires an unknown trait")
    return rule_set


def all_rule_set_files() -> Iterable[Path]:
    """Rule set files; `*_traits.toml`, `*_checks.toml` and `*_grants.toml` are parts
    they include."""
    return sorted(
        p
        for p in DATA_DIR.glob("*.toml")
        if not p.name.endswith(("_traits.toml", "_checks.toml", "_grants.toml"))
    )
