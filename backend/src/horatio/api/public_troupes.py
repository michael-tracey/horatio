"""The troupes anyone may find (#1164): those whose profile is public and that are
still running, for the landing page and the troupe directory (/find-a-troupe, #1192),
signed in or not. Each is only what its public profile shows already
(api/troupe_profiles.py): its name, what it goes by, its portrait, its description,
where and when it plays, whether it takes new players, and its age and content notes.
Its profile is at /t/<troupe id>.

The directory searches and filters them here, from the profile's own fields: its name,
its place (the venue's region and name, and the setting's city, never the street
address, which only people signed in see), the day and how often it plays (from the
schedule, which its storytellers write as words), new players and the minimum age.
A day is also found from its games to come (#1206): one in the next eight weeks on
that weekday, in its lead storyteller's time zone, as the troupe keeps none of its own.
"""

import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import (
    ColumnElement,
    Integer,
    SQLColumnExpression,
    and_,
    exists,
    extract,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from horatio import pictures, troupe_abbreviations
from horatio.api.troupe_profiles import Profile
from horatio.auth.deps import DbSession
from horatio.models import ScheduledGame, Troupe, User

router = APIRouter(prefix="/public/troupes", tags=["troupe profiles"])

# Troupes on a page of the list.
PAGE_SIZE = 12

Day = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
Frequency = Literal["weekly", "fortnightly", "monthly"]

# A day as a schedule writes it: "Saturday", "Saturdays" or "Sat".
DAY_WORDS: dict[str, str] = {
    "monday": r"mon(day)?s?",
    "tuesday": r"tue(s(day)?)?s?",
    "wednesday": r"wed(nesday)?s?",
    "thursday": r"thu(r(s(day)?)?)?s?",
    "friday": r"fri(day)?s?",
    "saturday": r"sat(urday)?s?",
    "sunday": r"sun(day)?s?",
}
# As a whole word. Postgres regular expressions: \m and \M are the start and end of one.
DAYS = {day: rf"\m{words}\M" for day, words in DAY_WORDS.items()}
ANY_DAY = "(" + "|".join(DAY_WORDS.values()) + ")"
# Its day by number, as Postgres's isodow counts them: Monday is 1.
ISO_DAYS = {day: number for number, day in enumerate(DAY_WORDS, start=1)}
# How far ahead its games say which day it plays.
GAMES_AHEAD = timedelta(weeks=8)
# How often, as a schedule says it. "Every Friday" is weekly, "every other Friday" or
# "every second Friday" fortnightly, and anything "of the month" monthly.
FREQUENCIES: dict[str, str] = {
    "weekly": rf"(^|[^a-z-])weekly\M|\m(every|each)\s+(week|{ANY_DAY})\M",
    "fortnightly": (
        rf"fortnight|\mbi-?weekly\M|\mevery\s+(other|second|2nd|two)\s+(weeks?|{ANY_DAY})\M"
    ),
    "monthly": r"month",
}

Words = Annotated[str, Query(max_length=200)]


class PublicTroupeOut(BaseModel):
    id: uuid.UUID
    name: str
    # What it goes by where its name won't fit (horatio.troupe_abbreviations).
    abbreviation: str
    # Where its portrait is (add "/48.webp", "/128.webp" or "/512.webp"), or None.
    portrait: str | None
    # Markdown, as on its profile.
    description: str
    # Its venue's city or region, else its setting's city; "" for neither.
    place: str
    # When it plays, as its storytellers wrote it.
    schedule: str
    new_players: Literal["welcoming", "closed"] | None
    min_age: int | None
    content_notes: str
    # When its next game starts (or the one under way began), as its profile shows
    # it; None with none to come.
    next_game: datetime | None


class PublicTroupePageOut(BaseModel):
    """A page of public troupes, by name."""

    troupes: list[PublicTroupeOut]
    page: int
    pages: int
    total: int


# Which troupes anyone may find: as the sitemap lists them (api/sharing.py).
SHOWN = (Troupe.public, Troupe.archived_at.is_(None))


def field(*path: str) -> ColumnElement[str]:
    """A text field of the troupe's profile, "" where it has none."""
    return func.coalesce(Troupe.profile[path].astext, "")


def containing(column: SQLColumnExpression[str], words: str) -> ColumnElement[bool]:
    return func.lower(column).contains(words.lower(), autoescape=True)


def matching(column: SQLColumnExpression[str], pattern: str) -> ColumnElement[bool]:
    return column.regexp_match(pattern, flags="i")


def plays_on(day: Day, at: datetime) -> ColumnElement[bool]:
    """It has a game still to come, starting in the next GAMES_AHEAD, that falls on
    `day` in its lead storyteller's time zone (UTC for a lead who chose none, as
    elsewhere). A game taken off the schedule is gone, so it never counts."""
    zone = func.coalesce(User.preferences["time_zone"].astext, "UTC")
    return exists().where(
        ScheduledGame.troupe_id == Troupe.id,
        User.id == Troupe.lead_user_id,
        ScheduledGame.ends_at > at,
        ScheduledGame.starts_at < at + GAMES_AHEAD,
        extract("isodow", func.timezone(zone, ScheduledGame.starts_at)) == ISO_DAYS[day],
    )


def filters(
    name: str,
    place: str,
    day: Day | None,
    frequency: Frequency | None,
    new_players: bool,
    age: int | None,
    at: datetime,
) -> list[ColumnElement[bool]]:
    """Which troupes the directory's search finds, beyond SHOWN, at `at`."""
    found: list[ColumnElement[bool]] = []
    if name := name.strip():
        found.append(
            or_(
                containing(Troupe.name, name),
                func.lower(Troupe.abbreviation) == name.lower(),
            )
        )
    if place := place.strip():
        # Where it plays, as its row shows it (its venue's region, else its setting's
        # city), or its venue's name. Never the venue's street address: that is only
        # for people signed in.
        region = field("venue", "region")
        found.append(
            or_(
                containing(region, place),
                containing(field("venue", "name"), place),
                and_(region == "", containing(field("setting", "city"), place)),
            )
        )
    schedule = field("schedule")
    if day:
        # Its schedule names the day, or one of its games falls on it.
        found.append(or_(matching(schedule, DAYS[day]), plays_on(day, at)))
    if frequency:
        found.append(matching(schedule, FREQUENCIES[frequency]))
    if new_players:
        found.append(field("new_players") == "welcoming")
    if age is not None:
        # A troupe that gives no minimum age is open to anyone.
        min_age = Troupe.profile["min_age"].astext.cast(Integer)
        found.append(or_(min_age.is_(None), min_age <= age))
    return found


def next_game_of(db: Session, ids: list[uuid.UUID], at: datetime) -> dict[uuid.UUID, datetime]:
    """When each troupe's next game starts, as its profile shows it first
    (troupe_profiles.upcoming): the soonest not yet over."""
    soonest = (
        select(ScheduledGame.troupe_id, func.min(ScheduledGame.starts_at))
        .where(ScheduledGame.troupe_id.in_(ids), ScheduledGame.ends_at > at)
        .group_by(ScheduledGame.troupe_id)
    )
    return {troupe_id: starts for troupe_id, starts in db.execute(soonest)}


@router.get("")
def list_public_troupes(
    db: DbSession,
    page: int = Query(1, ge=1, le=10_000, description="Counting from 1."),
    name: Words = "",
    place: Words = "",
    day: Annotated[
        Day | None,
        Query(description="A day its schedule names, or that one of its next games is on."),
    ] = None,
    frequency: Annotated[
        Frequency | None, Query(description="How often its schedule says.")
    ] = None,
    new_players: Annotated[bool, Query(description="Only those welcoming new players.")] = False,
    age: Annotated[
        int | None,
        Query(ge=0, le=99, description="Only those a player of this age may join."),
    ] = None,
) -> PublicTroupePageOut:
    """The troupes whose profiles are public and that aren't archived, by name, a page
    at a time, found by the directory's search: by name or abbreviation, place, the
    day (from the schedule or the games to come) and how often they play, whether
    they welcome new players, and age. For anyone at all."""
    at = datetime.now(UTC)
    where = (*SHOWN, *filters(name, place, day, frequency, new_players, age, at))
    total = db.scalar(select(func.count()).select_from(Troupe).where(*where)) or 0
    found = list(
        db.scalars(
            select(Troupe)
            .where(*where)
            .order_by(func.lower(Troupe.name), Troupe.id)
            .limit(PAGE_SIZE)
            .offset((page - 1) * PAGE_SIZE)
        )
    )
    goes_by = troupe_abbreviations.effective(db) if found else {}
    next_games = next_game_of(db, [t.id for t in found], at) if found else {}
    troupes: list[PublicTroupeOut] = []
    for troupe in found:
        kept = Profile.model_validate(troupe.profile)
        troupes.append(
            PublicTroupeOut(
                id=troupe.id,
                name=troupe.name,
                abbreviation=goes_by[troupe.id].abbreviation,
                portrait=pictures.troupe_portrait_url(troupe.id, troupe.portrait_id),
                description=troupe.description,
                place=kept.venue.region or kept.setting.city,
                schedule=kept.schedule,
                new_players=kept.new_players,
                min_age=kept.min_age,
                content_notes=kept.content_notes,
                next_game=next_games.get(troupe.id),
            )
        )
    return PublicTroupePageOut(
        troupes=troupes,
        page=page,
        pages=max(1, math.ceil(total / PAGE_SIZE)),
        total=total,
    )
