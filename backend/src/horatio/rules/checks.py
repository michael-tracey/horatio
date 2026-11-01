"""Checks: what a sheet may hold, beyond what it costs.

A check is about one trait (its subject) and either requires a condition while
the sheet holds it, or forbids one. Checks are data in the rule set, so a
troupe can change them; what each condition means stays here.

Condition vocabulary (every key in one table must hold):

    clan = ["Brujah"]               the clan is exactly one of these
    clan_family = ["Toreador"]      the clan is one of these or one of its bloodlines
    has = { category, name, detail?, rating? }
                                    the sheet holds that trait (at least `rating`)
    has_any = [ {...}, {...} ]      the sheet holds any of these
    has_all = [ {...}, {...} ]      the sheet holds all of these
    generation = { gte = 3 }        the Generation background's rating
    on_path = true                  the character follows a Path other than Humanity
    count = { category, name_prefix?, names?, gte }
                                    how many traits the sheet holds in a category
                                    (whose names start with `name_prefix`, or are
                                    among `names`)
    one_below = { category, name_prefix? }
                                    the sheet holds a trait of that kind rated one
                                    less than the subject (a level 2 ritual needs a
                                    level 1 one, p. 202)
    parent = { category, rating }   the trait named before the subject's ":" (an
                                    elder power's discipline) is held at `rating`
    self = { names?, name_prefix?, rating?, has_detail?, given?, detail_without_field? }
                                    the subject itself: one of these names, a name
                                    starting with `name_prefix`, its rating,
                                    whether it has a detail, whether another trait
                                    gives it (SheetTrait.granted), and whether its
                                    detail names one of these skills without the
                                    field after it ("Performance", not
                                    "Performance: Singing")
    kind = ["Clan", "Morality"]     the subject's catalogue type is one of these
    tagged = "vampire_only"         the subject's catalogue `tags` include this one
    dots = { category, name_prefix?, gt }
                                    the dots the sheet holds in a category (whose
                                    names start with `name_prefix`), added up
    domitor_clan = true             the clan is the linked domitor's (a ghoul's,
                                    horatio.domitors); true with none linked
    domitor_has = true              the linked domitor holds the subject at its
                                    rating or more (a ghoul's discipline is one of
                                    its domitor's powers); true with none linked
    copies = { gte = 2 }            how many times the sheet holds the subject's
                                    trait (with different details), leaving out
                                    copies another trait gives (SheetTrait.granted)
    in_clan = true                  the subject is one of the character's in-clan
                                    disciplines
    detail_in_clan = true           the subject's detail names one of the character's
                                    native in-clan disciplines (Inept's discipline)
    accepted = true                 a home troupe has accepted the character
    finished = true                 the character's creation is finished
    npc = true                      the character is an NPC, built by staff
    more_than_dots = { count = { category, name_prefix }, dots = { category, name_prefix },
                       per_dot? }
                                    the sheet holds more traits of the first kind
                                    than it has dots of the second (rituals against
                                    Thaumaturgy), leaving out those another trait
                                    gives (Chosen of Cappadocius' specialisations)
    above_in_clan = { category, name_prefix }
                                    the subject is rated above every in-clan trait
                                    of that kind the sheet holds, or the primary
                                    path the player named (a path of Thaumaturgy
                                    above the primary path)
    same_value = { kind, also?, except_prefix?, together? }
                                    the sheet holds another trait of the subject's
                                    category and `kind` (its catalogue type, or one
                                    of the names in `also`) at the subject's rating,
                                    the subject being of that kind too: two clan
                                    merits of one value. Names starting with
                                    `except_prefix` never count, nor pairs listed in
                                    `together` ([[a, b], ...]). A check's message can
                                    name the other trait as {other}. A merit another
                                    trait gives never counts.
    excess_over_generation = { category, above }
                                    the dots rated above `above`, added up across
                                    the sheet's traits in that category, are more
                                    than the Generation rating (attributes: p. 102)
    any_of = [ {...}, {...} ]       any of these conditions
    not = { ... }                   the condition does not hold

A check's strength says what happens when a change breaks it: "refuse" stops
the change; "complete" lets it be while the character is being built, but
creation cannot be finished until it holds; "review" lets it through once the
character has a home troupe, waiting on that troupe's approval (and freely
before, as acceptance reviews the whole sheet); "note" only shows on the sheet.
A troupe can change any check's strength, or switch it off.

A check's message can name its subject as {name}: "{name} is not in-clan".

A "complete" check can also name a creation `step`, the category whose picks
must meet it: the wizard does not move on from that step until it holds (a
vampire's Generation, on Backgrounds).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Literal, cast

from horatio.rules.conditions import OPERATORS
from horatio.rules.conditions import describe as describe_facts
from horatio.rules.model import SheetTrait

Strength = Literal["refuse", "complete", "review", "note"]
Condition = Mapping[str, Any]

CONDITION_KEYS = frozenset(
    {"clan", "clan_family", "has", "has_any", "has_all", "generation", "on_path", "count",
     "one_below", "parent", "self", "copies", "in_clan", "detail_in_clan", "accepted",
     "finished", "npc", "more_than_dots",
     "above_in_clan", "same_value", "excess_over_generation", "any_of", "not",
     "kind", "tagged", "dots", "domitor_clan", "domitor_has"}
)  # fmt: skip


@dataclass(frozen=True)
class Context:
    """What checks may know beyond the sheet itself."""

    # A home troupe has accepted the character.
    accepted: bool = False
    # The character's creation is finished.
    finished: bool = False
    # The character is an NPC, which staff build as they like (horatio.npcs).
    npc: bool = False
    # The character's in-clan disciplines, by name ("Celerity") or full name
    # ("Thaumaturgy: Path of Blood").
    in_clan: frozenset[str] = frozenset()
    # Truly native only: in_clan without the paths a merit prices as in-clan.
    native: frozenset[str] = frozenset()
    # The primary paths: the ones the player named, else the clan's in-clan path.
    primary: frozenset[str] = frozenset()
    # Each trait's catalogue type, such as "Clan" for a clan merit.
    kinds: Mapping[tuple[str, str], str] = field(default_factory=dict[tuple[str, str], str])
    # Each trait's catalogue tags, such as "vampire_only".
    tags: Mapping[tuple[str, str], frozenset[str]] = field(
        default_factory=dict[tuple[str, str], frozenset[str]]
    )
    # A ghoul's linked domitor (horatio.domitors): its clan, and the rating it holds
    # each discipline at, by full name. None with no domitor linked.
    domitor_clan: str | None = None
    domitor_powers: Mapping[str, int] | None = None
    # The character's splat has Generation (horatio.rules.splats). A ghoul's has
    # none: a condition on Generation never holds for it, and its attributes get no
    # bonus above 10.
    generation: bool = True


NO_CONTEXT = Context()

# The end of the key of a check derived from a merit's requirement (a clan merit
# only for that clan). A merit another trait gives is not held to it.
REQUIREMENT_KEY = "/requirement"


@dataclass(frozen=True)
class CheckData:
    # Stable within the rule set, e.g. "merits/Calm Heart/1"; house rules will name it.
    key: str
    # The subject: a trait, every trait in a category (name None), or every trait
    # whose name starts with `name_prefix` (an elder power's discipline).
    category: str
    name: str | None = None
    name_prefix: str | None = None
    detail: str | None = None
    requires: Condition | None = None
    forbids: Condition | None = None
    strength: Strength = "refuse"
    message: str = ""
    page: str | None = None
    # The creation step (a category's picks) that must meet a "complete" check.
    step: str | None = None

    def about(self, trait: SheetTrait) -> bool:
        if trait.category != self.category or (trait.rating == 0):
            return False
        if self.name is not None and trait.name != self.name:
            return False
        if self.name_prefix is not None and not trait.name.startswith(self.name_prefix):
            return False
        return self.detail is None or trait.detail == self.detail

    @cached_property
    def looks_at(self) -> frozenset[tuple[str, str | None]]:
        """The traits the check's conditions look at, as (category, name), with no
        name for a whole category: a technique's disciplines, Archaic's skills."""
        return frozenset(traits_in(self.requires) | traits_in(self.forbids))


# Conditions that look at a trait without naming it.
IMPLIED_TRAIT: dict[str, tuple[str, str | None]] = {
    "clan": ("clan", None),
    "clan_family": ("clan", None),
    "detail_in_clan": ("clan", None),
    "generation": ("backgrounds", "Generation"),
    "on_path": ("paths", None),
    "excess_over_generation": ("backgrounds", "Generation"),
    "domitor_clan": ("clan", None),
}


def traits_in(condition: Any) -> set[tuple[str, str | None]]:
    """Every trait named anywhere in a condition, or implied by it."""
    found: set[tuple[str, str | None]] = set()
    if isinstance(condition, Mapping):
        items = cast(Mapping[str, Any], condition)
        category, name = items.get("category"), items.get("name")
        if isinstance(category, str):
            found.add((category, name if isinstance(name, str) else None))
        for key, value in items.items():
            if key in IMPLIED_TRAIT:
                found.add(IMPLIED_TRAIT[key])
            found |= traits_in(value)
    elif isinstance(condition, list | tuple):
        for item in cast(Sequence[Any], condition):
            found |= traits_in(item)
    return found


@dataclass(frozen=True)
class Violation:
    check: CheckData
    subject: SheetTrait
    # The trait the subject clashes with, where the check names one (same_value).
    other: str = ""

    @property
    def message(self) -> str:
        page = f" ({page_text(self.check.page)})" if self.check.page else ""
        text = self.check.message or f"{self.subject.full_name} is not allowed here."
        return text.replace("{other}", self.other).replace("{name}", self.subject.full_name) + page

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.check.key, self.subject.category, self.subject.name, self.subject.detail)


# Where the V20 LARP SRD's pages are, for the rules taken from it rather than a book
# (Dark Thaumaturgy): their page reference is a link there.
SRD_PAGES = "https://www.oneworldofdarkness.com/srd-v20/"
SRD_NAME = "V20 LARP SRD"


def page_text(page: str) -> str:
    """A page reference as written: "p. 225" for the core book, the reference as
    given for a supplement ("Vol. 2, p. 98"), or the SRD's name for a link to one
    of its pages, as a message is plain text."""
    if page.startswith(SRD_PAGES):
        return SRD_NAME
    return f"p. {page}" if page[:1].isdigit() else page


def clan_of(sheet: Sequence[SheetTrait]) -> str | None:
    return next((t.name for t in sheet if t.category == "clan"), None)


def generation_of(sheet: Sequence[SheetTrait]) -> int:
    return next(
        (t.rating or 0 for t in sheet if t.category == "backgrounds" and t.name == "Generation"),
        0,
    )


def holds_trait(sheet: Sequence[SheetTrait], wanted: Mapping[str, Any]) -> bool:
    for t in sheet:
        if t.category != wanted["category"] or t.name != wanted["name"]:
            continue
        if "detail" in wanted and t.detail != wanted["detail"]:
            continue
        if t.rating is None or t.rating >= wanted.get("rating", 1):
            return True
    return False


def compare(value: Any, test: Any) -> bool:
    if isinstance(test, Mapping):
        return all(OPERATORS[op](value, operand) for op, operand in test.items())
    return bool(value == test)


def matches(
    condition: Condition,
    sheet: Sequence[SheetTrait],
    subject: SheetTrait,
    context: Context = NO_CONTEXT,
) -> bool:
    for key, test in condition.items():
        if key == "clan":
            ok = clan_of(sheet) in test
        elif key == "clan_family":
            clan = clan_of(sheet) or ""
            ok = any(clan == c or clan.startswith(f"{c}:") for c in test)
        elif key == "has":
            ok = holds_trait(sheet, test)
        elif key == "has_any":
            ok = any(holds_trait(sheet, t) for t in test)
        elif key == "has_all":
            ok = all(holds_trait(sheet, t) for t in test)
        elif key == "generation":
            ok = context.generation and compare(generation_of(sheet), test)
        elif key == "on_path":
            on_path = any(
                t.category == "paths" and t.name != "Humanity" and (t.rating or 0) > 0
                for t in sheet
            )
            ok = on_path == bool(test)
        elif key == "count":
            prefix = test.get("name_prefix", "")
            names = test.get("names")
            held = sum(
                1
                for t in sheet
                if t.category == test["category"]
                and t.name.startswith(prefix)
                and (names is None or t.name in names)
                and t.rating != 0
            )
            ok = compare(held, {k: v for k, v in test.items() if k in OPERATORS})
        elif key == "one_below":
            below = (subject.rating or 0) - 1
            ok = any(
                t.category == test["category"]
                and t.name.startswith(test.get("name_prefix", ""))
                and t.rating == below
                for t in sheet
            )
        elif key == "parent":
            parent = subject.name.split(":")[0].strip()
            ok = holds_trait(
                sheet, {"category": test["category"], "name": parent, "rating": test["rating"]}
            )
        elif key == "self":
            ok = (
                ("names" not in test or subject.name in test["names"])
                and ("name_prefix" not in test or subject.name.startswith(test["name_prefix"]))
                and ("rating" not in test or compare(subject.rating or 0, test["rating"]))
                and ("has_detail" not in test or bool(subject.detail) == test["has_detail"])
                and ("given" not in test or subject.granted == test["given"])
                and (
                    "detail_without_field" not in test
                    or without_field(subject.detail, test["detail_without_field"])
                )
            )
        elif key == "copies":
            held = sum(
                1
                for t in sheet
                if t.category == subject.category
                and t.name == subject.name
                and t.rating != 0
                and not t.granted
            )
            ok = compare(held, test)
        elif key == "in_clan":
            ok = (subject.name in context.in_clan or subject.full_name in context.in_clan) == test
        elif key == "detail_in_clan":
            ok = (subject.detail in context.native) == test
        elif key == "accepted":
            ok = context.accepted == test
        elif key == "finished":
            ok = context.finished == test
        elif key == "npc":
            ok = context.npc == test
        elif key == "more_than_dots":
            counted, dotted = test["count"], test["dots"]
            held = sum(
                1
                for t in sheet
                if t.category == counted["category"]
                and t.name.startswith(counted.get("name_prefix", ""))
                and t.rating != 0
                and not t.granted
            )
            dots = sum(
                t.rating or 0
                for t in sheet
                if t.category == dotted["category"]
                and t.name.startswith(dotted.get("name_prefix", ""))
            )
            ok = held > dots * test.get("per_dot", 1)
        elif key == "above_in_clan":
            primaries = [
                t.rating or 0
                for t in sheet
                if t.category == test["category"]
                and t.name.startswith(test.get("name_prefix", ""))
                and t.name in context.primary
                and t.name != subject.name
            ]
            ok = bool(primaries) and (subject.rating or 0) > max(primaries)
        elif key == "excess_over_generation":
            excess = sum(
                max((t.rating or 0) - test["above"], 0)
                for t in sheet
                if t.category == test["category"]
            )
            # Without a Generation background, a vampire is Generation 1 (as in pricing);
            # a splat without Generation has no bonus points at all.
            bonus = max(generation_of(sheet), 1) if context.generation else 0
            ok = excess > bonus
        elif key == "same_value":
            ok = clashing(test, sheet, subject, context) is not None
        elif key == "kind":
            ok = context.kinds.get((subject.category, subject.name)) in test
        elif key == "tagged":
            ok = test in context.tags.get((subject.category, subject.name), frozenset())
        elif key == "dots":
            dots = sum(
                t.rating or 0
                for t in sheet
                if t.category == test["category"] and t.name.startswith(test.get("name_prefix", ""))
            )
            ok = compare(dots, {k: v for k, v in test.items() if k in OPERATORS})
        elif key == "domitor_clan":
            ok = (context.domitor_clan is None or clan_of(sheet) == context.domitor_clan) == test
        elif key == "domitor_has":
            powers = context.domitor_powers
            held = (
                None
                if powers is None
                else max(powers.get(subject.full_name, 0), powers.get(subject.name, 0))
            )
            ok = (held is None or (subject.rating or 0) <= held) == test
        elif key == "any_of":
            ok = any(matches(c, sheet, subject, context) for c in test)
        elif key == "not":
            ok = not matches(test, sheet, subject, context)
        else:
            raise ValueError(f"unknown condition {key!r}")
        if not ok:
            return False
    return True


def clashing(
    test: Mapping[str, Any], sheet: Sequence[SheetTrait], subject: SheetTrait, context: Context
) -> SheetTrait | None:
    """For same_value: another held trait of the subject's kind at its rating, if any."""

    def counts(t: SheetTrait) -> bool:
        kind = context.kinds.get((t.category, t.name))
        return (kind == test["kind"] or t.name in test.get("also", ())) and not (
            "except_prefix" in test and t.name.startswith(test["except_prefix"])
        )

    if subject.granted or not counts(subject):
        return None
    allowed = [set(pair) for pair in test.get("together", ())]
    return next(
        (
            t
            for t in sheet
            if t.category == subject.category
            and t.name != subject.name
            and t.rating == subject.rating
            and t.rating != 0
            and not t.granted
            and counts(t)
            and {t.name, subject.name} not in allowed
        ),
        None,
    )


