"""Game XP charts (issue #438): how a troupe gives a game's XP, all of it optional.

With nothing set, a troupe works as the book suggests (MET: VtM core, p. 108) and
as check-in has always awarded (horatio.api.checkin): staff give everyone there the
same XP, the troupe's session XP to start with, and an award that takes a character
past 10 XP earned in the calendar month is warned of, never refused. That is the
"Flat" preset.

A troupe may set instead:

- A chart: rows of earned-XP bands ("0–200", "201–300" ... "501+"), and for each the
  XP for a game attended and for an absentee game. Earned XP is counted as the
  monthly guidance counts it (horatio.checkin.earned), over the character's whole
  history: awards and corrections, without starting XP or what joining a troupe gave.
  A character's band is read when its award is made, so a character who crosses into
  the next band mid-month gets the next band's figure from its next game on.
- Adjustments: an amount staff tick for a character when awarding ("Helped +1",
  "Not findable −1"), each with an optional limit of so many times a calendar month.
- The monthly cap: "warn" past it (the book's 10, or the troupe's own figure), "cap"
  awards at it, so the excess is not given, or "off".
- Absentee games: staff, or players where the troupe allows, record a character as
  absentee for a game it missed. It is its own attendance kind (GameAttendance.kind
  "absentee"), never counted as having been there, and the game's award gives it the
  chart's absentee figure. Payments are not tracked: "paid" is staff marking it.
  With absentee downtimes on, a character can submit a cycle's downtime only if it
  attended a game in the lookback (60 days unless set) before the cycle closes.

Staff can set any one character's figure by hand, with a reason. Each award is its
own XP entry, its reason naming the attendance kind and band, and a GameXpAward
keeps the working: the figure, the adjustments ticked, what the cap held back.

The troupe's XP floor and ceiling (horatio.xp_range) rise by the game's XP for a
character at the floor: the chart's attended figure for the band of the floor's
earned XP (the floor less the starting XP), capped in "cap" mode against the game
XP the floor has had this month. With no chart, the game's flat amount, as before.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, checkin, sheets, xp_range
from horatio.models import (
    Character,
    DowntimeCycle,
    GameAttendance,
    GameXpAward,
    ScheduledGame,
    Troupe,
    User,
    XpRangeEntry,
)
from horatio.sheets import unprocessable

Kind = Literal["attended", "absentee"]
CapMode = Literal["warn", "cap", "off"]
KIND_TEXT = {"attended": "attended", "absentee": "absentee"}
LOOKBACK_DAYS = 60
MAX_BANDS = 20
MAX_ADJUSTMENTS = 12


class Band(BaseModel):
    """One row of the chart: earned XP up to and including `up_to` (None for the last
    row, which has no top), and the XP for a game attended and an absentee game."""

    up_to: int | None = Field(default=None, ge=0, le=100_000)
    attended: int = Field(ge=0, le=100)
    absentee: int = Field(ge=0, le=100)


class Adjustment(BaseModel):
    """XP staff tick for a character when awarding a game: "Helped +1", at most
    `per_month` times a calendar month (None for no limit)."""

    # Kept across edits, so monthly limits keep counting; made when first saved.
    key: str = Field(default="", max_length=40)
    name: str = Field(min_length=1, max_length=60)
    amount: int = Field(ge=-100, le=100)
    per_month: int | None = Field(default=None, ge=1, le=31)


class GameXpSettings(BaseModel):
    """A troupe's game XP, as Troupe.game_xp keeps it. The defaults are the book's way."""

    # Empty: no chart, the "Flat" preset.
    bands: list[Band] = Field(default=[], max_length=MAX_BANDS)
    adjustments: list[Adjustment] = Field(default=[], max_length=MAX_ADJUSTMENTS)
    cap: CapMode = "warn"
    # The monthly figure the cap works to; None for the book's (horatio.checkin.MONTHLY_XP).
    monthly_xp: int | None = Field(default=None, ge=1, le=1000)
    absentee: bool = False
    # Players may mark their own characters absentee, as well as staff.
    absentee_by_players: bool = False
    # A downtime needs a game attended within the lookback before its cycle closes.
    absentee_downtime: bool = False
    absentee_lookback_days: int = Field(default=LOOKBACK_DAYS, ge=1, le=365)


def settings(troupe: Troupe) -> GameXpSettings:
    return GameXpSettings.model_validate(troupe.game_xp or {})


def monthly_limit(found: GameXpSettings) -> int:
    return found.monthly_xp or checkin.MONTHLY_XP


def tidy(found: GameXpSettings) -> GameXpSettings:
    """Check a chart before it is kept: bands rising, the last with no top, and each
    adjustment named once, not nothing, with its key."""
    bands = found.bands
    if bands:
        tops = [b.up_to for b in bands[:-1]]
        if any(top is None for top in tops):
            raise unprocessable("Only the last band can have no top.")
        if bands[-1].up_to is not None:
            raise unprocessable("The last band goes on from the one before, with no top.")
        rising = [t for t in tops if t is not None]
        if any(b <= a for a, b in zip(rising, rising[1:], strict=False)):
            raise unprocessable("Each band must go higher than the one before.")
    seen: set[str] = set()
    keys: set[str] = set()
    adjustments: list[Adjustment] = []
    for a in found.adjustments:
        name = a.name.strip()
        if not name:
            raise unprocessable("Each adjustment needs a name.")
        if name.lower() in seen:
            raise unprocessable(f"There are two adjustments called {name}.")
        if a.amount == 0:
            raise unprocessable(f"{name} adds no XP: give it an amount, more or less.")
        seen.add(name.lower())
        key = a.key or uuid.uuid4().hex[:12]
        while key in keys:
            key = uuid.uuid4().hex[:12]
        keys.add(key)
        adjustments.append(a.model_copy(update={"name": name, "key": key}))
    return found.model_copy(update={"adjustments": adjustments})


# --- words --------------------------------------------------------------------------------


def band_label(bands: Sequence[Band], index: int) -> str:
    """A band's label: "0–200", "201–300", "501+"."""
    low = 0 if index == 0 else (bands[index - 1].up_to or 0) + 1
    top = bands[index].up_to
    return f"{low}+" if top is None else f"{low}–{top}"


