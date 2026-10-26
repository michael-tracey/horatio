"""What a troupe's house merits and flaws do on the sheet (horatio.house_traits).

A storyteller gives one effect blocks on a form. Each block is turned into the
grants and checks the engine already runs for merits from the book
(horatio.rules.grants, horatio.rules.checks), built with the rules files' own
`grant_from_dict` and `check_from_dict` and checked as the files are, so a house
merit does exactly what the book merit it copies does. Blocks, by `kind`:

    free_up_to     the first `amount` dots of a trait are free; with several
                   `names`, of the one the player chooses in the merit's detail
                   (Personal Cult)
    free_choices   the player picks `count` different traits from `names`, each
                   with `amount` free dots (Ventrue Royalty's places)
    add            each of `names` goes up (or down) by `amount`, free: health
                   levels (Rugged, Low Pain Threshold)
    raise_max      `names`, or every trait of the category, can go `amount` higher
                   than usual (Blood of the Tzimisce)
    cost_percent   `names`, or the whole category, cost `amount` percent of their
                   price (Supernatural Aria)
    price_in_clan, price_out_of_clan
                   `names` are priced as in-clan, or as out-of-clan (Thaumaturgic
                   Expertise, Inept)
    extra_in_clan  one more in-clan discipline, chosen from `names`, as Additional
                   Common Discipline adds one (p. 248)
    requires, forbids
                   the merit needs, or cannot be held with, a clan (`test` "clan":
                   a clan and its bloodlines), a sect ("sect"), or a trait at a
                   rating ("trait"), with a check's `strength`

`detail` narrows the trait of a raise or a price to one field (Performance:
Singing). Every block names its category, but extra_in_clan and the checks.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from horatio.rules.checks import CheckData, check_from_dict, validate_condition
from horatio.rules.grants import GrantData, grant_from_dict, validate_grant
from horatio.rules.model import HouseTraitData, RuleSetData, house_page

EXTRA_IN_CLAN = "extra_in_clan_disciplines"
# The book merit whose rules an extra_in_clan block follows, and the others that add
# an in-clan discipline the same way (pp. 242, 248).
LIKE_IN_CLAN = "Additional Common Discipline"
ADDS_IN_CLAN = ("Additional Common Discipline", "Additional Uncommon Discipline", "Pliable Blood")

GRANT_KINDS = (
    "free_up_to",
    "free_choices",
    "add",
    "raise_max",
    "cost_percent",
    "price_in_clan",
    "price_out_of_clan",
)
CHECK_KINDS = ("requires", "forbids")
KINDS = (*GRANT_KINDS, "extra_in_clan", *CHECK_KINDS)
STRENGTHS = ("refuse", "complete", "review", "note")
TESTS = ("clan", "sect", "trait")

# What each kind keeps of a block, beside its kind.
FIELDS: dict[str, tuple[str, ...]] = {
    "free_up_to": ("category", "names", "amount"),
    "free_choices": ("category", "names", "count", "amount"),
    "add": ("category", "names", "amount"),
    "raise_max": ("category", "names", "detail", "amount"),
    "cost_percent": ("category", "names", "detail", "amount"),
    "price_in_clan": ("category", "names", "detail"),
    "price_out_of_clan": ("category", "names", "detail"),
    "extra_in_clan": ("names",),
    "requires": ("test", "names", "category", "name", "rating", "strength"),
    "forbids": ("test", "names", "category", "name", "rating", "strength"),
}
DEFAULTS: dict[str, Any] = {
    "category": "",
    "names": [],
    "amount": 0,
    "count": 1,
    "detail": "",
    "test": "trait",
    "name": "",
    "rating": None,
    "strength": "refuse",
}


class BlockProblem(ValueError):
    """Why a block cannot be used, in plain words."""


@dataclass(frozen=True)
class Problem:
    # Which block, counted from 0.
    index: int
    message: str


@dataclass(frozen=True)
class Compiled:
    """What a house trait's blocks become."""

    grants: tuple[GrantData, ...] = ()
    checks: tuple[CheckData, ...] = ()
    # The disciplines its extra_in_clan block lets it add in-clan.
    in_clan: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()
    # What it does, a sentence a block.
    lines: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        return " ".join(self.lines)