def breaks(
    check: CheckData, sheet: Sequence[SheetTrait], trait: SheetTrait, context: Context = NO_CONTEXT
) -> bool:
    """Whether `trait`, one the check is about, breaks it on this sheet."""
    return (check.requires is not None and not matches(check.requires, sheet, trait, context)) or (
        check.forbids is not None and matches(check.forbids, sheet, trait, context)
    )


def violations(
    checks: Sequence[CheckData], sheet: Sequence[SheetTrait], context: Context = NO_CONTEXT
) -> list[Violation]:
    """Every check the sheet breaks, once per trait it is about."""
    # Each check only looks at its own category's traits, or its own trait's where
    # it names one (the wizard asks this for every merit in the catalogue).
    by_category: dict[str, list[SheetTrait]] = {}
    by_name: dict[tuple[str, str], list[SheetTrait]] = {}
    for trait in sheet:
        by_category.setdefault(trait.category, []).append(trait)
        by_name.setdefault((trait.category, trait.name), []).append(trait)
    found: list[Violation] = []
    for check in checks:
        about = (
            by_category.get(check.category, ())
            if check.name is None
            else by_name.get((check.category, check.name), ())
        )
        for trait in about:
            if not check.about(trait) or (trait.granted and check.key.endswith(REQUIREMENT_KEY)):
                continue
            if breaks(check, sheet, trait, context):
                test = (check.forbids or {}).get("same_value")
                other = clashing(test, sheet, trait, context) if test else None
                found.append(Violation(check, trait, other.name if other else ""))
    return found