def signed(amount: int) -> str:
    """An amount with its sign, "+1" or "−1", with a true minus."""
    return f"+{amount}" if amount >= 0 else f"−{-amount}"


def adjustment_text(a: Adjustment) -> str:
    """An adjustment in words: "Helped +1, once a month"."""
    times = {None: "", 1: ", once a month", 2: ", twice a month"}.get(
        a.per_month, f", {a.per_month} times a month"
    )
    return f"{a.name} {signed(a.amount)}{times}"


def chart_text(found: GameXpSettings) -> str:
    """The chart in a sentence: "5 XP a game up to 200 earned XP, 4 up to 300, then 1;
    an absentee game 4, 3 and 0"."""
    bands = found.bands
    if not bands:
        return "Flat: the troupe's session XP for each game"
    if len(bands) == 1:
        text = f"{bands[0].attended} XP a game"
    else:
        text = ", ".join(
            f"{b.attended} XP a game up to {b.up_to} earned XP"
            if n == 0
            else f"then {b.attended}"
            if b.up_to is None
            else f"{b.attended} up to {b.up_to}"
            for n, b in enumerate(bands)
        )
    if found.absentee:
        figures = [str(b.absentee) for b in bands]
        joined = figures[0] if len(figures) == 1 else f"{', '.join(figures[:-1])} and {figures[-1]}"
        text += f"; an absentee game {joined}"
    return text


def cap_text(found: GameXpSettings) -> str:
    if found.cap == "off":
        return "Not limited"
    limit = monthly_limit(found)
    return f"Warned past {limit} a month" if found.cap == "warn" else f"Capped at {limit} a month"


def absentee_text(found: GameXpSettings) -> str:
    if not found.absentee:
        return "Not recorded"
    who = "staff or the player" if found.absentee_by_players else "staff"
    text = f"Recorded by {who}"
    if found.absentee_downtime:
        text += (
            f"; a downtime needs a game attended in the {found.absentee_lookback_days} days"
            " before its cycle closes"
        )
    return text


def house_settings(troupe: Troupe) -> list[tuple[str, str, str]]:
    """The troupe's game XP where it differs from the book, as the House rules tab lists
    house rules: (what, how the troupe plays it, how the book does)."""
    found = settings(troupe)
    rows: list[tuple[str, str, str]] = []
    book_game = f"{checkin.GAME_XP[0]} to {checkin.GAME_XP[1]} XP a game (MET: VtM core, p. 108)"
    if found.bands:
        rows.append(("Game XP, by earned XP", chart_text(found), book_game))
    for a in found.adjustments:
        rows.append((f"Game XP adjustment: {a.name}", adjustment_text(a), "None"))
    if found.cap != "warn" or found.monthly_xp is not None:
        rows.append(
            (
                "Monthly XP",
                cap_text(found),
                f"No more than 8 to {checkin.MONTHLY_XP} a month (MET: VtM core, p. 108)",
            )
        )
    if found.absentee:
        rows.append(
            (
                "Absentee games",
                absentee_text(found) + ". Payments are not tracked in Horatio",
                "None",
            )
        )
    return rows


