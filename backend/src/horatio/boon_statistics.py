"""Boon statistics (#702): the troupe's boon ledger over time, who owes whom, how debt
flows between clans and sects, and what each game did, for the statistics page's
charts.

It builds on the standings (horatio.boon_standings): the same rows (`load`), the same
weights (`weights_of`), the same scope ("active" leaves out boons that involve
someone dead or off-field), and each party's net from `compute`. `compute` here, like
the standings', reads no database, so it can be tested on rows of its own. Only those
who may read the standings read these (`boon_standings.reader`): staff, and the
Harpy with the full ledger where the troupe allows it (#749), who sees who has left
only as the court knows it.

**Time.** A boon has two dates: the in-game night it was made (`made_on`, which can
go back decades) and the day it went in the ledger. The trends go by the day it went
in, as do settling and open debt (a boon is settled on a real day, never an in-game
one); registering can also be read by the in-game night.

**Games.** A boon belongs to a game if staff registered it at that game, or, if none
was given, it went in the ledger from two hours before the game started to twelve
hours after it ended: the Harpy typing in the night's boons as it ends.
"""

import uuid
from collections import Counter, defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import boon_standings as standings
from horatio.boon_standings import Ledger, Row, Scope, Who, rounded
from horatio.models import ScheduledGame, Troupe

# A game's boons: entered from this long before it starts to this long after it ends.
BEFORE_GAME = timedelta(hours=2)
AFTER_GAME = timedelta(hours=12)
# How many of a game's most active the page lists.
MOST_ACTIVE = 3
# The latest games the page shows.
GAMES = 24


@dataclass(frozen=True)
class Game:
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime


@dataclass
class MonthLine:
    """One kind of boon in one month: registered, settled, and what stood at its end.
    `month` is "2026-10"."""

    month: str
    kind: str
    registered: int = 0
    registered_weight: float = 0.0
    settled: int = 0
    settled_weight: float = 0.0
    open: int = 0
    open_weight: float = 0.0


@dataclass
class Node:
    """Someone with open boons: who they are, and where they stand."""

    who: Who
    owes: float
    owed: float
    owes_count: int
    owed_count: int

    @property
    def net(self) -> float:
        return rounded(self.owed - self.owes)


@dataclass
class Link:
    """What one party owes another, still open: how many by kind, and the weight."""

    debtor: str
    creditor: str
    count: int
    weight: float
    kinds: dict[str, int]


@dataclass
class Flow:
    """Open debt between groups (clans or sects): `matrix[i][j]` is the weight owed by
    `groups[i]` to `groups[j]`, and `counts[i][j]` how many boons."""

    groups: list[str]
    matrix: list[list[float]]
    counts: list[list[int]]


@dataclass
class GameActivity:
    game: Game
    registered: int = 0
    registered_weight: float = 0.0
    by_kind: dict[str, int] = field(default_factory=dict[str, int])
    settled: int = 0
    settled_weight: float = 0.0
    # Of those on its boons, the most, by boons as either side.
    most_active: list[tuple[Who, int]] = field(default_factory=list[tuple[Who, int]])


@dataclass
class Statistics:
    scope: Scope
    weights: dict[str, float]
    # By the day each boon went in the ledger; registered by the in-game night.
    by_entered: list[MonthLine]
    by_night: list[MonthLine]
    nodes: list[Node]
    links: list[Link]
    clan_flow: Flow
    sect_flow: Flow
    games: list[GameActivity]