def normalised(block: Mapping[str, Any]) -> dict[str, Any]:
    """A block with only its kind's fields, defaults filled in: as it is stored."""
    kind = block.get("kind")
    if kind not in FIELDS:
        raise BlockProblem("Choose what the effect does.")
    found: dict[str, Any] = {"kind": kind}
    for name in FIELDS[kind]:
        value = block.get(name, DEFAULTS[name])
        found[name] = list(value) if isinstance(value, list | tuple) else value
    if "names" in found:
        found["names"] = [str(n).strip() for n in found["names"] if str(n).strip()]
    for name in ("detail", "name", "category"):
        if isinstance(found.get(name), str):
            found[name] = found[name].strip()
    return found


def either(names: Sequence[str], word: str = "or") -> str:
    """ "A", "A or B", "A, B or C"."""
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} {word} {names[-1]}"


def dots(amount: int) -> str:
    return f"{amount} dot" if abs(amount) == 1 else f"{amount} dots"


def first(amount: int) -> str:
    return "The first dot" if amount == 1 else f"The first {amount} dots"


def are(amount: int) -> str:
    return "is" if amount == 1 else "are"


class Compiler:
    """Turns one house trait's blocks into grants and checks against a rule set."""

    def __init__(self, house: HouseTraitData, rule_set: RuleSetData) -> None:
        self.house = house
        self.rule_set = rule_set
        self.source = {"category": house.category, "name": house.name}
        self.page = house_page(house.troupe_name)
        known = set(rule_set.traits) | {(house.category, house.name)}
        self.known = known

    # --- reading a block ---------------------------------------------------------

    def category(self, block: Mapping[str, Any], *, derived: bool = False) -> str:
        key = block["category"]
        category = self.rule_set.categories.get(key)
        if category is None:
            raise BlockProblem("Choose a kind of trait.")
        if not category.rated or category.specializes or (category.derived and not derived):
            raise BlockProblem(f"{category.name} have no dots for this.")
        return key

    def category_name(self, key: str) -> str:
        category = self.rule_set.categories.get(key)
        return category.name.lower() if category else key

    def names(self, block: Mapping[str, Any], category: str, *, needed: bool = True) -> list[str]:
        names: list[str] = block["names"]
        if needed and not names:
            raise BlockProblem("Choose at least one trait.")
        if len(set(names)) < len(names):
            raise BlockProblem("A trait is listed twice.")
        for name in names:
            if (category, name) == (self.house.category, self.house.name):
                raise BlockProblem(f"An effect of {self.house.name} cannot be about itself.")
            if (category, name) not in self.rule_set.traits:
                raise BlockProblem(f"{name} is not one of the {self.category_name(category)}.")
        return names

    def amount(self, block: Mapping[str, Any], low: int, high: int, what: str) -> int:
        amount = block["amount"]
        if not isinstance(amount, int) or not low <= amount <= high:
            raise BlockProblem(f"{what} is {low} to {high}.")
        return amount

    def named(self, names: Sequence[str], detail: str) -> list[str]:
        return [f"{n}: {detail}" if detail else n for n in names]

    # --- the blocks ----------------------------------------------------------------

    def compile(self, blocks: Sequence[Mapping[str, Any]]) -> Compiled:
        grants: list[GrantData] = []
        checks: list[CheckData] = []
        in_clan: list[str] = []
        problems: list[Problem] = []
        lines: list[str] = []
        for index, raw in enumerate(blocks):
            try:
                block = normalised(raw)
                if block["kind"] == "extra_in_clan" and in_clan:
                    raise BlockProblem("One merit adds one in-clan discipline.")
                key = f"house/{self.house.id}/{index}"
                made_grants, made_checks, adds, line = self.block(key, block)
                for grant in made_grants:
                    validate_grant(grant, self.known, set(self.rule_set.categories))
                    if grant.when:
                        validate_condition(grant.when, self.known)
                for check in made_checks:
                    for condition in (check.requires, check.forbids):
                        if condition:
                            validate_condition(condition, self.known)
            except BlockProblem as problem:
                problems.append(Problem(index, str(problem)))
                continue
            except (ValueError, KeyError, TypeError) as error:
                # What the rules files' own checks refuse that the form did not catch.
                problems.append(Problem(index, f"The rules cannot use this: {error}."))
                continue
            grants += made_grants
            checks += made_checks
            in_clan += adds
            lines.append(line)
        return Compiled(tuple(grants), tuple(checks), tuple(in_clan), tuple(problems), tuple(lines))

    def grant(
        self, key: str, kind: str, target: dict[str, Any], amount: int, **more: Any
    ) -> GrantData:
        return grant_from_dict(
            {
                "key": key,
                "source": self.source,
                "kind": kind,
                "target": target,
                "amount": amount,
                "page": self.page,
                **more,
            }
        )

    def block(
        self, key: str, block: Mapping[str, Any]
    ) -> tuple[list[GrantData], list[CheckData], list[str], str]:
        kind = block["kind"]
        if kind in CHECK_KINDS:
            check, line = self.check(key, block)
            return [], [check], [], line
        if kind == "extra_in_clan":
            return self.extra_in_clan(key, block)
        derived = kind == "add"
        category = self.category(block, derived=derived)
        names = self.names(block, category, needed=kind not in ("raise_max", "cost_percent"))
        detail: str = block.get("detail", "")
        target: dict[str, Any] = {"category": category}
        if kind == "free_up_to":
            top = self.rule_set.categories[category].max_rating or 10
            amount = self.amount(block, 1, top, "The free dots")
            if len(names) == 1:
                target["name"] = names[0]
                line = self.free_line(category, names[0], amount)
            else:
                target["choose"] = names
                chooses = f"{either(names)}, which the player chooses,"
                line = f"{first(amount)} of {chooses} {are(amount)} free."
            return [self.grant(key, kind, target, amount)], [], [], line
        if kind == "free_choices":
            count = block["count"]
            if not isinstance(count, int) or not 1 <= count <= len(names):
                raise BlockProblem(f"The player picks 1 to {len(names)} of them.")
            amount = self.amount(block, 1, 10, "The free dots")
            target["choose"] = names
            grant = self.grant(key, kind, target, amount, picks={"places": [amount] * count})
            line = (
                f"The player picks {count} of {either(names, 'and')}, "
                f"each with {dots(amount)} free."
            )
            return [grant], [], [], line
        if kind == "add":
            amount = self.amount(block, -5, 5, "The change")
            if amount == 0:
                raise BlockProblem("Add or take away at least one.")
            made = [
                self.grant(f"{key}/{i}", kind, {"category": category, "name": n}, amount)
                for i, n in enumerate(names)
            ]
            return made, [], [], self.add_line(category, names, amount)
        if names:
            target["names"] = names
        if detail and names:
            target["detail"] = detail
        what = either(self.named(names, detail)) if names else f"All {self.category_name(category)}"
        if kind == "raise_max":
            amount = self.amount(block, 1, 5, "How much higher")
            line = f"{what} can go {amount} higher than usual."
            return [self.grant(key, kind, target, amount)], [], [], line
        if kind == "cost_percent":
            amount = self.amount(block, 0, 500, "The percent")
            line = f"{what} {'cost' if len(names) != 1 else 'costs'} {amount}% of the usual XP."
            return [self.grant(key, kind, target, amount)], [], [], line
        if not names:
            raise BlockProblem("Choose at least one trait.")
        side = "in-clan" if kind == "price_in_clan" else "out-of-clan"
        line = f"{what} {'are' if len(names) > 1 else 'is'} priced as {side}."
        return [self.grant(key, kind, target, 0)], [], [], line

    def free_line(self, category: str, name: str, amount: int) -> str:
        if category in ("merits", "flaws"):
            return f"Gives {name} free."
        return f"{first(amount)} of {name} {are(amount)} free."

    def add_line(self, category: str, names: Sequence[str], amount: int) -> str:
        if category == "health_levels":
            levels = "health level" if abs(amount) == 1 else "health levels"
            each = " each" if len(names) > 1 else ""
            if amount > 0:
                return f"{amount} more {either(names, 'and')} {levels}{each}."
            return f"{-amount} fewer {either(names, 'and')} {levels}{each}."
        if amount > 0:
            return f"{dots(amount)} more of {either(names, 'and')}, free."
        return f"{dots(-amount)} fewer of {either(names, 'and')}."

    def extra_in_clan(
        self, key: str, block: Mapping[str, Any]
    ) -> tuple[list[GrantData], list[CheckData], list[str], str]:
        if EXTRA_IN_CLAN not in self.rule_set.categories:
            raise BlockProblem("These rules have no extra in-clan disciplines.")
        names = self.names(block, EXTRA_IN_CLAN)
        caitiff = ("clan", "Caitiff") in self.rule_set.traits
        not_caitiff = {"not": {"clan": ["Caitiff"]}}
        # As Additional Common Discipline: the one it adds starts without a free dot,
        # it must be chosen from its list before creation is finished, and no other
        # merit that adds one can be held with it.
        grant = self.grant(
            key,
            "no_free_dot",
            {"category": EXTRA_IN_CLAN, "names": names},
            0,
            **({"when": not_caitiff} if caitiff else {}),
        )
        chosen = {"count": {"category": EXTRA_IN_CLAN, "names": names, "gte": 1}}
        arms: list[dict[str, Any]] = [{"finished": True}]
        if caitiff:
            arms += [
                {"clan": ["Caitiff"], "count": {"category": EXTRA_IN_CLAN, "gte": 4}},
                {**not_caitiff, **chosen},
            ]
        else:
            arms.append(chosen)
        checks = [
            check_from_dict(
                {
                    "key": f"{key}/choose",
                    **self.source,
                    "requires": {"any_of": arms},
                    "strength": "complete",
                    "message": f"{self.house.name}: choose the in-clan discipline it adds.",
                    "page": self.page,
                }
            )
        ]
        others = [n for n in ADDS_IN_CLAN if ("merits", n) in self.rule_set.traits]
        if others:
            checks.append(
                check_from_dict(
                    {
                        "key": f"{key}/one",
                        **self.source,
                        "forbids": {"has_any": [{"category": "merits", "name": n} for n in others]},
                        "message": "Only one merit can add an in-clan discipline.",
                        "page": self.page,
                    }
                )
            )
        line = f"Adds one in-clan discipline, chosen from {either(names)}."
        return [grant], checks, names, line

    def check(self, key: str, block: Mapping[str, Any]) -> tuple[CheckData, str]:
        kind, test = block["kind"], block["test"]
        strength = block["strength"]
        if strength not in STRENGTHS:
            raise BlockProblem("Choose how strictly it holds.")
        name = self.house.name
        if test in ("clan", "sect"):
            names: list[str] = block["names"]
            if not names:
                raise BlockProblem(f"Choose at least one {test}.")
            if test == "clan":
                families = {n.split(":")[0].strip() for c, n in self.rule_set.traits if c == "clan"}
                unknown = [n for n in names if n not in families]
                condition: dict[str, Any] = {"clan_family": names}
            else:
                unknown = [n for n in names if ("sect", n) not in self.rule_set.traits]
                condition = (
                    {"has": {"category": "sect", "name": names[0]}}
                    if len(names) == 1
                    else {"has_any": [{"category": "sect", "name": n} for n in names]}
                )
            if unknown:
                raise BlockProblem(f"{either(unknown)}: no such {test} in these rules.")
            who = either(names) if test == "clan" else f"the {either(names)}"
            text = f"Only for {who}" if kind == "requires" else f"Not for {who}"
        elif test == "trait":
            category = self.rule_set.categories.get(block["category"])
            wanted = block["name"]
            if category is None or not wanted:
                raise BlockProblem("Choose the trait.")
            if (category.key, wanted) not in self.rule_set.traits:
                raise BlockProblem(f"{wanted} is not one of the {category.name.lower()}.")
            if (category.key, wanted) == (self.house.category, self.house.name):
                raise BlockProblem(f"{name} cannot need itself.")
            has: dict[str, Any] = {"category": category.key, "name": wanted}
            rating = block["rating"]
            fixed = self.rule_set.trait_properties(category.key, wanted).get("rating")
            if category.rated and fixed is None:
                top = category.max_rating or 10
                if not isinstance(rating, int) or not 1 <= rating <= top:
                    raise BlockProblem(f"The rating is 1 to {top}.")
                has["rating"] = rating
                held = f"{wanted} {rating} or more"
            else:
                held = wanted
            condition = {"has": has}
            text = f"Needs {held}" if kind == "requires" else f"Not with {held}"
        else:
            raise BlockProblem("Choose a clan, a sect or a trait.")
        when = {
            "refuse": "",
            "complete": " by the end of creation",
            "review": ", or staff approve it",
            "note": " (a note only)",
        }[strength]
        check = check_from_dict(
            {
                "key": key,
                **self.source,
                kind: condition,
                "strength": strength,
                "message": f"{name}: {text[0].lower()}{text[1:]}.",
                "page": self.page,
            }
        )
        return check, f"{text}{when}."


