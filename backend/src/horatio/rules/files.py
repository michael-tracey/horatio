"""Reading rule sets from the TOML files in `horatio/rules/data/`, and checking them."""

import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from horatio.rules.checks import REQUIREMENT_KEY, CheckData, check_from_dict, validate_condition
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
    FeedingModifierData,
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


def feeding_modifier_from_dict(raw: dict[str, Any]) -> FeedingModifierData:
    return FeedingModifierData(
        category=raw["category"],
        trait=raw["trait"],
        amount=raw.get("amount", 0),
        herd_factor=raw.get("herd_factor", 1),
        always_half=raw.get("always_half", False),
        page=raw.get("page"),
    )


def feeding_modifier_to_dict(modifier: FeedingModifierData) -> dict[str, Any]:
    raw: dict[str, Any] = {"category": modifier.category, "trait": modifier.trait}
    if modifier.amount:
        raw["amount"] = modifier.amount
    if modifier.herd_factor != 1:
        raw["herd_factor"] = modifier.herd_factor
    if modifier.always_half:
        raw["always_half"] = True
    if modifier.page is not None:
        raw["page"] = modifier.page
    return raw


def check_feeding_modifier(modifier: FeedingModifierData, rule_set: RuleSetData) -> None:
    where = f"feeding modifier for {modifier.trait}"
    if (modifier.category, modifier.trait) not in rule_set.traits:
        raise ValueError(f"{where}: no {modifier.category} trait {modifier.trait!r}")
    if modifier.herd_factor < 0:
        raise ValueError(f"{where}: herd_factor cannot be negative")
    if not (modifier.amount or modifier.herd_factor != 1 or modifier.always_half):
        raise ValueError(f"{where}: changes nothing")


def check_creation_rules(rules: Iterable[CreationRuleData], rule_set: RuleSetData) -> None:
    """Refuse creation rules a character could not be built with."""
    # Two rules for one rating are fine when their conditions differ (Inept's one pick
    # fewer at 1): whichever holds for the sheet is the one that counts.
    seen_picks: set[tuple[str, int, str]] = set()
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
            if (rule.category, 0, "") in seen_picks:
                raise ValueError(f"{where}: only one points rule per category")
            seen_picks.add((rule.category, 0, ""))
        else:
            if rule.rating is None or rule.picks is None or rule.rating < 1 or rule.picks < 1:
                raise ValueError(
                    f"{where}: a picks rule needs a positive rating and number of picks"
                )
            if category.max_rating is not None and rule.rating > category.max_rating:
                raise ValueError(f"{where}: rating above the category's maximum")
            condition = repr(sorted((rule.when or {}).items()))
            if (rule.category, rule.rating, condition) in seen_picks:
                raise ValueError(f"{where}: two rules for picks at {rule.rating}")
            seen_picks.add((rule.category, rule.rating, condition))


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
                "key": f"{category}/{name}{REQUIREMENT_KEY}",
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
    left_out: Sequence[Mapping[str, str]] = (),
) -> list[CheckData]:
    """The rule set's checks, written and derived, each with a key and validated.
    Those about traits the rule set leaves out are dropped once they have their key,
    so the rest keep the keys they have where nothing is left out."""
    known = set(traits)
    checks: list[CheckData] = []
    seen: dict[str, int] = {}
    for raw in derived_checks(traits) + raw_checks:
        subject = raw.get("name") or raw.get("name_prefix") or "*"
        if "key" not in raw:
            base = f"{raw['category']}/{subject}"
            seen[base] = seen.get(base, 0) + 1
            raw = {**raw, "key": f"{base}/{seen[base]}"}
        if names_left_out(raw, left_out):
            continue
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
        if raw.get("step") is not None and (
            raw["step"] not in categories or raw.get("strength") != "complete"
        ):
            raise ValueError(
                f"{where}: check {raw['key']} names a step; it must be a category,"
                " on a complete check"
            )
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
    left_out: Sequence[Mapping[str, str]] = (),
) -> list[GrantData]:
    grants: list[GrantData] = []
    seen: dict[str, int] = {}
    for raw in raw_grants:
        if "key" not in raw:
            base = f"{raw['source']['category']}/{raw['source']['name']}"
            seen[base] = seen.get(base, 0) + 1
            raw = {**raw, "key": f"{base}/{seen[base]}"}
        if names_left_out(raw, left_out):
            continue
        grant = grant_from_dict(raw)
        try:
            validate_grant(grant, set(traits), set(categories))
            if grant.when:
                validate_condition(grant.when, set(traits))
        except ValueError as error:
            raise ValueError(f"{where}: {error}") from error
        grants.append(grant)
    return grants


# Sections a rule set can borrow whole from another rule set's file (`borrow`).
BORROWABLE = ("action_kinds", "allowance_rules", "feeding_modifiers")


def borrowed(path: Path, raw: dict[str, Any]) -> dict[str, Any]:
    """The rule set with the sections it borrows from other files put ahead of its own:
    `borrow = { action_kinds = "bns_met_vampire.toml" }` takes the vampire's."""
    found = dict(raw)
    for section, source in raw.get("borrow", {}).items():
        if section not in BORROWABLE:
            raise ValueError(f"{path.name}: cannot borrow {section!r}")
        with (path.parent / source).open("rb") as f:
            found[section] = tomllib.load(f).get(section, []) + raw.get(section, [])
    return found


def leaves_out(selector: Mapping[str, str], category: str, names: Iterable[str]) -> bool:
    """Whether a `leave_out` selector ({category} or {category, name}) is about a
    reference to these traits of a category (no names: the whole category)."""
    return selector["category"] == category and (
        "name" not in selector or selector["name"] in names
    )