# --- saving ------------------------------------------------------------------------------


def save(db: Session, staff: User, troupe: Troupe, chosen: GameXpSettings) -> GameXpSettings:
    found = tidy(chosen)
    troupe.game_xp = found.model_dump(mode="json")
    audit.record(
        db,
        staff,
        "troupe.xp_game_settings",
        troupe_id=troupe.id,
        chart=chart_text(found),
        adjustments=", ".join(adjustment_text(a) for a in found.adjustments) or "none",
        cap=cap_text(found).lower(),
        absentee=absentee_text(found).lower(),
    )
    db.flush()
    return found


# --- a game's award ----------------------------------------------------------------------


@dataclass
class Line:
    """A character to award for a game, and what its figure comes from."""

    character: Character
    kind: str
    # XP earned in all, and in the calendar month so far (horatio.checkin.earned).
    earned: int
    month: int
    # Its band on the chart, and the chart's figure for it and its kind; None with no chart.
    band: str | None
    figure: int | None
    # How often each adjustment has been ticked for it this calendar month, by key.
    used: dict[str, int] = field(default_factory=dict)


def band_of(found: GameXpSettings, earned: int) -> tuple[str, Band] | None:
    for n, b in enumerate(found.bands):
        if b.up_to is None or earned <= b.up_to:
            return band_label(found.bands, n), b
    return None


def month_began(today: datetime | None = None) -> datetime:
    at = today or checkin.now()
    return datetime.combine(checkin.month_start(at.date()), datetime.min.time(), tzinfo=UTC)


def used_this_month(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """How often each adjustment was ticked for each character this calendar month."""
    found: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)
    for character_id, ticked in db.execute(
        select(GameXpAward.character_id, GameXpAward.adjustments).where(
            GameXpAward.character_id.in_(list(ids)), GameXpAward.created_at >= month_began()
        )
    ):
        for a in ticked:
            key = str(a.get("key", ""))
            found[character_id][key] = found[character_id].get(key, 0) + 1
    return found


def lines(db: Session, troupe: Troupe, present: Sequence[tuple[Character, str]]) -> list[Line]:
    """Each character with its attendance kind, ready to award."""
    found = settings(troupe)
    ids = [c.id for c, _ in present]
    earned = checkin.earned(db, ids)
    month = checkin.earned_this_month(db, ids)
    used = used_this_month(db, ids)
    out: list[Line] = []
    for character, kind in present:
        band = band_of(found, earned[character.id])
        out.append(
            Line(
                character=character,
                kind=kind,
                earned=earned[character.id],
                month=month[character.id],
                band=band[0] if band else None,
                figure=(band[1].absentee if kind == "absentee" else band[1].attended)
                if band
                else None,
                used=used.get(character.id, {}),
            )
        )
    return out


@dataclass
class Choice:
    """What staff chose for one character: adjustments ticked, and a figure set by hand."""

    ticks: list[str] = field(default_factory=list)
    override: int | None = None
    override_reason: str = ""


@dataclass
class Given:
    line: Line
    figure: int
    ticked: list[Adjustment]
    capped: int
    override: int | None
    override_reason: str
    amount: int
    reason: str


