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
"""

import math
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Integer, SQLColumnExpression, and_, func, or_, select

from horatio import pictures, troupe_abbreviations
from horatio.api.troupe_profiles import Profile
from horatio.auth.deps import DbSession
from horatio.models import Troupe

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


def filters(
    name: str,
    place: str,
    day: Day | None,
    frequency: Frequency | None,
    new_players: bool,
    age: int | None,
) -> list[ColumnElement[bool]]:
    """Which troupes the directory's search finds, beyond SHOWN."""
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
        found.append(matching(schedule, DAYS[day]))
    if frequency:
        found.append(matching(schedule, FREQUENCIES[frequency]))
    if new_players:
        found.append(field("new_players") == "welcoming")
    if age is not None:
        # A troupe that gives no minimum age is open to anyone.
        min_age = Troupe.profile["min_age"].astext.cast(Integer)
        found.append(or_(min_age.is_(None), min_age <= age))
    return found


@router.get("")
def list_public_troupes(
    db: DbSession,
    page: int = Query(1, ge=1, le=10_000, description="Counting from 1."),
    name: Words = "",
    place: Words = "",
    day: Annotated[Day | None, Query(description="A day its schedule names.")] = None,
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
    day and how often they play, whether they welcome new players, and age. For anyone
    at all."""
    where = (*SHOWN, *filters(name, place, day, frequency, new_players, age))
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
            )
        )
    return PublicTroupePageOut(
        troupes=troupes,
        page=page,
        pages=max(1, math.ceil(total / PAGE_SIZE)),
        total=total,
    )
