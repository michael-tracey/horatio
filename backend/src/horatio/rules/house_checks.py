"""A troupe's own checks (horatio.house_checks): ones its storytellers add beside the
book's, built on a form rather than written in a rules file.

A house check is a check like any other (horatio.rules.checks): a subject, a
condition it requires or forbids, a strength and a message, and for a "complete"
check an optional creation step. It is turned into a `CheckData` with the rules
files' own `check_from_dict`, and the troupe's rules (horatio.rules.store) list it
among the rule set's checks, so purchases, creation, review holds and the sheet's
notes judge it exactly as they judge a book check.

Its subject is one trait, every trait of a category whose name starts with a
prefix (an empty prefix: the whole category), or every trait of a category of one
catalogue type (Clan merits). A type is not something a check's subject can say,
so it goes into the condition as the `kind` condition does: a check that requires
a condition of Clan merits requires it only of those that are Clan merits.

The form builds the condition from a part of the vocabulary, the part a
storyteller needs for a house rule:

    clan = [...]                    the clan is one of these
    clan_family = [...]             the clan is one of these or one of its bloodlines
    has = { category, name, rating? }
                                    the sheet holds that trait (at that rating)
    has_all = [ {...}, {...} ]      the sheet holds all of these (two "holds" side by side)
    generation = { gte?, lte? }     the Generation background's rating is at least,
                                    or at most, this
    finished = true                 the character's creation is finished
    copies = { gte = 2 }            the sheet holds the subject's trait this many times
    self = { names = [...] }        the subject is one of these traits
    not = { ... }                   the condition does not hold
    any_of = [ {...}, {...} ]       any of these conditions

Anything else is refused here, as is a value of the wrong shape, so a house check
can never stop the engine for the troupe's characters.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from horatio.rules import conditions
from horatio.rules.checks import CheckData, breaks, check_from_dict, validate_condition
from horatio.rules.model import RuleSetData, SheetTrait, house_page

Mode = Literal["requires", "forbids"]
STRENGTHS = ("refuse", "complete", "review", "note")
MODES = ("requires", "forbids")
# The start of a house check's key, after which comes its id.
KEY_PREFIX = "house-check/"
# The most blocks a condition may nest, and the most it may hold.
DEPTH = 6
SIZE = 60


class HouseCheckProblem(ValueError):
    """Why a house check cannot be used, in words for the storyteller."""


@dataclass(frozen=True)
class HouseCheckData:
    """A house check as staff make it, and as the database keeps it."""

    category: str
    mode: Mode
    condition: Mapping[str, Any]
    strength: str = "refuse"
    message: str = ""
    # The subject, beside its category: one trait, a name prefix, or a catalogue
    # type; none of them for every trait of the category.
    name: str | None = None
    name_prefix: str | None = None
    kind: str | None = None
    step: str | None = None
    splat: str = "vampire"
    # Its id, once saved; the key the engine knows it by is made from it.
    id: str = "draft"


def key_of(check_id: object) -> str:
    return f"{KEY_PREFIX}{check_id}"


def is_house_check(key: str) -> bool:
    return key.startswith(KEY_PREFIX)


def to_check(data: HouseCheckData, troupe_name: str) -> CheckData:
    """The engine's check for a house check, with the troupe's name as its page."""
    condition: dict[str, Any] = dict(data.condition)
    if data.kind is not None:
        of_kind = {"kind": [data.kind]}
        condition = (
            {"any_of": [{"not": of_kind}, condition]}
            if data.mode == "requires"
            else {**of_kind, "any_of": [condition]}
        )
    raw: dict[str, Any] = {
        "key": key_of(data.id),
        "category": data.category,
        data.mode: condition,
        "strength": data.strength,
        "message": data.message,
        "page": house_page(troupe_name),
    }
    if data.name is not None:
        raw["name"] = data.name
    if data.name_prefix:
        raw["name_prefix"] = data.name_prefix
    if data.step is not None:
        raw["step"] = data.step
    return check_from_dict(raw)


# --- checking one ----------------------------------------------------------------


def names_list(value: Any, what: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(n, str) and n for n in cast(list[Any], value))
    ):
        raise HouseCheckProblem(f"Choose at least one {what}.")
    return cast(list[str], value)


def number(value: Any, low: int, high: int, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise HouseCheckProblem(f"{what} is {low} to {high}.")
    return value


class Checker:
    """Checks a house check against a rule set: its subject, its condition's shape
    and the traits it names."""

    def __init__(self, rule_set: RuleSetData) -> None:
        self.rule_set = rule_set
        self.clans = {n for c, n in rule_set.traits if c == "clan"}
        self.families = {n.split(":")[0].strip() for n in self.clans}
        # The subject's category, for the names a `self` block lists.
        self.category = ""

    def trait(self, wanted: Any) -> None:
        if not isinstance(wanted, Mapping):
            raise HouseCheckProblem("Choose the trait.")
        trait = cast(Mapping[str, Any], wanted)
        if set(trait) - {"category", "name", "rating"}:
            raise HouseCheckProblem("A trait is a kind, a name and a rating.")
        category = self.rule_set.categories.get(trait.get("category", ""))
        name = trait.get("name")
        if category is None or not isinstance(name, str) or not name:
            raise HouseCheckProblem("Choose the trait.")
        if (category.key, name) not in self.rule_set.traits:
            raise HouseCheckProblem(f"{name} is not one of the {category.name.lower()}.")
        if "rating" in trait:
            number(trait["rating"], 1, category.max_rating or 10, f"The rating of {name}")

    def condition(self, condition: Any, depth: int = 0) -> int:
        """Check a condition's shape; the number of blocks in it."""
        if depth > DEPTH:
            raise HouseCheckProblem("The condition is nested too deeply.")
        if not isinstance(condition, Mapping) or not condition:
            raise HouseCheckProblem("Add at least one block to the condition.")
        blocks = 0
        for key, test in cast(Mapping[str, Any], condition).items():
            blocks += 1
            if key == "clan":
                unknown = [n for n in names_list(test, "clan") if n not in self.clans]
                if unknown:
                    raise HouseCheckProblem(f"{', '.join(unknown)}: no such clan in these rules.")
            elif key == "clan_family":
                unknown = [n for n in names_list(test, "clan") if n not in self.families]
                if unknown:
                    raise HouseCheckProblem(f"{', '.join(unknown)}: no such clan in these rules.")
            elif key == "has":
                self.trait(test)
            elif key == "has_all":
                if not isinstance(test, list) or not test:
                    raise HouseCheckProblem("Choose the traits.")
                for t in cast(list[Any], test):
                    self.trait(t)
            elif key == "generation":
                if not isinstance(test, Mapping) or not test or set(test) - {"gte", "lte"}:
                    raise HouseCheckProblem("Say the Generation it is at least or at most.")
                for value in cast(Mapping[str, Any], test).values():
                    number(value, 1, 5, "Generation")
            elif key == "finished":
                if test is not True:
                    raise HouseCheckProblem("“Creation is finished” is yes or no.")
            elif key == "copies":
                if not isinstance(test, Mapping) or set(test) != {"gte"}:
                    raise HouseCheckProblem("Say how many times it is held.")
                number(cast(Mapping[str, Any], test)["gte"], 2, 10, "How many times")
            elif key == "self":
                if not isinstance(test, Mapping) or set(test) != {"names"}:
                    raise HouseCheckProblem("Choose the traits it is one of.")
                names = names_list(cast(Mapping[str, Any], test)["names"], "trait")
                unknown = [n for n in names if (self.category, n) not in self.rule_set.traits]
                if unknown:
                    raise HouseCheckProblem(f"{', '.join(unknown)}: not what the check is about.")
            elif key == "not":
                blocks += self.condition(test, depth + 1)
            elif key == "any_of":
                if not isinstance(test, list) or len(cast(list[Any], test)) < 2:
                    raise HouseCheckProblem("“Any of” needs at least two blocks.")
                for c in cast(list[Any], test):
                    blocks += self.condition(c, depth + 1)
            else:
                raise HouseCheckProblem(f"A house check cannot use {key!r}.")
        if blocks > SIZE:
            raise HouseCheckProblem("The condition has too many blocks.")
        return blocks

    def check(self, data: HouseCheckData) -> None:
        category = self.rule_set.categories.get(data.category)
        if category is None:
            raise HouseCheckProblem("Choose what the check is about.")
        if data.mode not in MODES:
            raise HouseCheckProblem("Say whether it requires or forbids the condition.")
        if data.strength not in STRENGTHS:
            raise HouseCheckProblem("Choose how strictly it holds.")
        if not data.message.strip():
            raise HouseCheckProblem("Write the message the player sees.")
        subjects = [s for s in (data.name, data.name_prefix, data.kind) if s is not None]
        if len(subjects) > 1:
            raise HouseCheckProblem("A check is about one trait, a name prefix or a type.")
        if data.name is not None and (data.category, data.name) not in self.rule_set.traits:
            raise HouseCheckProblem(f"{data.name} is not one of the {category.name.lower()}.")
        if data.kind is not None and not any(
            c == data.category and t.properties.get("type") == data.kind
            for (c, _), t in self.rule_set.traits.items()
        ):
            raise HouseCheckProblem(f"No {category.name.lower()} are of the type {data.kind}.")
        if data.step is not None and (
            data.step not in self.rule_set.categories or data.strength != "complete"
        ):
            raise HouseCheckProblem("Only a check needed to finish creation can name a step.")
        self.category = data.category
        self.condition(data.condition)
        try:
            check = to_check(data, "")
            for condition in (check.requires, check.forbids):
                if condition:
                    validate_condition(condition, set(self.rule_set.traits))
            # Run once on an empty sheet, as the engine will on every change.
            breaks(check, [], SheetTrait(data.category, data.name or "", 1))
        except (ValueError, KeyError, TypeError) as error:
            raise HouseCheckProblem(f"The rules cannot use this: {error}.") from error


