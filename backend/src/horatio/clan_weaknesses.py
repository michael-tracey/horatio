"""Clan weaknesses as a troupe plays them (issues #1127, #1197).

**Versions.** Where the books differ on a clan's weakness, the rules data keeps both:
`weakness`, Volume 2's, and `core_weakness`, the core book's, each a line in our own
words with its page. Volume 2 replaced the Tremere's (Vol. 2, p. 22); for the Brujah
it only reads the core book's otherwise (Lash Out, Vol. 2, p. 121). Each troupe
chooses which it plays. A clan plays its `weakness_default` (Volume 2's unless the
data says "core") until the troupe chooses the other: the Tremere play Volume 2's
and the Brujah the core book's, as each did before there was a choice. The troupe
keeps the clans it plays the other way (`Troupe.core_weaknesses` and
`Troupe.vol2_weaknesses`), and its rules carry the outcome
(`RuleSetData.weakness_books`), so whatever reads a troupe's rules plays its choice.
With no troupe there is no one weakness to show for such a clan: what is shown says
it varies by troupe and gives each, with its page.

**What a character carries** is `carried`, the one place that decides it (p. 42): a
bloodline's own weakness, or with none of its own its clan's; one marked
`weakness_adds` ("additional") as well as its clan's, and `weakness_also` another
clan's too (Angelis Ater, p. 72); a flaw that adds a weakness (`adds_weakness`:
Coldly Logical gives the True Brujah's, Vol. 2, p. 270); none for a Golconda Seeker
who took freedom from it as the merit's benefit, while their Humanity is 5 or more
(pp. 249-250); and none for a ghoul, who plays its domitor's for roleplay only
(p. 297).

**What a weakness does** is data on the clan too, `weakness_effects` (and
`core_weakness_effects` for the core book's version): the `pools`, `active` and `use`
shapes of the powers file, read by the Play View's reference (horatio.reference),
`notes`, and a `feeding_note`. Each is labelled with the weakness it comes from
("Brujah weakness"), so the player sees why a number moved. The rule set's
[[feeding_modifiers]] with category "clan" hold for a character carrying that
clan's weakness (horatio.rules.feeding), and checks and prices ask for one by name
(the `weakness` condition and fact: horatio.rules.checks, horatio.rules.splats).

Blood bonds follow the Tremere choice (horatio.bonds, #1145): Volume 2's holds a
Tremere regnant's vampire thrall at one drink, and the core book's counts a Tremere
thrall's first drink as two. Each drink keeps the weakness it was recorded under.
The Malkavian's lasting derangement keeps its Derangement trait at 1 or more on the
Play View (horatio.play).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Troupe, User
from horatio.rules.feeding import clan_family
from horatio.rules.model import RuleSetData, SheetTrait
from horatio.rules.splats import SPLATS
from horatio.rules.store import forget_rules, read_troupe_rules
from horatio.sheets import unprocessable

Book = Literal["vol2", "core"]
# What each is called, Volume 2's first.
BOOKS: dict[Book, str] = {"vol2": "Volume 2", "core": "Core book"}
# Golconda Seeker's benefit that frees the character of their clan weakness, kept as
# the merit's detail (core pp. 249-250). It holds while Humanity is 5 or more.
GOLCONDA_SEEKER = ("merits", "Golconda Seeker")
FREEDOM = "No clan weakness"
GOLCONDA_HUMANITY = 5


@dataclass(frozen=True)
class Weakness:
    """A clan's weakness in a line, the page it is on, and the book it is from."""

    text: str
    page: str | None
    book: Book

    @property
    def label(self) -> str:
        return BOOKS[self.book]


@dataclass(frozen=True)
class Carried:
    """A weakness a character carries: whose it is, the version played, what it does,
    and the trait it comes by where that isn't the character's own clan."""

    clan: str
    weakness: Weakness
    effects: Mapping[str, Any]
    via: str | None = None
    # The books differ on it, and this is the one the troupe these rules are for chose.
    chosen: bool = False

    @property
    def name(self) -> str:
        """What its effects are labelled: "Brujah weakness", "Ishtarri weakness"."""
        return f"{self.clan.split(': ', 1)[-1]} weakness"


def holding(rule_set: RuleSetData, clan: str) -> Mapping[str, Any]:
    """The properties a clan's or bloodline's weakness is in: its own, or for a
    bloodline with none of its own, its clan's."""
    found = rule_set.trait_properties("clan", clan)
    if "weakness" not in found:
        found = rule_set.trait_properties("clan", clan_family(clan))
    return found


