"""The Stock Location catalogue (issue #325): location types, qualities, negative
qualities, Haven advantages and the troupe house options that change the book,
from `data/bns_met_vampire_locations.toml` (MET: VTM Vol. II Issue 1, pp. 117-133);
see the top of that file for its shape.

`played` gives the catalogue as one troupe plays it: the book's qualities, those of
its house options that are on (a house quality that `replaces` a book one takes its
place), and the troupe's own qualities. horatio.locations checks a location against
it.
"""

import tomllib
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal, get_args

from horatio.rules.files import DATA_DIR

LOCATIONS_FILE = DATA_DIR / "bns_met_vampire_locations.toml"
BOOK = "Vol. II Issue 1"
HAVEN_BOOK = "MET: VTM"

QualityKind = Literal["standard", "iconic", "supernatural", "elysium"]
QUALITY_KINDS: tuple[QualityKind, ...] = get_args(QualityKind)
KIND_NAMES: dict[str, str] = {
    "standard": "Standard",
    "iconic": "Iconic",
    "supernatural": "Supernatural",
    "elysium": "Elysium",
}
# The most of one negative quality a location takes, unless a quality raises it.
MOST_NEGATIVE = 3
# The control limit: five locations, and one more for each dot of these (p. 119).
BASE_CONTROL = 5
CONTROL_BACKGROUNDS = ("Retainers", "Kinfolk")


@dataclass(frozen=True)
class Suggestion:
    """One thing a quest for a quality should ask for (#326 builds the quest)."""

    trait: str = ""
    # Any one of these, in place of one `trait`.
    traits: tuple[str, ...] = ()
    # A power, as "Discipline: Power".
    power: str = ""
    # By the location's rating, lowest first.
    levels: tuple[int, ...] = ()
    detail: str = ""
    expend: bool = False
    alternative: str = ""
    # Anything that isn't a trait, power or level.
    text: str = ""


@dataclass(frozen=True)
class LocationType:
    key: str
    name: str
    # The most qualities per point of rating; 0 for none (a haven).
    per_rating: int
    iconic: bool
    quest: str
    text: str


@dataclass(frozen=True)
class HouseOption:
    key: str
    name: str
    text: str


@dataclass(frozen=True)
class Quality:
    name: str
    kind: QualityKind
    text: str
    page: str | None = None
    # The house option it comes with, and the book quality it stands in for.
    option: str | None = None
    replaces: str | None = None
    # What an instance can name, such as a Laboratory's specialisation.
    detail: str = ""
    repeatable: bool = False
    # Whether it counts toward the location's qualities (Derelict doesn't).
    counts: bool = True
    excludes: tuple[str, ...] = ()
    # The skill that gives it free on a Haven of its holder's.
    haven_free: str = ""
    suggested: tuple[Suggestion, ...] = ()
    # The troupe's own quality.
    house: bool = False


@dataclass(frozen=True)
class Limit:
    option: str
    quality: str
    min_rating: int | None = None
    per_qualities: int | None = None


@dataclass(frozen=True)
class Negative:
    name: str
    page: str
    removed: str
    # What each level does, from ×1.
    levels: tuple[str, ...]
    # A quality that lets it take one more level.
    raised_by: str = ""
    names_who: bool = False


@dataclass(frozen=True)
class HavenAdvantage:
    name: str
    page: str
    text: str
    # A skill needed to take it.
    needs: str = ""


@dataclass(frozen=True)
class Catalogue:
    types: Mapping[str, LocationType]
    options: Mapping[str, HouseOption]
    # Every quality in the file, house options' too, in its order.
    qualities: tuple[Quality, ...]
    limits: tuple[Limit, ...]
    negatives: Mapping[str, Negative]
    haven_advantages: Mapping[str, HavenAdvantage]
    pages: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LocationRules:
    """The catalogue as one troupe plays it."""

    catalogue: Catalogue
    # The house options that are on.
    options: frozenset[str]
    # By name, in the book's order then the troupe's own.
    qualities: Mapping[str, Quality]
    min_rating: Mapping[str, int]
    per_qualities: Mapping[str, int]

    @property
    def types(self) -> Mapping[str, LocationType]:
        return self.catalogue.types

    @property
    def negatives(self) -> Mapping[str, Negative]:
        return self.catalogue.negatives

    @property
    def haven_advantages(self) -> Mapping[str, HavenAdvantage]:
        return self.catalogue.haven_advantages

    def on(self, option: str) -> bool:
        return option in self.options


