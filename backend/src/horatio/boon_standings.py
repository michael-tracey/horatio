"""Boon standings (#691): where everyone stands in a troupe's boon ledger, worked out
live from the ledger (horatio.boons), as the registry spreadsheet's standings pages
had them as snapshots.

Each kind of boon has a weight, set per troupe (`weights_of`): Trivial 0.5, Minor 1,
Major 3, Blood 5 and Life 10 unless the troupe sets its own. A character's **net**
is the weight owed to them less the weight they owe.

`load` reads a troupe's ledger into plain rows (`Row`, `Who`); `compute` works out
every section from them and touches no database, so the statistics page (#702) and
anything else can reuse the sums on rows of its own. The troupe's staff read them
(`reader`), and so does its Harpy with the full ledger where the troupe allows it
(#749): for the Harpy, `load` reads who has left only as the court knows it
(horatio.court_knows), so their standings never say a player stopped.

**Scope.** "active", the default, leaves out every boon that involves someone
departed (dead or off-field, as horatio.boons counts them); "everyone" keeps them.
The totals always count the whole ledger. A party known only by name is in play as
far as Horatio knows, so stays in either scope.
"""

import statistics
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, boon_harpy, boons, court_knows, social_age, titles
from horatio.boon_harpy import Keeper
from horatio.models import Boon, Character, CharacterTitle, Troupe, User
from horatio.sheets import unprocessable

# What each kind weighs unless the troupe sets its own.
DEFAULT_WEIGHTS: dict[str, float] = {
    "trivial": 0.5,
    "minor": 1.0,
    "major": 3.0,
    "blood": 5.0,
    "life": 10.0,
}
HEAVIEST = 100.0
Scope = Literal["active", "everyone"]
# How many lines a "most" list keeps.
TOP = 10
# Open debt's age, in three-month bands up to three years, then one for older.
BANDS = 12


def weights_of(troupe: Troupe) -> dict[str, float]:
    """What each kind of boon weighs in the troupe: its own, else the default."""
    own = troupe.boon_weights or {}
    return {k: float(own.get(k, w)) for k, w in DEFAULT_WEIGHTS.items()}


def set_weights(db: Session, user: User, troupe: Troupe, weights: Mapping[str, float]) -> None:
    """Set what each kind weighs. Every kind must be named, more than 0 and at most
    100; the defaults themselves are kept as none set, so a later default applies."""
    if set(weights) != set(DEFAULT_WEIGHTS):
        raise unprocessable("Give a weight for each kind of boon.")
    for kind, weight in weights.items():
        if not 0 < weight <= HEAVIEST:
            raise unprocessable(
                f"A {boons.KINDS[kind]} boon must weigh more than 0 and at most {HEAVIEST:g}."
            )
    own = {k: float(w) for k, w in weights.items() if float(w) != DEFAULT_WEIGHTS[k]}
    if own == (troupe.boon_weights or {}):
        return
    before = weights_of(troupe)
    troupe.boon_weights = own
    after = weights_of(troupe)
    changed = ", ".join(
        f"{boons.KINDS[k]} {before[k]:g} → {after[k]:g}"
        for k in DEFAULT_WEIGHTS
        if before[k] != after[k]
    )
    audit.record(db, user, "boon.weights", troupe_id=troupe.id, changed=changed)


def reader(db: Session, user: User, troupe: Troupe) -> Keeper | None:
    """Who reads the troupe's standings, and as whom: its running staff (and the
    custodian), as for the ledger; or, where the troupe lets its Harpy read them
    (horatio.boon_harpy.reads_standings, #749), its Harpy with the full ledger and the
    Lesser Harpies who may see it (#689), following their Harpy's view. None for
    anyone else."""
    keeper = boon_harpy.keeper(db, user, troupe, "view")
    if keeper is None or keeper.staff:
        return keeper
    return keeper if boon_harpy.reads_standings(troupe) else None


def can_read(db: Session, user: User, troupe: Troupe) -> bool:
    return reader(db, user, troupe) is not None


