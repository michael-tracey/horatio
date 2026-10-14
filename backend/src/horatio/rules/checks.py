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
    count = { category, name_prefix?, gte }
                                    how many traits the sheet holds in a category
                                    (whose names start with `name_prefix`)
    parent = { category, rating }   the trait named before the subject's ":" (an
                                    elder power's discipline) is held at `rating`
    self = { names?, rating?, has_detail? }
                                    the subject itself: one of these names, its
                                    rating, whether it has a detail
    copies = { gte = 2 }            how many times the sheet holds the subject's
                                    trait (with different details)
    in_clan = true                  the subject is one of the character's in-clan
                                    disciplines
    accepted = true                 a home troupe has accepted the character
    any_of = [ {...}, {...} ]       any of these conditions
    not = { ... }                   the condition does not hold

A check's strength says what happens when a change breaks it: "refuse" stops
the change; "complete" lets it be while the character is being built, but
creation cannot be finished until it holds; "review" lets it through once the
character has a home troupe, waiting on that troupe's approval (and freely
before, as acceptance reviews the whole sheet); "note" only shows on the sheet.
A troupe can change any check's strength, or switch it off.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from horatio.rules.conditions import OPERATORS
from horatio.rules.model import SheetTrait

Strength = Literal["refuse", "complete", "review", "note"]
Condition = Mapping[str, Any]

CONDITION_KEYS = frozenset(
    {"clan", "clan_family", "has", "has_any", "has_all", "generation", "on_path", "count", "parent",
     "self", "copies", "in_clan", "accepted", "any_of", "not"}
)  # fmt: skip


@dataclass(frozen=True)
class Context:
    """What checks may know beyond the sheet itself."""

    # A home troupe has accepted the character.
    accepted: bool = False
    # The character's in-clan disciplines, by name ("Celerity") or full name
    # ("Thaumaturgy: Path of Blood").
    in_clan: frozenset[str] = frozenset()


NO_CONTEXT = Context()


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

    def about(self, trait: SheetTrait) -> bool:
        if trait.category != self.category or (trait.rating == 0):
            return False
        if self.name is not None and trait.name != self.name:
            return False
        if self.name_prefix is not None and not trait.name.startswith(self.name_prefix):
            return False
        return self.detail is None or trait.detail == self.detail


@dataclass(frozen=True)
class Violation:
    check: CheckData
    subject: SheetTrait

    @property
    def message(self) -> str:
        page = f" (p. {self.check.page})" if self.check.page else ""
        return (self.check.message or f"{self.subject.full_name} is not allowed here.") + page

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.check.key, self.subject.category, self.subject.name, self.subject.detail)


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
            ok = compare(generation_of(sheet), test)
        elif key == "on_path":
            on_path = any(
                t.category == "paths" and t.name != "Humanity" and (t.rating or 0) > 0
                for t in sheet
            )
            ok = on_path == bool(test)
        elif key == "count":
            prefix = test.get("name_prefix", "")
            held = sum(
                1
                for t in sheet
                if t.category == test["category"] and t.name.startswith(prefix) and t.rating != 0
            )
            ok = compare(held, {k: v for k, v in test.items() if k in OPERATORS})
        elif key == "parent":
            parent = subject.name.split(":")[0].strip()
            ok = holds_trait(
                sheet, {"category": test["category"], "name": parent, "rating": test["rating"]}
            )
        elif key == "self":
            ok = (
                ("names" not in test or subject.name in test["names"])
                and ("rating" not in test or compare(subject.rating or 0, test["rating"]))
                and ("has_detail" not in test or bool(subject.detail) == test["has_detail"])
            )
        elif key == "copies":
            held = sum(
                1
                for t in sheet
                if t.category == subject.category and t.name == subject.name and t.rating != 0
            )
            ok = compare(held, test)
        elif key == "in_clan":
            ok = (subject.name in context.in_clan or subject.full_name in context.in_clan) == test
        elif key == "accepted":
            ok = context.accepted == test
        elif key == "any_of":
            ok = any(matches(c, sheet, subject, context) for c in test)
        elif key == "not":
            ok = not matches(test, sheet, subject, context)
        else:
            raise ValueError(f"unknown condition {key!r}")
        if not ok:
            return False
    return True


def violations(
    checks: Sequence[CheckData], sheet: Sequence[SheetTrait], context: Context = NO_CONTEXT
) -> list[Violation]:
    """Every check the sheet breaks, once per trait it is about."""
    found: list[Violation] = []
    for check in checks:
        for trait in sheet:
            if not check.about(trait):
                continue
            broken = (
                check.requires is not None and not matches(check.requires, sheet, trait, context)
            ) or (check.forbids is not None and matches(check.forbids, sheet, trait, context))
            if broken:
                found.append(Violation(check, trait))
    return found


def validate_condition(condition: Condition, known: set[tuple[str, str]]) -> None:
    """Refuse unknown condition keys, and traits the rule set does not have."""
    for key, test in condition.items():
        if key not in CONDITION_KEYS:
            raise ValueError(f"unknown condition {key!r}")
        wanted = [test] if key == "has" else test if key in ("has_any", "has_all") else []
        for t in wanted:
            if (t["category"], t["name"]) not in known:
                raise ValueError(f"a check names an unknown trait: {t['category']} {t['name']!r}")
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
    )


def check_to_dict(check: CheckData) -> dict[str, Any]:
    return {k: v for k, v in vars(check).items() if v is not None and v != ""}