def default(rule_set: RuleSetData, clan: str) -> Book:
    """The book a troupe plays the clan's weakness by until it chooses."""
    return "core" if holding(rule_set, clan).get("weakness_default") == "core" else "vol2"


def versions(rule_set: RuleSetData, clan: str) -> list[Weakness]:
    """Each weakness a troupe may play for the clan or bloodline: none, one, or for
    one the books differ on, its default first and then the other."""
    found = holding(rule_set, clan)
    if "weakness" not in found:
        return []
    page: str | None = found.get("weakness_page")
    if "core_weakness" not in found:
        # One weakness only, nothing to choose: the core book's, or a Volume 2
        # bloodline's.
        return [Weakness(found["weakness"], page, "core" if page and page[0].isdigit() else "vol2")]
    both = [
        Weakness(found["weakness"], page, "vol2"),
        Weakness(found["core_weakness"], found.get("core_weakness_page"), "core"),
    ]
    return both if default(rule_set, clan) == "vol2" else both[::-1]


def choosable(rule_set: RuleSetData) -> list[str]:
    """The clans, without their bloodlines, whose weakness a troupe chooses."""
    return sorted(
        name
        for (category, name), trait in rule_set.traits.items()
        if category == "clan" and ":" not in name and "core_weakness" in trait.properties
    )


def chosen(troupe: Troupe, clan: str, rule_set: RuleSetData) -> Book:
    """Which book's weakness the troupe plays for the clan or bloodline."""
    family = clan_family(clan)
    if family in troupe.core_weaknesses:
        return "core"
    if family in troupe.vol2_weaknesses:
        return "vol2"
    return default(rule_set, clan)


def books(rule_set: RuleSetData, troupe: Troupe) -> dict[str, Book]:
    """The book the troupe plays each clan's weakness by, where the books differ: what
    its rules carry (`RuleSetData.weakness_books`)."""
    return {clan: chosen(troupe, clan, rule_set) for clan in choosable(rule_set)}


def book_of(rule_set: RuleSetData, clan: str) -> Book:
    """The book the clan's weakness is played by under these rules: the troupe's
    choice, or with no troupe, its default."""
    found = rule_set.weakness_books.get(clan_family(clan))
    if found in BOOKS:
        return "core" if found == "core" else "vol2"
    return default(rule_set, clan)


def played(rule_set: RuleSetData, clan: str, troupe: Troupe | None) -> Weakness | None:
    """The clan's or bloodline's weakness as `troupe` plays it. None for none, or with
    no troupe where it varies by troupe (then show each of `versions`)."""
    found = versions(rule_set, clan)
    if len(found) <= 1:
        return found[0] if found else None
    if troupe is None:
        return None
    book = chosen(troupe, clan, rule_set)
    return next(w for w in found if w.book == book)


def own(rule_set: RuleSetData, clan: str) -> list[str]:
    """The clans and bloodlines whose weakness a clan or bloodline has (p. 42): its
    own, else its clan's; with an additional weakness its clan's too, and another
    clan's where it names one (Angelis Ater: the Baali's and the Lasombra's, p. 72)."""
    properties = rule_set.trait_properties("clan", clan)
    family = clan_family(clan)
    if "weakness" not in properties:
        return own(rule_set, family) if family != clan else []
    found = [clan]
    if properties.get("weakness_adds") and family != clan:
        found += own(rule_set, family)
    for other in properties.get("weakness_also", []):
        found += own(rule_set, other)
    return list(dict.fromkeys(found))


def freed(sheet: Sequence[SheetTrait]) -> bool:
    """A Golconda Seeker who took freedom from their clan weakness, while their
    Humanity is 5 or more (core pp. 249-250)."""
    seeker = any(
        (t.category, t.name) == GOLCONDA_SEEKER and t.detail == FREEDOM and t.rating != 0
        for t in sheet
    )
    humanity = max(
        (t.rating or 0 for t in sheet if (t.category, t.name) == ("paths", "Humanity")), default=0
    )
    return seeker and humanity >= GOLCONDA_HUMANITY