# --- rows ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Who:
    """One side of a boon, as the standings group it: a character, or a name only."""

    key: str
    name: str
    character_id: uuid.UUID | None = None
    # Active, or why it retired (horatio.boons.standing); None for a name only.
    standing: str | None = None
    clan: str | None = None
    # Neonate, Ancilla or Elder as the troupe's roster shows it (horatio.social_age),
    # or what the character is instead ("Ghoul").
    age: str | None = None
    sect: str | None = None
    # The titles it holds in the troupe, in court order.
    titles: tuple[str, ...] = ()

    @property
    def departed(self) -> bool:
        return self.standing in boons.DEPARTED


@dataclass(frozen=True)
class Row:
    """A boon, as the standings need it."""

    debtor: str
    creditor: str
    kind: str
    # pending, registered or settled; a void boon is never a row.
    state: str
    made_on: date
    settled_how: str | None = None
    closed_on: date | None = None
    # When it went in the ledger, when it was closed, and the game it was registered
    # at, for the statistics (horatio.boon_statistics).
    entered_at: datetime | None = None
    closed_at: datetime | None = None
    game_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Ledger:
    """A troupe's ledger as the standings read it: its boons, everyone on them, and
    each title's place at court (lower first)."""

    rows: list[Row]
    people: dict[str, Who]
    court_order: dict[str, int] = field(default_factory=dict[str, int])


def name_key(name: str) -> str:
    return f"name:{name.strip().casefold()}"


def load(db: Session, troupe: Troupe, court: Collection[uuid.UUID] | None = None) -> Ledger:
    """The troupe's ledger as rows, everyone on them, and its court order. With
    `court`, for a Harpy, each character's standing as the court knows it
    (horatio.court_knows): gone only if the Who's Who lists it, and why only when
    that says something in game."""
    found = list(db.scalars(select(Boon).where(Boon.troupe_id == troupe.id, Boon.state != "void")))
    ids = {c for b in found for c in (b.debtor_id, b.creditor_id) if c is not None}
    characters = {c.id: c for c in db.scalars(select(Character).where(Character.id.in_(ids)))}
    ages = social_age.standings(db, list(ids))
    sects = titles.character_sects(db, ids)
    order = titles.court_order(db, troupe.id)
    held: dict[uuid.UUID, list[str]] = defaultdict(list)
    for who, name in db.execute(
        select(CharacterTitle.character_id, CharacterTitle.name).where(
            CharacterTitle.troupe_id == troupe.id
        )
    ):
        held[who].append(name)

    people: dict[str, Who] = {}

    def side(character_id: uuid.UUID | None, name: str) -> str:
        if character_id is None:
            key = name_key(name)
            people.setdefault(key, Who(key=key, name=name.strip()))
            return key
        key = str(character_id)
        if key not in people:
            character = characters[character_id]
            age = ages.get(character_id)
            people[key] = Who(
                key=key,
                name=character.name,
                character_id=character_id,
                standing=boons.standing(character)
                if court is None
                else court_knows.standing(character, court),
                clan=age.clan if age else None,
                age=age.age if age else None,
                sect=sects.get(character_id),
                titles=tuple(
                    sorted(held.get(character_id, []), key=lambda n: titles.court_key(order, n))
                ),
            )
        return key

    rows = [
        Row(
            debtor=side(b.debtor_id, b.debtor_name),
            creditor=side(b.creditor_id, b.creditor_name),
            kind=b.kind,
            state=b.state,
            made_on=b.made_on,
            settled_how=b.settled_how,
            closed_on=b.closed_at.date() if b.closed_at else None,
            entered_at=b.created_at,
            closed_at=b.closed_at,
            game_id=b.game_id,
        )
        for b in found
    ]
    held_titles = {t for w in people.values() for t in w.titles}
    ranked = sorted(held_titles, key=lambda n: titles.court_key(order, n))
    return Ledger(rows, people, {t: i for i, t in enumerate(ranked)})


# --- what the standings say ---------------------------------------------------------------


@dataclass
class Totals:
    # Standing, with everyone on them in play.
    open: int = 0
    # Standing, but someone on them is dead or off-field.
    departed: int = 0
    settled: int = 0
    # Submitted and waiting for review (#687).
    pending: int = 0
    # Standing boons with a side known only by name, not linked to a character.
    name_only: int = 0


@dataclass
class KindLine:
    kind: str
    weight: float
    count: int
    total: float


