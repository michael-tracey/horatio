"""Calendar links (issue #420): a secret address a calendar app subscribes to
without signing in, carrying a troupe's games and downtime dates
(horatio.calendar_feed).

Each member of a troupe has their own link to its calendar, and each person one
to the calendars of every troupe they are in, so they subscribe once. A link is
made when its person first asks for it, and resetting it gives it a new address:
the old one stops working at once. The address is the only secret, so it is long
and random, and it opens that calendar and nothing else.

A link works only while its person could see the troupe's dates in Horatio: a
member of it, not suspended, and not merged into another account. There is no
public calendar, even for a troupe with a public profile: the profile already
shows its games to come, and a link anyone may hold can never be taken back.
"""

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import calendar_feed, suspensions
from horatio.api.games import member_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import CalendarFeed, Troupe, User
from horatio.permissions import is_member, member_troupe_ids

router = APIRouter(prefix="/calendar", tags=["calendar"])

NOT_A_LINK = "This calendar link doesn't work. Get a new one from the troupe's page in Horatio."


class CalendarLink(BaseModel):
    # The https address; a calendar app may also take it as webcal://.
    url: str


class CalendarLinks(BaseModel):
    # The caller's link to this troupe's calendar, and to all their troupes',
    # each None until they ask for it.
    troupe: CalendarLink | None
    personal: CalendarLink | None


class CalendarLinkIn(BaseModel):
    # The troupe whose calendar; None for all the caller's troupes.
    troupe_id: uuid.UUID | None


def link(feed: CalendarFeed | None) -> CalendarLink | None:
    if feed is None:
        return None
    return CalendarLink(url=f"{calendar_feed.site()}/api/calendar/{feed.token}.ics")


def feed_of(db: Session, user: User, troupe_id: uuid.UUID | None) -> CalendarFeed | None:
    return db.scalar(
        select(CalendarFeed).where(
            CalendarFeed.user_id == user.id,
            CalendarFeed.troupe_id.is_(None)
            if troupe_id is None
            else CalendarFeed.troupe_id == troupe_id,
        )
    )


@router.get("/links")
def links(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CalendarLinks:
    """The caller's calendar links, for a member of the troupe."""
    troupe = member_troupe(db, user, troupe_id)
    return CalendarLinks(
        troupe=link(feed_of(db, user, troupe.id)), personal=link(feed_of(db, user, None))
    )


@router.post("/links")
def make_link(body: CalendarLinkIn, db: DbSession, user: CurrentUser) -> CalendarLink:
    """A new address for one of the caller's calendars: made the first time,
    and after that reset, so the old address stops working."""
    if body.troupe_id is not None:
        member_troupe(db, user, body.troupe_id)
    feed = feed_of(db, user, body.troupe_id)
    token = secrets.token_urlsafe(32)
    if feed is None:
        feed = CalendarFeed(user_id=user.id, troupe_id=body.troupe_id, token=token)
        db.add(feed)
    else:
        feed.token = token
    db.commit()
    made = link(feed)
    assert made is not None
    return made


# Some calendar apps ask with HEAD first, to see whether the calendar is there.
@router.head("/{token}.ics", include_in_schema=False)
@router.get("/{token}.ics", response_class=Response)
def feed(token: str, db: DbSession) -> Response:
    """The calendar itself, for a calendar app: no sign-in, only the address."""
    found = db.scalar(select(CalendarFeed).where(CalendarFeed.token == token))
    user = db.get(User, found.user_id) if found else None
    if found is None or user is None or user.merged_into_id is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_A_LINK)
    if suspensions.current(db, user.id) is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_A_LINK)
    now = datetime.now(UTC)
    if found.troupe_id is not None:
        troupe = db.get(Troupe, found.troupe_id)
        if troupe is None or not is_member(db, user, troupe):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_A_LINK)
        troupes = [troupe]
        name = troupe.name
        about = f"{troupe.name}'s games and downtime dates, from Horatio."
    else:
        ids = member_troupe_ids(db, user)
        troupes = list(db.scalars(select(Troupe).where(Troupe.id.in_(ids)).order_by(Troupe.name)))
        name = "Your troupes"
        about = "Games and downtime dates of every troupe you're in, from Horatio."
    text = calendar_feed.calendar(name, about, calendar_feed.troupe_events(db, troupes, now), now)
    return Response(
        text,
        media_type="text/calendar",
        headers={
            "Content-Disposition": 'inline; filename="horatio.ics"',
            "Cache-Control": "private, max-age=900",
        },
    )
