"""How many languages Linguistics gives, as a troupe plays it.

By the book each dot of Linguistics gives one language (p. 95), and Natural
Linguist two (p. 252): two checks on the Languages category say so, with
more_than_dots (horatio.rules.checks). A troupe can play a chart instead: the
accelerated one some troupes use, or its own figure for each rating. Natural
Linguist doubles whichever is used, unless the troupe says it does not.

The troupe's choice rewrites those two checks where its rules are put together
(horatio.rules.store), so creation, purchases, review and the sheet all follow.
The checks keep their keys, so a troupe's strength for them still applies. A
character who already holds more languages than a new chart allows keeps them,
and the sheet shows the broken check.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, cast

from horatio.rules.checks import CheckData

if TYPE_CHECKING:
    from horatio.models import Troupe

CATEGORY = "linguistics_specializations"
SKILL = "Linguistics"
MERIT = "Natural Linguist"

Mode = Literal["book", "accelerated", "custom"]
MODES: tuple[Mode, ...] = ("book", "accelerated", "custom")

# The accelerated chart, as Land of the Sky plays it: languages at Linguistics 1 to 7.
ACCELERATED = (1, 2, 4, 8, 16, 24, 32)

MODE_TEXT: dict[Mode, str] = {
    "book": "the book's",
    "accelerated": "the accelerated chart",
    "custom": "the troupe's own chart",
}


@dataclass(frozen=True)
class LanguageRule:
    """A troupe's setting: which chart, its own figures (kept while another chart is
    chosen, for going back to), and whether Natural Linguist doubles it."""

    mode: Mode = "book"
    custom: tuple[int, ...] = ()
    natural_doubles: bool = True

    @property
    def table(self) -> tuple[int, ...] | None:
        """Languages at each rating from 1, the last carrying on above; None for the
        book's one per dot."""
        if self.mode == "accelerated":
            return ACCELERATED
        if self.mode == "custom" and self.custom:
            return self.custom
        return None

    @property
    def is_book(self) -> bool:
        return self.table is None and self.natural_doubles

    def allowed(self, rating: int, natural: bool = False) -> int:
        """How many languages a character may hold at this rating of Linguistics."""
        table = self.table
        base = rating if table is None else (table[min(rating, len(table)) - 1] if rating else 0)
        return base * 2 if natural and self.natural_doubles else base

    def ratings(self, max_rating: int) -> list[int]:
        """The languages at each rating from 1 to `max_rating`, for showing."""
        return [self.allowed(r) for r in range(1, max_rating + 1)]


def rule_of(troupe: "Troupe | None") -> LanguageRule:
    """A troupe's setting; the book's for no troupe."""
    if troupe is None:
        return LanguageRule()
    return LanguageRule(
        mode=cast(Mode, troupe.languages),  # checked by the database
        custom=tuple(troupe.languages_table or ()),
        natural_doubles=troupe.natural_linguist_doubles,
    )


def counts_languages(check: CheckData) -> bool:
    """Whether a check limits languages by the dots of Linguistics."""
    test = (check.forbids or {}).get("more_than_dots")
    return check.category == CATEGORY and test is not None and test["count"]["category"] == CATEGORY


def chart_text(table: Sequence[int]) -> str:
    """A chart in words: "1, 2, 4 and 8 languages at Linguistics 1 to 4, and 8 above"."""
    shown = list(table)
    while len(shown) > 1 and shown[-1] == shown[-2]:
        shown.pop()
    numbers = (
        str(shown[0]) if len(shown) == 1 else f"{', '.join(map(str, shown[:-1]))} and {shown[-1]}"
    )
    word = "language" if shown == [1] else "languages"
    if len(shown) == 1:
        return f"{numbers} {word} at any rating of {SKILL}"
    return f"{numbers} {word} at {SKILL} 1 to {len(shown)}, and {shown[-1]} above"


def setting_text(rule: LanguageRule, capital: bool = False) -> str:
    """The setting in words, for the log and (with a capital) the House rules tab."""
    table = rule.table
    chart = f"one per dot of {SKILL}" if table is None else chart_text(table)
    natural = "doubles it" if rule.natural_doubles else "does not double it"
    text = f"{chart} ({MODE_TEXT[rule.mode]}); {MERIT} {natural}"
    return text[:1].upper() + text[1:] if capital else text


BOOK_TEXT = f"One per dot of {SKILL}; {MERIT} doubles it (pp. 95, 252)"


def applied(checks: Sequence[CheckData], rule: LanguageRule, page: str) -> tuple[CheckData, ...]:
    """The rule set's checks with the two on languages played by the troupe's
    setting; `page` is where the house rule's page reference goes."""
    if rule.is_book:
        return tuple(checks)
    table = rule.table
    found: list[CheckData] = []
    for check in checks:
        if not counts_languages(check):
            found.append(check)
            continue
        assert check.forbids is not None
        forbids: dict[str, Any] = dict(check.forbids)
        test = {k: v for k, v in forbids["more_than_dots"].items() if k not in ("per_dot", "table")}
        # The plain check leaves out Natural Linguist's holders; the other is theirs.
        natural = "not" not in forbids
        doubles = natural and rule.natural_doubles
        if table is None:
            # The book's one per dot, with Natural Linguist not doubling it.
            if not natural:
                found.append(check)
                continue
            test["per_dot"] = 1
            chart = "one per dot of Linguistics"
        else:
            test["table"] = [n * 2 for n in table] if doubles else list(table)
            chart = chart_text(test["table"])
        if not natural:
            message = f"This troupe's chart: {chart}."
        elif doubles:
            message = f"{MERIT} doubles the troupe's chart: {chart}."
        else:
            message = f"{MERIT} gives no more languages here: {chart}."
        forbids["more_than_dots"] = test
        found.append(replace(check, forbids=forbids, message=message, page=page))
    return tuple(found)
