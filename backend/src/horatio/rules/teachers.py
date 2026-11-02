"""A troupe's teacher rules (horatio.teaching): kinds of trait that need a teacher
in that troupe, beyond the discipline dots the book already has one for.

A rule says:

- **which traits:** a category, and in it some traits by name or the names starting
  with a prefix ("Lore:"); neither for the whole category;
- **for whom:** everyone, or a condition from the house checks' blocks
  (horatio.rules.house_checks), such as "Generation at least 3";
- **when:** once creation is finished (the default), or always;
- **what the teacher must hold:** the same trait at the rating being bought, or at
  a set rating;
- optionally, downtime actions the learning takes;
- optionally, Willpower the teacher spends, and how many games they attend before
  it returns.

Merits and flaws are left out: once a character is accepted, every change to them
is asked of the troupe's staff already (horatio.merit_requests). So are kinds of
trait with no rating to buy (a clan, a sect) and those worked out from the sheet.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from horatio.rules.checks import Context, matches
from horatio.rules.house_checks import Checker, HouseCheckProblem, either, phrase
from horatio.rules.model import RuleSetData, SheetTrait

Holds = Literal["same", "rating"]
# Kinds of trait no teacher rule can be about: every change to them is asked of
# staff already once the character is accepted.
NOT_TAUGHT = frozenset({"merits", "flaws"})
MOST_ACTIONS = 5
MOST_WILLPOWER = 5
MOST_GAMES = 12


class TeacherRuleProblem(ValueError):
    """Why a teacher rule cannot be used, in words for the storyteller."""


@dataclass(frozen=True)
class TeacherRuleData:
    """A teacher rule as staff make it, and as the database keeps it."""

    category: str
    names: tuple[str, ...] = ()
    name_prefix: str | None = None
    # None: everyone.
    condition: Mapping[str, Any] | None = None
    # False: only once creation is finished.
    always: bool = False
    holds: Holds = "same"
    rating: int | None = None
    actions: int = 0
    willpower: int = 0
    games: int = 0
    splat: str = "vampire"
    id: str = "draft"

    def about(self, category: str, name: str) -> bool:
        """Whether the rule is about this trait."""
        if category != self.category:
            return False
        if self.names and name not in self.names:
            return False
        return not self.name_prefix or name.startswith(self.name_prefix)

    def needed(self, rating: int) -> int:
        """The rating the teacher must hold to teach the trait at `rating`."""
        return self.rating or 1 if self.holds == "rating" else max(rating, 1)

    def applies(self, sheet: Sequence[SheetTrait], subject: SheetTrait, context: Context) -> bool:
        """Whether the rule asks a teacher of this character for `subject` now: its
        "when" and its "for whom"."""
        if not self.always and not context.finished:
            return False
        return self.condition is None or matches(self.condition, sheet, subject, context)


def first_applying(
    rules: Sequence[TeacherRuleData],
    sheet: Sequence[SheetTrait],
    subject: SheetTrait,
    context: Context,
) -> TeacherRuleData | None:
    """The first rule, oldest first, that asks a teacher for `subject`."""
    return next(
        (
            r
            for r in rules
            if r.about(subject.category, subject.name) and r.applies(sheet, subject, context)
        ),
        None,
    )


def check_rule(data: TeacherRuleData, rule_set: RuleSetData) -> None:
    """Refuse a teacher rule the rule set cannot use, saying why."""
    category = rule_set.categories.get(data.category)
    if category is None or category.derived or not category.rated:
        raise TeacherRuleProblem("Choose a kind of trait bought in dots.")
    if data.category in NOT_TAUGHT:
        raise TeacherRuleProblem(
            "Merits and flaws are asked of staff already once a character is accepted."
        )
    if data.names and data.name_prefix:
        raise TeacherRuleProblem("A rule is about some traits by name, or a name prefix.")
    unknown = [n for n in data.names if (data.category, n) not in rule_set.traits]
    if unknown:
        raise TeacherRuleProblem(f"{', '.join(unknown)}: not one of the {category.name.lower()}.")
    if data.name_prefix and not any(
        c == data.category and n.startswith(data.name_prefix) for c, n in rule_set.traits
    ):
        raise TeacherRuleProblem(f"No {category.name.lower()} start “{data.name_prefix}”.")
    if data.holds not in ("same", "rating"):
        raise TeacherRuleProblem("Say what the teacher must hold.")
    top = category.max_rating or 10
    if data.holds == "rating" and (data.rating is None or not 1 <= data.rating <= top):
        raise TeacherRuleProblem(f"The teacher's rating is 1 to {top}.")
    if not 0 <= data.actions <= MOST_ACTIONS:
        raise TeacherRuleProblem(f"Downtime actions are 0 to {MOST_ACTIONS}.")
    if not 0 <= data.willpower <= MOST_WILLPOWER:
        raise TeacherRuleProblem(f"The teacher's Willpower is 0 to {MOST_WILLPOWER}.")
    if data.willpower and not 1 <= data.games <= MOST_GAMES:
        raise TeacherRuleProblem(f"The Willpower returns after 1 to {MOST_GAMES} games.")
    if data.condition is not None:
        checker = Checker(rule_set)
        checker.category = data.category
        try:
            checker.condition(data.condition)
        except HouseCheckProblem as problem:
            raise TeacherRuleProblem(str(problem)) from problem
        try:
            # Run once on an empty sheet, as purchases will.
            subject = SheetTrait(data.category, data.names[0] if data.names else "", 1)
            matches(data.condition, [], subject)
        except (ValueError, KeyError, TypeError) as error:
            raise TeacherRuleProblem(f"The rules cannot use this: {error}.") from error


# --- in words ----------------------------------------------------------------------


def plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else many or one + 's'}"


def subject_text(data: TeacherRuleData, rule_set: RuleSetData) -> str:
    category = rule_set.categories.get(data.category)
    kind = category.name if category else data.category
    if data.names:
        return either(list(data.names))
    if data.name_prefix:
        return f"{kind} starting “{data.name_prefix}”"
    return kind


def teacher_text(data: TeacherRuleData) -> str:
    if data.holds == "rating":
        return f"a teacher who holds it at {data.rating} or more"
    return "a teacher who holds it at the rating learned"


def costs_text(data: TeacherRuleData) -> list[str]:
    found: list[str] = []
    if data.actions:
        found.append(plural(data.actions, "downtime action"))
    if data.willpower:
        found.append(
            f"{data.willpower} of the teacher's Willpower, back after {plural(data.games, 'game')}"
        )
    return found


def describe(data: TeacherRuleData, rule_set: RuleSetData) -> str:
    """The rule in plain words: "Lore Specialisations need a teacher who holds it at
    the rating learned and 1 downtime action, once creation is finished."."""
    needs = either([teacher_text(data), *costs_text(data)], "and")
    when = "" if data.always else ", once creation is finished"
    who = f", if {phrase(data.condition)}" if data.condition else ""
    return f"{subject_text(data, rule_set)} need {needs}{when}{who}."