def compile_effects(house: HouseTraitData, rule_set: RuleSetData) -> Compiled:
    """The grants and checks a house trait's blocks make, and what it does in words;
    with the blocks that cannot be used and why."""
    return Compiler(house, rule_set).compile(house.effects)


def widened(check: CheckData, house: HouseTraitData, names: Sequence[str]) -> CheckData:
    """A book check about extra in-clan disciplines, letting the house trait add one
    from `names` wherever it lets Additional Common Discipline add one of its own."""
    if check.category != EXTRA_IN_CLAN:
        return check
    holds = {"category": house.category, "name": house.name}
    like = {"category": "merits", "name": LIKE_IN_CLAN}
    requires, forbids = check.requires, check.forbids
    arms = (requires or {}).get("any_of")
    if arms and any(a.get("has") == like for a in arms):
        requires = {
            **(requires or {}),
            "any_of": [*arms, {"has": holds, "self": {"names": list(names)}}],
        }
    unless = (forbids or {}).get("not")
    if isinstance(unless, Mapping) and like in unless.get("has_any", []):
        forbids = {
            **(forbids or {}),
            "not": {**unless, "has_any": [*unless["has_any"], holds]},
        }
    if (requires, forbids) == (check.requires, check.forbids):
        return check
    return replace(check, requires=requires, forbids=forbids)


def merged(
    rule_set: RuleSetData, house: Sequence[HouseTraitData]
) -> tuple[RuleSetData, list[HouseTraitData]]:
    """The rule set with the house traits' grants and checks added, and the house
    traits with what each does. A block that cannot be used (a trait the book has
    since lost) is left out; storytellers see why when they next change it."""
    grants = list(rule_set.grants)
    checks = list(rule_set.checks)
    found: list[HouseTraitData] = []
    for trait in house:
        compiled = compile_effects(trait, rule_set)
        grants += compiled.grants
        if compiled.in_clan:
            checks = [widened(c, trait, compiled.in_clan) for c in checks]
        checks += compiled.checks
        found.append(replace(trait, summary=compiled.summary, in_clan=compiled.in_clan))
    if not any(t.effects for t in house):
        return rule_set, found
    return replace(rule_set, grants=tuple(grants), checks=tuple(checks)), found