def suggestion_from(raw: Mapping[str, Any], where: str) -> Suggestion:
    known = {"trait", "traits", "power", "levels", "detail", "expend", "alternative", "text"}
    if extra := set(raw) - known:
        raise ValueError(f"{where}: unknown keys {sorted(extra)}")
    found = Suggestion(
        trait=raw.get("trait", ""),
        traits=tuple(raw.get("traits", ())),
        power=raw.get("power", ""),
        levels=tuple(raw.get("levels", ())),
        detail=raw.get("detail", ""),
        expend=raw.get("expend", False),
        alternative=raw.get("alternative", ""),
        text=raw.get("text", ""),
    )
    if sum(bool(x) for x in (found.trait, found.traits, found.power, found.text)) != 1:
        raise ValueError(f"{where}: name one of trait, traits, power or text")
    if found.text and (found.levels or found.detail or found.expend or found.alternative):
        raise ValueError(f"{where}: text stands alone")
    if found.power and ": " not in found.power:
        raise ValueError(f"{where}: a power is 'Discipline: Power'")
    if any(not 1 <= n <= 5 for n in found.levels) or list(found.levels) != sorted(found.levels):
        raise ValueError(f"{where}: levels go from 1 to 5, lowest first")
    return found


def quality_from(raw: Mapping[str, Any], *, house: bool = False) -> Quality:
    known = {
        "name",
        "kind",
        "page",
        "text",
        "option",
        "replaces",
        "detail",
        "repeatable",
        "counts",
        "excludes",
        "haven_free",
        "suggested",
    }
    name = raw.get("name", "")
    if extra := set(raw) - known:
        raise ValueError(f"quality {name!r}: unknown keys {sorted(extra)}")
    if not name or not raw.get("text"):
        raise ValueError(f"quality {name!r}: needs a name and text")
    if raw.get("kind") not in QUALITY_KINDS:
        raise ValueError(f"quality {name!r}: unknown kind {raw.get('kind')!r}")
    return Quality(
        name=name,
        kind=raw["kind"],
        text=raw["text"],
        page=raw.get("page"),
        option=raw.get("option"),
        replaces=raw.get("replaces"),
        detail=raw.get("detail", ""),
        repeatable=raw.get("repeatable", False),
        counts=raw.get("counts", True),
        excludes=tuple(raw.get("excludes", ())),
        haven_free=raw.get("haven_free", ""),
        suggested=tuple(
            suggestion_from(s, f"quality {name!r}, suggestion {n + 1}")
            for n, s in enumerate(raw.get("suggested", ()))
        ),
        house=house,
    )


def catalogue_from(raw: Mapping[str, Any]) -> Catalogue:
    """The catalogue in `raw`, as read from the file, checked."""
    types = {
        t["key"]: LocationType(
            key=t["key"],
            name=t["name"],
            per_rating=t["per_rating"],
            iconic=t.get("iconic", False),
            quest=t.get("quest", ""),
            text=t["text"],
        )
        for t in raw.get("types", ())
    }
    options = {o["key"]: HouseOption(o["key"], o["name"], o["text"]) for o in raw["options"]}
    qualities = tuple(quality_from(q) for q in raw["qualities"])
    limits = tuple(
        Limit(
            option=x["option"],
            quality=x["quality"],
            min_rating=x.get("min_rating"),
            per_qualities=x.get("per_qualities"),
        )
        for x in raw.get("limits", ())
    )
    negatives = {
        n["name"]: Negative(
            name=n["name"],
            page=n["page"],
            removed=n["removed"],
            levels=tuple(n["levels"]),
            raised_by=n.get("raised_by", ""),
            names_who=n.get("names_who", False),
        )
        for n in raw["negatives"]
    }
    advantages = {
        a["name"]: HavenAdvantage(a["name"], a["page"], a["text"], a.get("needs", ""))
        for a in raw["haven_advantages"]
    }
    pages = {k: v for k, v in raw.items() if k.endswith("_page") and isinstance(v, str)}
    catalogue = Catalogue(types, options, qualities, limits, negatives, advantages, pages)
    check(catalogue)
    return catalogue