def month_of(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def months_from(first: date, last: date) -> list[str]:
    """Every month from `first`'s to `last`'s, in order."""
    found: list[str] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        found.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return found


def month_end(month: str) -> date:
    year, number = int(month[:4]), int(month[5:])
    following = date(year + 1, 1, 1) if number == 12 else date(year, number + 1, 1)
    return following - timedelta(days=1)


def group_of(value: str | None, who: Who) -> str:
    """A party's clan or sect as the flows group it: a bloodline counts as its clan."""
    if value:
        return value.split(":")[0].strip() or value
    return "Not known" if who.character_id is not None else "Name only"


def trends(rows: Sequence[Row], weights: Mapping[str, float], today: date) -> list[MonthLine]:
    """By month and kind, from the first boon entered to this month: registered and
    settled that month, and open at its end."""
    entered = [r for r in rows if r.entered_at is not None]
    if not entered:
        return []
    first = min(r.entered_at.date() for r in entered if r.entered_at)
    months = months_from(first, today)
    lines = {(m, k): MonthLine(m, k) for m in months for k in weights}
    for r in entered:
        assert r.entered_at is not None
        w = weights[r.kind]
        line = lines[(month_of(r.entered_at.date()), r.kind)]
        line.registered += 1
        line.registered_weight += w
        closed = r.closed_at.date() if r.closed_at else None
        if r.state == "settled" and closed is not None and closed <= today:
            done = lines[(month_of(closed), r.kind)]
            done.settled += 1
            done.settled_weight += w
        # Open at the end of every month from the one it went in until it closed.
        for m in months[months.index(month_of(r.entered_at.date())) :]:
            if closed is not None and closed <= month_end(m):
                break
            stood = lines[(m, r.kind)]
            stood.open += 1
            stood.open_weight += w
    for line in lines.values():
        line.registered_weight = rounded(line.registered_weight)
        line.settled_weight = rounded(line.settled_weight)
        line.open_weight = rounded(line.open_weight)
    return list(lines.values())


def by_night(rows: Sequence[Row], weights: Mapping[str, float]) -> list[MonthLine]:
    """Registered by the in-game night each boon was made, by month and kind; only the
    months that have any."""
    counts: dict[tuple[str, str], MonthLine] = {}
    for r in rows:
        key = (month_of(r.made_on), r.kind)
        line = counts.setdefault(key, MonthLine(*key))
        line.registered += 1
        line.registered_weight = rounded(line.registered_weight + weights[r.kind])
    return sorted(counts.values(), key=lambda line: (line.month, list(weights).index(line.kind)))


def flow(
    standing_open: Sequence[Row],
    people: Mapping[str, Who],
    weights: Mapping[str, float],
    value: str,
) -> Flow:
    """Open debt from each group to each other (and within itself), by weight."""
    pairs: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for r in standing_open:
        debtor, creditor = people[r.debtor], people[r.creditor]
        pairs[
            (group_of(getattr(debtor, value), debtor), group_of(getattr(creditor, value), creditor))
        ].append(r)
    totals: dict[str, float] = defaultdict(float)
    for (a, b), rs in pairs.items():
        w = sum(weights[r.kind] for r in rs)
        totals[a] += w
        totals[b] += w
    groups = sorted(totals, key=lambda g: (-totals[g], g))
    at = {g: i for i, g in enumerate(groups)}
    matrix = [[0.0] * len(groups) for _ in groups]
    counts = [[0] * len(groups) for _ in groups]
    for (a, b), rs in pairs.items():
        matrix[at[a]][at[b]] = rounded(sum(weights[r.kind] for r in rs))
        counts[at[a]][at[b]] = len(rs)
    return Flow(groups, matrix, counts)


def at_game(r: Row, game: Game) -> bool:
    if r.game_id is not None:
        return r.game_id == game.id
    return (
        r.entered_at is not None
        and game.starts_at - BEFORE_GAME <= r.entered_at <= game.ends_at + AFTER_GAME
    )


def activity(
    rows: Sequence[Row], people: Mapping[str, Who], weights: Mapping[str, float], game: Game
) -> GameActivity:
    """What a game did: boons registered at it, by kind, those settled during it, and
    who was on most of them."""
    found = GameActivity(game)
    on: Counter[str] = Counter()
    for r in rows:
        if at_game(r, game):
            found.registered += 1
            found.registered_weight = rounded(found.registered_weight + weights[r.kind])
            found.by_kind[r.kind] = found.by_kind.get(r.kind, 0) + 1
            on[r.debtor] += 1
            on[r.creditor] += 1
        if (
            r.state == "settled"
            and r.closed_at is not None
            and game.starts_at - BEFORE_GAME <= r.closed_at <= game.ends_at + AFTER_GAME
        ):
            found.settled += 1
            found.settled_weight = rounded(found.settled_weight + weights[r.kind])
    ranked = sorted(on.items(), key=lambda kv: (-kv[1], people[kv[0]].name.casefold()))
    found.most_active = [(people[k], n) for k, n in ranked[:MOST_ACTIVE]]
    return found


def compute(
    ledger: Ledger,
    weights: Mapping[str, float],
    games: Sequence[Game] = (),
    scope: Scope = "active",
    today: date | None = None,
) -> Statistics:
    """Every chart's data, from the ledger's rows and the troupe's games."""
    today = today or date.today()
    people = ledger.people

    def gone(r: Row) -> bool:
        return people[r.debtor].departed or people[r.creditor].departed

    # Pending boons were never registered; void ones are never rows.
    kept = [r for r in ledger.rows if r.state != "pending" and (scope == "everyone" or not gone(r))]
    standing_open = [r for r in kept if r.state == "registered"]

    # Each party's standing, as the standings work it out.
    places = standings.compute(ledger, weights, scope, today).characters
    nodes = [Node(s.who, s.owes, s.owed, s.owes_count, s.owed_count) for s in places]

    owing: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for r in standing_open:
        owing[(r.debtor, r.creditor)].append(r)
    links = sorted(
        (
            Link(
                debtor=d,
                creditor=c,
                count=len(rs),
                weight=rounded(sum(weights[r.kind] for r in rs)),
                kinds=dict(Counter(r.kind for r in rs)),
            )
            for (d, c), rs in owing.items()
        ),
        key=lambda link: (-link.weight, link.debtor, link.creditor),
    )

    return Statistics(
        scope=scope,
        weights=dict(weights),
        by_entered=trends(kept, weights, today),
        by_night=by_night(kept, weights),
        nodes=nodes,
        links=links,
        clan_flow=flow(standing_open, people, weights, "clan"),
        sect_flow=flow(standing_open, people, weights, "sect"),
        games=[activity(kept, people, weights, g) for g in games],
    )


def games_of(db: Session, troupe: Troupe, now: datetime) -> list[Game]:
    """The troupe's latest games already started, newest first."""
    return [
        Game(g.id, g.starts_at, g.ends_at)
        for g in db.scalars(
            select(ScheduledGame)
            .where(ScheduledGame.troupe_id == troupe.id, ScheduledGame.starts_at <= now)
            .order_by(ScheduledGame.starts_at.desc())
            .limit(GAMES)
        )
    ]


def statistics_of(
    db: Session,
    troupe: Troupe,
    now: datetime,
    scope: Scope = "active",
    court: Collection[uuid.UUID] | None = None,
) -> Statistics:
    """The troupe's statistics, read from its ledger now; with `court`, as a Harpy reads
    them (horatio.boon_standings.load)."""
    return compute(
        standings.load(db, troupe, court),
        standings.weights_of(troupe),
        games_of(db, troupe, now),
        scope,
        now.date(),
    )