def names_left_out(raw: Any, left_out: Sequence[Mapping[str, str]]) -> bool:
    """Whether a check, grant or creation-only selector is about a trait the rule set
    leaves out, or names one anywhere in its conditions: a table with a `category`,
    and a `name` or `names`, that a `leave_out` selector covers."""
    if isinstance(raw, Mapping):
        table = cast(Mapping[str, Any], raw)
        category = table.get("category")
        if isinstance(category, str):
            name, names = table.get("name"), table.get("names")
            named = [name] if isinstance(name, str) else names if isinstance(names, list) else []
            if any(leaves_out(s, category, cast(list[str], named)) for s in left_out):
                return True
        return any(names_left_out(v, left_out) for v in table.values())
    if isinstance(raw, list):
        return any(names_left_out(v, left_out) for v in cast(list[Any], raw))
    return False


def load_rule_set(path: Path) -> RuleSetData:
    with path.open("rb") as f:
        raw = borrowed(path, tomllib.load(f))

    if raw["splat"] not in SPLATS:
        raise ValueError(f"{path.name}: no splat {raw['splat']!r} in horatio.rules.splats")
    # Traits the rule set leaves out of the files it includes (a ghoul's Generation and
    # Paths), with the checks, grants and creation-only selectors about them.
    left_out: list[dict[str, str]] = list(raw.get("leave_out", []))

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
    for selector in left_out:
        if "category" not in selector or not any(
            leaves_out(selector, t["category"], [t["name"]]) for t in raw_traits
        ):
            raise ValueError(f"{path.name}: leave_out {selector} leaves out nothing")
    raw_traits = [
        t
        for t in raw_traits
        if not any(leaves_out(s, t["category"], [t["name"]]) for s in left_out)
    ]
    traits: dict[tuple[str, str], TraitData] = {}
    for t in raw_traits:
        if (t["category"], t["name"]) in traits:
            raise ValueError(f"{path.name}: {t['category']} {t['name']!r} is defined twice")
        traits[(t["category"], t["name"])] = TraitData(
            category=t["category"],
            name=t["name"],
            description=t.get("description"),
            page_reference=t.get("page_reference"),
            # A trait's tags ("vampire_only") are kept with its properties.
            properties={**t.get("properties", {}), **({"tags": t["tags"]} if "tags" in t else {})},
        )
    raw_checks = list(raw.get("checks", []))
    creation_only = list(raw.get("creation_only", []))
    for check_file in raw.get("check_files", []):
        with (path.parent / check_file).open("rb") as f:
            included_checks = tomllib.load(f)
        raw_checks += included_checks.get("checks", [])
        creation_only += included_checks.get("creation_only", [])
    creation_only = [c for c in creation_only if not names_left_out(c, left_out)]
    for selector in creation_only:
        if selector["category"] not in categories:
            raise ValueError(f"{path.name}: creation_only names unknown category")
        if selector.get("name") and (selector["category"], selector["name"]) not in traits:
            raise ValueError(f"{path.name}: creation_only names unknown trait {selector['name']!r}")
        if selector.get("until", "accepted") != "accepted":
            raise ValueError(f"{path.name}: creation_only until can only be 'accepted'")
    checks = load_checks(path.name, raw_checks, traits, categories, left_out)
    raw_grants = list(raw.get("grants", []))
    for grant_file in raw.get("grant_files", []):
        with (path.parent / grant_file).open("rb") as f:
            raw_grants += tomllib.load(f).get("grants", [])
    grants = load_grants(path.name, raw_grants, traits, categories, left_out)
    action_kinds = {
        k["key"]: ActionKindData(
            key=k["key"],
            name=k["name"],
            fields=tuple(k.get("fields", [])),
            actions=tuple(k.get("actions", [])),
        )
        for k in raw.get("action_kinds", [])
    }
    for kind in action_kinds.values():
        check_named_actions(path.name, kind)
    allowance_rules = [allowance_rule_from_dict(r) for r in raw.get("allowance_rules", [])]
    feeding_modifiers = [feeding_modifier_from_dict(r) for r in raw.get("feeding_modifiers", [])]
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
        feeding_modifiers=feeding_modifiers,
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
    for modifier in feeding_modifiers:
        check_feeding_modifier(modifier, rule_set)
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


def check_named_actions(source: str, kind: ActionKindData) -> None:
    """An action kind's named actions each have a key and a name, keys differ, and a
    level, where there is one, is from 1 to 10."""
    keys = [a.get("key") for a in kind.actions]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{source}: {kind.key} names an action twice")
    for action in kind.actions:
        if not action.get("key") or not action.get("name"):
            raise ValueError(f"{source}: each of {kind.key}'s actions needs a key and a name")
        level = action.get("level")
        if level is not None and (not isinstance(level, int) or not 1 <= level <= 10):
            raise ValueError(f"{source}: {kind.key} action {action['key']!r} level is 1 to 10")
        if level is not None and action.get("conflict"):
            raise ValueError(f"{source}: {kind.key} conflict action {action['key']!r} has a level")


def all_rule_set_files() -> Iterable[Path]:
    """Rule set files; `*_traits.toml`, `*_checks.toml` and `*_grants.toml` are parts
    they include, `*_powers.toml` is horatio.reference's quick notes, and
    `*_npc_kinds.toml` is horatio.rules.npc_kinds' NPC kinds."""
    return sorted(
        p
        for p in DATA_DIR.glob("*.toml")
        if not p.name.endswith(
            ("_traits.toml", "_checks.toml", "_grants.toml", "_powers.toml", "_npc_kinds.toml")
        )
    )
