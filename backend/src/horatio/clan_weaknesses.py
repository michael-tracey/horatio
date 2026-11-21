"""Clan weaknesses as a troupe plays them (issue #1127).

Volume 2 replaced the Tremere's weakness from the core book (Vol. 2, p. 22). The
rules data keeps both for such a clan: `weakness`, the later book's, and
`core_weakness`, the core book's, each a line in our own words with its page. Each
troupe chooses which it plays (`Troupe.core_weaknesses`: the clans it plays by the
core book's). A clan it leaves out plays the later book's, so a troupe made before
this kept Volume 2's. A bloodline with no weakness of its own has its clan's, and
so its clan's choice (MET: VtM p. 42).

With no troupe there is no one weakness to show for such a clan: what is shown
says it varies by troupe and gives each, with its page.

No rule Horatio runs uses a clan weakness yet. Blood bonds count drinks alike for
every clan (horatio.bonds), so neither Tremere weakness changes a bond; staff
apply it as they record drinks.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Troupe, User
from horatio.rules.feeding import clan_family
from horatio.rules.model import RuleSetData
from horatio.rules.store import read_troupe_rules
from horatio.sheets import unprocessable

Book = Literal["vol2", "core"]
# What each is called, the default first.
BOOKS: dict[Book, str] = {"vol2": "Volume 2", "core": "Core book"}


@dataclass(frozen=True)
class Weakness:
    """A clan's weakness in a line, the page it is on, and the book it is from."""

    text: str
    page: str | None
    book: Book

    @property
    def label(self) -> str:
        return BOOKS[self.book]


def holding(rule_set: RuleSetData, clan: str) -> Mapping[str, Any]:
    """The properties a clan's or bloodline's weakness is in: its own, or for a
    bloodline with none of its own, its clan's."""
    found = rule_set.trait_properties("clan", clan)
    if "weakness" not in found:
        found = rule_set.trait_properties("clan", clan_family(clan))
    return found


def versions(rule_set: RuleSetData, clan: str) -> list[Weakness]:
    """Each weakness a troupe may play for the clan or bloodline: none, one, or for
    one a later book replaced, the later book's and then the core book's."""
    found = holding(rule_set, clan)
    if "weakness" not in found:
        return []
    page: str | None = found.get("weakness_page")
    if "core_weakness" not in found:
        # One weakness only, nothing to choose: the core book's, or a Volume 2
        # bloodline's.
        return [Weakness(found["weakness"], page, "core" if page and page[0].isdigit() else "vol2")]
    return [
        Weakness(found["weakness"], page, "vol2"),
        Weakness(found["core_weakness"], found.get("core_weakness_page"), "core"),
    ]


def choosable(rule_set: RuleSetData) -> list[str]:
    """The clans, without their bloodlines, whose weakness a troupe chooses."""
    return sorted(
        name
        for (category, name), trait in rule_set.traits.items()
        if category == "clan" and ":" not in name and "core_weakness" in trait.properties
    )


def chosen(troupe: Troupe, clan: str) -> Book:
    """Which book's weakness the troupe plays for the clan or bloodline."""
    return "core" if clan_family(clan) in troupe.core_weaknesses else "vol2"


def played(rule_set: RuleSetData, clan: str, troupe: Troupe | None) -> Weakness | None:
    """The clan's or bloodline's weakness as `troupe` plays it. None for none, or with
    no troupe where it varies by troupe (then show each of `versions`)."""
    found = versions(rule_set, clan)
    if len(found) <= 1:
        return found[0] if found else None
    if troupe is None:
        return None
    book = chosen(troupe, clan)
    return next(w for w in found if w.book == book)


def setting_text(clans: Sequence[str]) -> str:
    """The setting in words, for the log: the clans that play the core book's."""
    if not clans:
        return "Volume 2's for every clan"
    return f"the core book's for the {', '.join(clans)}; Volume 2's for the rest"


def set_core(db: Session, user: User, troupe: Troupe, clans: Sequence[str]) -> None:
    """Play the core book's weakness for these clans here, and the later book's for
    every other. Logged when it changes. What is shown changes at once; no rule uses
    a weakness yet, so no sheet changes."""
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    offered = choosable(rule_set)
    unknown = sorted(set(clans) - set(offered))
    if unknown:
        raise unprocessable(
            f"No other weakness to choose for: {', '.join(unknown)}."
            f" Only {', '.join(offered) or 'no clan'} has one."
        )
    new = sorted(set(clans))
    if new == sorted(troupe.core_weaknesses):
        return
    troupe.core_weaknesses = new
    audit.record(db, user, "house.clan_weaknesses", troupe_id=troupe.id, setting=setting_text(new))