@dataclass
class Standing:
    """Where one party stands: what they owe and are owed, by weight and count."""

    who: Who
    owes: float = 0.0
    owed: float = 0.0
    owes_count: int = 0
    owed_count: int = 0

    @property
    def net(self) -> float:
        return self.owed - self.owes


@dataclass
class Tally:
    """Someone on the other side of a list: how many boons, and their weight."""

    who: Who
    count: int
    weight: float


@dataclass
class Officer:
    """A title holder at court: where they stand, who owes them most and whom they owe
    most."""

    title: str
    standing: Standing
    owe_them: list[Tally]
    they_owe: list[Tally]


@dataclass
class Group:
    """A clan, an age or a sect, rolled up: how many on the ledger, and its sums."""

    label: str
    characters: int
    owes: float
    owed: float

    @property
    def net(self) -> float:
        return self.owed - self.owes


@dataclass
class Band:
    label: str
    count: int
    weight: float


@dataclass
class SettledKind:
    kind: str
    count: int
    weight: float
    called_in: int
    forgiven: int
    ignored: int
    # From the night it was made to the day it was settled; None with no dates.
    median_months: float | None


@dataclass
class Collector:
    """A creditor's habit: the weight they have called in, what they still hold, and
    the share of all of it called in."""

    who: Who
    called_in: float
    open: float

    @property
    def rate(self) -> int:
        whole = self.called_in + self.open
        return round(100 * self.called_in / whole) if whole else 0


@dataclass
class Pair:
    """Boons between two clans or sects, either way."""

    label: str
    count: int
    weight: float


@dataclass
class Mutual:
    """Two who owe each other: the one who owes more first, what they owe, what comes
    back, and the difference."""

    first: Who
    second: Who
    owes: float
    back: float

    @property
    def net(self) -> float:
        return self.owes - self.back


@dataclass
class Settling:
    count: int = 0
    weight: float = 0.0
    median_months: float | None = None
    by_kind: list[SettledKind] = field(default_factory=list[SettledKind])
    by_clan: list[Band] = field(default_factory=list[Band])
    calls_in: list[Collector] = field(default_factory=list[Collector])
    leaves: list[Collector] = field(default_factory=list[Collector])


@dataclass
class Across:
    """Open boons that cross a line (clan or sect): how many of all, the pairs, and
    who has most across it."""

    crossing: int
    crossing_weight: float
    of: int
    pairs: list[Pair]
    most: list[Tally]


@dataclass
class Standings:
    scope: Scope
    weights: dict[str, float]
    totals: Totals
    by_kind: list[KindLine]
    characters: list[Standing]
    court: list[Officer]
    clans: list[Group]
    ages: list[Group]
    sects: list[Group]
    debt_age: list[Band]
    settling: Settling
    across_clans: Across
    across_sects: Across
    mutual: list[Mutual]