def check_house_check(data: HouseCheckData, rule_set: RuleSetData) -> None:
    """Refuse a house check the rule set cannot run, saying why."""
    Checker(rule_set).check(data)


# --- in words ----------------------------------------------------------------------


def either(names: Sequence[str], word: str = "or") -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} {word} {names[-1]}"


def held(trait: Mapping[str, Any]) -> str:
    rating = trait.get("rating")
    return f"{trait['name']} {rating} or more" if rating else str(trait["name"])


def phrase(condition: Mapping[str, Any]) -> str:
    """A condition in plain words: "the clan is Nagaraja and Generation 5 or more"."""
    return either([part(k, v) for k, v in condition.items()], "and")


def part(key: str, test: Any) -> str:
    if key == "clan":
        return f"the clan is {either(test)}"
    if key == "clan_family":
        their = "its" if len(test) == 1 else "their"
        return f"the clan is {either(test)} or one of {their} bloodlines"
    if key == "has":
        return f"holds {held(test)}"
    if key == "has_all":
        return f"holds {either([held(t) for t in test], 'and')}"
    if key == "generation":
        return (
            conditions.describe({"generation": test}, {"generation": "Generation {}"})
            or "Generation"
        )
    if key == "finished":
        return "creation is finished"
    if key == "copies":
        return conditions.describe({"copies": test}, {"copies": "held {} times"}) or "held twice"
    if key == "self":
        return f"it is {either(test['names'])}"
    if key == "not":
        return negated(test)
    if key == "any_of":
        return "either " + either([phrase(c) for c in test])
    return key