def without_field(detail: str, names: Sequence[str]) -> bool:
    """Whether a detail names one of these skills with no field after it: "Performance"
    or "Performance:", but not "Performance: Singing"."""
    name, _, field = detail.partition(":")
    return name.strip() in names and not field.strip()


def describe(condition: Condition) -> str:
    """A condition in plain words, for the commonest forms ("without Thin
    Blooded", "for Tremere"); anything else reads as "under a condition"."""
    parts: list[str] = []
    for key, test in condition.items():
        if key == "has":
            parts.append(f"with {test['name']}")
        elif key == "not" and set(test) == {"has"}:
            parts.append(f"without {test['has']['name']}")
        elif key in ("clan", "clan_family"):
            parts.append("for " + " or ".join(test))
        elif key == "generation":
            parts.append(
                describe_facts({"generation": test}, {"generation": "Generation background {}"})
                or ""
            )
        elif key == "any_of":
            parts.append(" or ".join(describe(c) for c in test))
        else:
            return "under a condition"
    return ", ".join(parts)


def validate_condition(condition: Condition, known: set[tuple[str, str]]) -> None:
    """Refuse unknown condition keys, and traits the rule set does not have."""
    for key, test in condition.items():
        if key not in CONDITION_KEYS:
            raise ValueError(f"unknown condition {key!r}")
        wanted = [test] if key == "has" else test if key in ("has_any", "has_all") else []
        for t in wanted:
            if (t["category"], t["name"]) not in known:
                raise ValueError(f"a check names an unknown trait: {t['category']} {t['name']!r}")
        if key == "same_value":
            named = [*test.get("also", ()), *(n for pair in test.get("together", ()) for n in pair)]
            for name in named:
                if not any(n == name for _, n in known):
                    raise ValueError(f"a check names an unknown trait: {name!r}")
        if key == "any_of":
            for c in test:
                validate_condition(c, known)
        if key == "not":
            validate_condition(test, known)


def check_from_dict(raw: Mapping[str, Any]) -> CheckData:
    return CheckData(
        key=raw["key"],
        category=raw["category"],
        name=raw.get("name"),
        name_prefix=raw.get("name_prefix"),
        detail=raw.get("detail"),
        requires=raw.get("requires"),
        forbids=raw.get("forbids"),
        strength=raw.get("strength", "refuse"),
        message=raw.get("message", ""),
        page=raw.get("page"),
        step=raw.get("step"),
    )


def check_to_dict(check: CheckData) -> dict[str, Any]:
    return {k: v for k, v in vars(check).items() if v is not None and v != ""}