def months_between(start: date, end: date) -> int:
    """Whole months from one day to another; never below 0."""
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def band_of(months: int) -> int:
    """Its three-month band: 0-3 is the first, 4-6 the second … over 36 the last."""
    return 0 if months <= 3 else min((months - 1) // 3, BANDS)


def band_label(index: int) -> str:
    if index == BANDS:
        return f"Over {BANDS * 3}"
    return "0–3" if index == 0 else f"{index * 3 + 1}–{index * 3 + 3}"


def rounded(value: float) -> float:
    return round(value, 2)


def compute(
    ledger: Ledger,
    weights: Mapping[str, float],
    scope: Scope = "active",
    today: date | None = None,
) -> Standings:
    """Every section of the standings, from the ledger's rows."""
    today = today or date.today()
    rows, people = ledger.rows, ledger.people

    def weight(r: Row) -> float:
        return weights[r.kind]

    def gone(r: Row) -> bool:
        return people[r.debtor].departed or people[r.creditor].departed

    totals = Totals()
    for r in rows:
        if r.state == "pending":
            totals.pending += 1
        elif r.state == "settled":
            totals.settled += 1
        elif gone(r):
            totals.departed += 1
        else:
            totals.open += 1
        if r.state == "registered" and (
            people[r.debtor].character_id is None or people[r.creditor].character_id is None
        ):
            totals.name_only += 1

    kept = [r for r in rows if scope == "everyone" or not gone(r)]
    standing_open = [r for r in kept if r.state == "registered"]
    settled = [r for r in kept if r.state == "settled"]

    by_kind = [
        KindLine(
            kind=k,
            weight=w,
            count=sum(1 for r in standing_open if r.kind == k),
            total=rounded(sum(w for r in standing_open if r.kind == k)),
        )
        for k, w in weights.items()
    ]

    # Where each party stands on what is still open.
    places: dict[str, Standing] = {}
    owing: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for r in standing_open:
        debtor = places.setdefault(r.debtor, Standing(people[r.debtor]))
        creditor = places.setdefault(r.creditor, Standing(people[r.creditor]))
        debtor.owes += weight(r)
        debtor.owes_count += 1
        creditor.owed += weight(r)
        creditor.owed_count += 1
        owing[(r.debtor, r.creditor)].append(r)
    for s in places.values():
        s.owes, s.owed = rounded(s.owes), rounded(s.owed)
    characters = sorted(places.values(), key=lambda s: (-s.net, s.who.name.casefold()))

    def tallies(pairs: Iterable[tuple[str, list[Row]]]) -> list[Tally]:
        found = [Tally(people[k], len(rs), rounded(sum(weight(r) for r in rs))) for k, rs in pairs]
        return sorted(found, key=lambda t: (-t.weight, -t.count, t.who.name.casefold()))[:5]

    court: list[Officer] = []
    for key, who in people.items():
        for title in who.titles:
            place = places.get(key, Standing(who))
            court.append(
                Officer(
                    title=title,
                    standing=place,
                    owe_them=tallies((d, rs) for (d, c), rs in owing.items() if c == key),
                    they_owe=tallies((c, rs) for (d, c), rs in owing.items() if d == key),
                )
            )
    court.sort(
        key=lambda o: (
            ledger.court_order.get(o.title, len(ledger.court_order)),
            o.title,
            o.standing.who.name.casefold(),
        )
    )

    def grouped(label_of: Mapping[str, str]) -> list[Group]:
        groups: dict[str, Group] = {}
        for key, s in places.items():
            label = label_of[key]
            g = groups.setdefault(label, Group(label, 0, 0.0, 0.0))
            g.characters += 1
            g.owes = rounded(g.owes + s.owes)
            g.owed = rounded(g.owed + s.owed)
        return sorted(groups.values(), key=lambda g: (-g.net, g.label))

    def label(value: str | None, who: Who) -> str:
        if value:
            return value
        return "Not known" if who.character_id is not None else "Name only"

    clans = grouped({k: label(people[k].clan, people[k]) for k in places})
    ages = grouped({k: label(people[k].age, people[k]) for k in places})
    sects = grouped({k: label(people[k].sect, people[k]) for k in places})

    aged: list[list[Row]] = [[] for _ in range(BANDS + 1)]
    for r in standing_open:
        aged[band_of(months_between(r.made_on, today))].append(r)
    debt_age = [
        Band(band_label(i), len(rs), rounded(sum(weight(r) for r in rs)))
        for i, rs in enumerate(aged)
    ]

    settling = settling_of(settled, standing_open, people, weights)
    across_clans = across(standing_open, people, weights, lambda w: w.clan)
    across_sects = across(standing_open, people, weights, lambda w: w.sect)

    mutual: list[Mutual] = []
    for (a, b), rs in owing.items():
        if a < b and (b, a) in owing:
            there = sum(weight(r) for r in rs)
            back = sum(weight(r) for r in owing[(b, a)])
            first, second = (a, b) if there >= back else (b, a)
            heavier, lighter = max(there, back), min(there, back)
            mutual.append(Mutual(people[first], people[second], rounded(heavier), rounded(lighter)))
    mutual.sort(key=lambda m: (-(m.owes + m.back), m.first.name.casefold()))

    return Standings(
        scope=scope,
        weights=dict(weights),
        totals=totals,
        by_kind=by_kind,
        characters=characters,
        court=court,
        clans=clans,
        ages=ages,
        sects=sects,
        debt_age=debt_age,
        settling=settling,
        across_clans=across_clans,
        across_sects=across_sects,
        mutual=mutual[: TOP * 2],
    )


def settling_of(
    settled: Sequence[Row],
    standing_open: Sequence[Row],
    people: Mapping[str, Who],
    weights: Mapping[str, float],
) -> Settling:
    """How boons get settled: by kind, how fast, by the debtor's clan, and which
    creditors call theirs in."""

    def months(r: Row) -> int | None:
        return months_between(r.made_on, r.closed_on) if r.closed_on else None

    def median(rs: Iterable[Row]) -> float | None:
        found = [m for m in (months(r) for r in rs) if m is not None]
        return rounded(statistics.median(found)) if found else None

    by_kind = []
    for kind, w in weights.items():
        rs = [r for r in settled if r.kind == kind]
        how = Counter(r.settled_how for r in rs)
        by_kind.append(
            SettledKind(
                kind=kind,
                count=len(rs),
                weight=rounded(w * len(rs)),
                called_in=how["called_in"],
                forgiven=how["forgiven"],
                ignored=how["ignored"],
                median_months=median(rs),
            )
        )

    clans: dict[str, list[Row]] = defaultdict(list)
    for r in settled:
        who = people[r.debtor]
        clans[who.clan or ("Not known" if who.character_id else "Name only")].append(r)
    by_clan = sorted(
        (Band(c, len(rs), rounded(sum(weights[r.kind] for r in rs))) for c, rs in clans.items()),
        key=lambda b: (-b.weight, b.label),
    )

    called: dict[str, float] = defaultdict(float)
    for r in settled:
        if r.settled_how == "called_in":
            called[r.creditor] += weights[r.kind]
    held: dict[str, float] = defaultdict(float)
    for r in standing_open:
        held[r.creditor] += weights[r.kind]
    collectors = [
        Collector(people[k], rounded(called.get(k, 0.0)), rounded(held.get(k, 0.0)))
        for k in set(called) | set(held)
    ]
    calls_in = sorted(
        (c for c in collectors if c.called_in > 0),
        key=lambda c: (-c.rate, -c.called_in, c.who.name.casefold()),
    )[:TOP]
    leaves = sorted(
        (c for c in collectors if c.called_in == 0 and c.open > 0),
        key=lambda c: (-c.open, c.who.name.casefold()),
    )[:TOP]

    return Settling(
        count=len(settled),
        weight=rounded(sum(weights[r.kind] for r in settled)),
        median_months=median(settled),
        by_kind=by_kind,
        by_clan=by_clan,
        calls_in=calls_in,
        leaves=leaves,
    )


def across(
    standing_open: Sequence[Row],
    people: Mapping[str, Who],
    weights: Mapping[str, float],
    line: Callable[[Who], str | None],
) -> Across:
    """Open boons between two different clans (or sects), both known."""
    pairs: dict[str, list[Row]] = defaultdict(list)
    most: dict[str, list[Row]] = defaultdict(list)
    for r in standing_open:
        a, b = line(people[r.debtor]), line(people[r.creditor])
        if not a or not b or a == b:
            continue
        first, second = sorted((a, b))
        pairs[f"{first} ↔ {second}"].append(r)
        most[r.debtor].append(r)
        most[r.creditor].append(r)
    crossing = [r for rs in pairs.values() for r in rs]
    found = sorted(
        (Pair(p, len(rs), rounded(sum(weights[r.kind] for r in rs))) for p, rs in pairs.items()),
        key=lambda p: (-p.weight, p.label),
    )
    exposed = sorted(
        (
            Tally(people[k], len(rs), rounded(sum(weights[r.kind] for r in rs)))
            for k, rs in most.items()
        ),
        key=lambda t: (-t.weight, t.who.name.casefold()),
    )
    return Across(
        crossing=len(crossing),
        crossing_weight=rounded(sum(weights[r.kind] for r in crossing)),
        of=len(standing_open),
        pairs=found[:TOP],
        most=exposed[:TOP],
    )


def standings_of(
    db: Session,
    troupe: Troupe,
    scope: Scope = "active",
    court: Collection[uuid.UUID] | None = None,
) -> Standings:
    """The troupe's standings, read from its ledger now; with `court`, as a Harpy
    reads them (`load`)."""
    return compute(load(db, troupe, court), weights_of(troupe), scope)