def check(catalogue: Catalogue) -> None:
    """Refuse a catalogue whose parts don't fit together."""
    if set(catalogue.types) != {"standard", "prestige", "iconic", "haven"}:
        raise ValueError("locations: the types are standard, prestige, iconic and haven")
    book = {q.name for q in catalogue.qualities if q.option is None}
    seen: set[tuple[str, str | None]] = set()
    for q in catalogue.qualities:
        where = f"quality {q.name!r}"
        if (q.name, q.option) in seen:
            raise ValueError(f"{where}: twice")
        seen.add((q.name, q.option))
        if q.option is not None and q.option not in catalogue.options:
            raise ValueError(f"{where}: unknown option {q.option!r}")
        if q.option is None and q.page is None:
            raise ValueError(f"{where}: a book quality has its page")
        if q.replaces is not None and (q.option is None or q.replaces not in book):
            raise ValueError(f"{where}: replaces a book quality, under an option")
        if q.option is not None and q.replaces is None and q.name in book:
            raise ValueError(f"{where}: a house quality of a book quality's name replaces it")
        names = {x.name for x in catalogue.qualities}
        for other in q.excludes:
            if other not in names:
                raise ValueError(f"{where}: excludes unknown quality {other!r}")
    names = {q.name for q in catalogue.qualities}
    for limit in catalogue.limits:
        if limit.option not in catalogue.options or limit.quality not in names:
            raise ValueError(f"limit on {limit.quality!r}: unknown option or quality")
        if (limit.min_rating is None) == (limit.per_qualities is None):
            raise ValueError(f"limit on {limit.quality!r}: one of min_rating, per_qualities")
    for n in catalogue.negatives.values():
        if len(n.levels) != MOST_NEGATIVE:
            raise ValueError(f"negative {n.name!r}: one text for each of its three levels")
        if n.raised_by and n.raised_by not in book:
            raise ValueError(f"negative {n.name!r}: raised by unknown quality {n.raised_by!r}")


@cache
def load_catalogue(path: Path = LOCATIONS_FILE) -> Catalogue:
    with path.open("rb") as f:
        return catalogue_from(tomllib.load(f))


def played(
    catalogue: Catalogue, off: Collection[str], own: Iterable[Quality] = ()
) -> LocationRules:
    """The catalogue with the house options not in `off`, and the troupe's `own`
    qualities after the book's."""
    on = frozenset(k for k in catalogue.options if k not in off)
    replaced = {q.replaces for q in catalogue.qualities if q.option in on and q.replaces}
    qualities: dict[str, Quality] = {}
    for q in catalogue.qualities:
        if (q.option is None and q.name not in replaced) or q.option in on:
            qualities[q.name] = q
    for q in own:
        qualities.setdefault(q.name, q)
    limits = [x for x in catalogue.limits if x.option in on]
    return LocationRules(
        catalogue=catalogue,
        options=on,
        qualities=qualities,
        min_rating={x.quality: x.min_rating for x in limits if x.min_rating is not None},
        per_qualities={x.quality: x.per_qualities for x in limits if x.per_qualities is not None},
    )


def most_qualities(rules: LocationRules, kind: str, rating: int) -> int:
    """How many qualities a location of `kind` and `rating` takes (p. 121)."""
    return rules.types[kind].per_rating * rating


def most_of(rules: LocationRules, name: str, limit: int) -> int:
    """How many times a location whose limit is `limit` can have `name`: once, or
    one for each `per_qualities` it can have, under a house option."""
    per = rules.per_qualities.get(name)
    if per is not None:
        return max(1, limit // per)
    return 1


def elysium_qualities(years: int) -> int:
    """How many Elysium qualities an Elysium unviolated for `years` has: one, a
    second after a decade, and one more each century (p. 131)."""
    return 1 + (years >= 10) + years // 100


def most_negative(rules: LocationRules, name: str, qualities: Collection[str]) -> int:
    """The most levels of negative `name` a location with `qualities` takes: three,
    or four where a quality ignores its first (Sturdy, Public Property)."""
    raised = rules.negatives[name].raised_by
    return MOST_NEGATIVE + (1 if raised and raised in qualities else 0)