def carried(rule_set: RuleSetData, sheet: Sequence[SheetTrait]) -> list[Carried]:
    """Every clan weakness the character carries, with the version its troupe plays
    and what it does (see above). The one place this is decided."""
    if not SPLATS[rule_set.splat].weakness or freed(sheet):
        return []
    clan = next((t.name for t in sheet if t.category == "clan"), None)
    whose: dict[str, str | None] = dict.fromkeys(own(rule_set, clan) if clan else [])
    for t in sheet:
        added = rule_set.trait_properties(t.category, t.name).get("adds_weakness")
        if added and t.rating != 0:
            for name in own(rule_set, added):
                whose.setdefault(name, t.name)
    found: list[Carried] = []
    for name, via in whose.items():
        properties = rule_set.trait_properties("clan", name)
        book = book_of(rule_set, name)
        each = versions(rule_set, name)
        weakness = next((w for w in each if w.book == book), each[0])
        core = book == "core" and "core_weakness" in properties
        effects = properties.get("core_weakness_effects" if core else "weakness_effects", {})
        picked = len(each) > 1 and clan_family(name) in rule_set.weakness_books
        found.append(Carried(name, weakness, effects, via, picked))
    return found


def lifted(rule_set: RuleSetData, sheet: Sequence[SheetTrait]) -> bool:
    """Golconda Seeker frees the character of a weakness they would carry without it."""
    without = [t for t in sheet if (t.category, t.name) != GOLCONDA_SEEKER]
    return freed(sheet) and bool(carried(rule_set, without))


def carries(rule_set: RuleSetData, sheet: Sequence[SheetTrait]) -> frozenset[str]:
    """The clans and bloodlines whose weakness the character carries, by name: what
    the `weakness` check condition and price fact ask about. Worked out once a sheet."""
    return rule_set.remembered(
        ("clan weaknesses", tuple(sheet)),
        lambda: frozenset(c.clan for c in carried(rule_set, sheet)),
    )


def setting_text(clans: Sequence[str]) -> str:
    """The setting in words, for the log: the clans that play the core book's."""
    if not clans:
        return "Volume 2's for every clan"
    return f"the core book's for the {', '.join(clans)}; Volume 2's for the rest"


def set_core(db: Session, user: User, troupe: Troupe, clans: Sequence[str]) -> None:
    """Play the core book's weakness for these clans here, and Volume 2's for every
    other. Logged when it changes. What is shown changes at once, and so do the
    drinks of blood bonds recorded from now (horatio.bonds); no sheet changes."""
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    offered = choosable(rule_set)
    unknown = sorted(set(clans) - set(offered))
    if unknown:
        raise unprocessable(
            f"No other weakness to choose for: {', '.join(unknown)}."
            f" Only {', '.join(offered) or 'no clan'} has one."
        )
    core = sorted(c for c in set(clans) if default(rule_set, c) == "vol2")
    vol2 = sorted(c for c in offered if default(rule_set, c) == "core" and c not in clans)
    keep(db, user, troupe, rule_set, core, vol2)


def set_lists(
    db: Session, user: User, troupe: Troupe, core: Sequence[str], vol2: Sequence[str]
) -> None:
    """Set the troupe's two lists as an import of its settings carries them: the clans
    it plays by the core book's where Volume 2's is the default, and by Volume 2's
    where the core book's is. A clan in the wrong list is refused."""
    rule_set = read_troupe_rules(db, "vampire", troupe.id).rule_set
    offered = choosable(rule_set)
    wrong = sorted(
        {c for c in core if c not in offered or default(rule_set, c) != "vol2"}
        | {c for c in vol2 if c not in offered or default(rule_set, c) != "core"}
    )
    if wrong:
        raise unprocessable(f"No other weakness to choose for: {', '.join(wrong)}.")
    keep(db, user, troupe, rule_set, sorted(set(core)), sorted(set(vol2)))


def keep(
    db: Session,
    user: User,
    troupe: Troupe,
    rule_set: RuleSetData,
    core: list[str],
    vol2: list[str],
) -> None:
    """Keep the troupe's choice, logged as the clans that now play the core book's."""
    if core == sorted(troupe.core_weaknesses) and vol2 == sorted(troupe.vol2_weaknesses):
        return
    troupe.core_weaknesses = core
    troupe.vol2_weaknesses = vol2
    # The troupe's rules carry the choice (RuleSetData.weakness_books).
    forget_rules(db)
    played_core = [c for c in choosable(rule_set) if chosen(troupe, c, rule_set) == "core"]
    audit.record(
        db, user, "house.clan_weaknesses", troupe_id=troupe.id, setting=setting_text(played_core)
    )