def negated(condition: Mapping[str, Any]) -> str:
    if len(condition) == 1:
        [(key, test)] = condition.items()
        if key == "clan":
            return f"the clan is not {either(test)}"
        if key == "clan_family":
            their = "its" if len(test) == 1 else "their"
            return f"the clan is not {either(test)} nor one of {their} bloodlines"
        if key == "has":
            return f"does not hold {held(test)}"
        if key == "finished":
            return "creation is not finished"
        if key == "self":
            return f"it is not {either(test['names'])}"
        if key == "not":
            return phrase(test)
    return f"not ({phrase(condition)})"


STRENGTH_WORDS = {
    "refuse": "refused",
    "complete": "to be put right before creation is finished",
    "review": "held for staff approval",
    "note": "noted for staff",
}


def subject_text(data: HouseCheckData, rule_set: RuleSetData) -> str:
    category = rule_set.categories.get(data.category)
    plural = category.name if category else data.category
    if data.name is not None:
        return data.name
    if data.kind is not None:
        return f"{data.kind} {plural.lower()}"
    if data.name_prefix:
        return f"{plural} starting “{data.name_prefix}”"
    return f"Any of the {plural.lower()}" if data.category != "clan" else "Any clan"


def describe(data: HouseCheckData, rule_set: RuleSetData) -> str:
    """The check in plain words: "Pliable Blood: refused once creation is finished."."""
    verb = STRENGTH_WORDS.get(data.strength, data.strength)
    if data.mode == "forbids" and dict(data.condition) == {"finished": True}:
        said = f"{verb} once creation is finished"
    else:
        said = f"{verb} {'unless' if data.mode == 'requires' else 'if'} {phrase(data.condition)}"
    return f"{subject_text(data, rule_set)}: {said}."