def work_out(
    found: GameXpSettings,
    line: Line,
    choice: Choice,
    *,
    flat: int,
    flat_absentee: int | None,
    reason: str,
) -> Given:
    """One character's XP for the game: its band and kind's figure (or the flat
    amount), with the adjustments ticked, and the cap; or the figure staff set."""
    name = line.character.name
    if line.figure is not None:
        figure = line.figure
    elif line.kind == "absentee":
        if flat_absentee is None:
            raise unprocessable("Say how much XP an absentee game gets.")
        figure = flat_absentee
    else:
        figure = flat
    known = {a.key: a for a in found.adjustments}
    ticked: list[Adjustment] = []
    for key in dict.fromkeys(choice.ticks):
        adjustment = known.get(key)
        if adjustment is None:
            raise unprocessable("That adjustment isn't in the troupe's chart any more.")
        if adjustment.per_month is not None and line.used.get(key, 0) >= adjustment.per_month:
            raise unprocessable(
                f"{name} has had {adjustment.name} {adjustment.per_month} times this month,"
                " its limit."
                if adjustment.per_month > 1
                else f"{name} has had {adjustment.name} this month, its limit."
            )
        ticked.append(adjustment)
    worked = max(0, figure + sum(a.amount for a in ticked))
    capped = 0
    override = choice.override
    override_reason = choice.override_reason.strip()
    if override is not None:
        if not override_reason:
            raise unprocessable(f"Say why {name}'s XP is set by hand.")
        amount = override
    else:
        amount = worked
        if found.cap == "cap":
            amount = min(worked, max(0, monthly_limit(found) - line.month))
            capped = worked - amount

    details: list[str] = []
    if line.band is not None:
        details.append(f"{KIND_TEXT[line.kind]}, {line.band} band")
    elif line.kind == "absentee":
        details.append(KIND_TEXT["absentee"])
    details.extend(f"{a.name} {signed(a.amount)}" for a in ticked)
    if capped:
        details.append(f"{capped} held back by the monthly cap of {monthly_limit(found)}")
    text = reason
    if details:
        text += ": " + ", ".join(details)
    if override is not None:
        text += f"; set by hand to {override}: {override_reason}"
    return Given(
        line=line,
        figure=figure,
        ticked=ticked,
        capped=capped,
        override=override,
        override_reason=override_reason,
        amount=amount,
        reason=text[:500],
    )


def give(db: Session, staff: User, game: ScheduledGame, given: Sequence[Given]) -> None:
    """Each character its own XP entry, and the working kept beside it."""
    for g in given:
        entry = (
            sheets.award_xp(db, staff, g.line.character, g.amount, g.reason)
            if g.amount > 0
            else None
        )
        db.add(
            GameXpAward(
                game_id=game.id,
                character_id=g.line.character.id,
                kind=g.line.kind,
                band=g.line.band,
                figure=g.figure,
                adjustments=[{"key": a.key, "name": a.name, "amount": a.amount} for a in g.ticked],
                capped=g.capped,
                override=g.override,
                override_reason=g.override_reason,
                amount=g.amount,
                xp_entry_id=entry.id if entry else None,
                awarded_by=staff.id,
            )
        )
    db.flush()


def range_figure(db: Session, troupe: Troupe, flat: int) -> int:
    """What the game adds to the troupe's XP floor and ceiling: the XP a character at
    the floor who came would get. With no chart, the flat amount."""
    found = settings(troupe)
    if not found.bands:
        return flat
    figures = xp_range.figures(db, troupe)
    band = band_of(found, max(0, figures.floor - troupe.starting_xp))
    amount = band[1].attended if band else 0
    if found.cap == "cap":
        this_month = db.scalar(
            select(func.coalesce(func.sum(XpRangeEntry.floor_change), 0)).where(
                XpRangeEntry.troupe_id == troupe.id,
                XpRangeEntry.kind == "game",
                XpRangeEntry.entered_on >= checkin.month_start(checkin.now().date()),
            )
        )
        amount = min(amount, max(0, monthly_limit(found) - int(this_month or 0)))
    return amount


# --- absentee downtimes -------------------------------------------------------------------


def downtime_closed(db: Session, cycle: DowntimeCycle, character: Character) -> str | None:
    """Why the cycle's downtime is closed to the character, if it is: the troupe asks
    for a game attended within its lookback before the cycle closes, and it has none.
    An absentee game does not count."""
    troupe = db.get(Troupe, cycle.troupe_id)
    if troupe is None:
        return None
    found = settings(troupe)
    if not (found.absentee and found.absentee_downtime):
        return None
    days = found.absentee_lookback_days
    since = cycle.closes_at - timedelta(days=days)
    came = db.scalar(
        select(GameAttendance.id)
        .join(ScheduledGame, GameAttendance.game_id == ScheduledGame.id)
        .where(
            GameAttendance.character_id == character.id,
            checkin.ATTENDED,
            ScheduledGame.starts_at >= since,
            ScheduledGame.starts_at <= cycle.closes_at,
        )
        .limit(1)
    )
    if came is not None:
        return None
    return (
        f"{character.name} hasn't attended a game in the {days} days before this cycle closes,"
        " so this downtime is closed to it. An absentee game doesn't count. A storyteller can"
        " still let it in with Accept late."
    )
