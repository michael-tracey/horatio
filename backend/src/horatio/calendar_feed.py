"""Calendars a calendar app can subscribe to (issue #420): a troupe's scheduled
games and its downtime cycles' dates, written as iCalendar (RFC 5545).

Horatio keeps moments, not time zones: a game is entered in its storyteller's own
zone and kept as an instant, and everyone sees it in theirs. So each event is
written in UTC, and the calendar app shows it in the subscriber's own zone, as the
app itself does.

Nothing here names a person: no emails, no players, no characters. A game says
when and where it is, and whether the subscriber said they are coming (issue
#1058); a cycle, when downtimes are due and when late ones stop being taken.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.models import DowntimeCycle, GameRsvp, ScheduledGame, Troupe

# How far back a feed reaches: past games and cycles stay in subscribers'
# calendars this long, rather than vanishing once they are over.
KEPT_FOR = timedelta(days=90)
# How often a calendar app should look again. Apps decide for themselves in the
# end (Google's every few hours, whatever this says).
REFRESH = "PT1H"

# The subscriber's own RSVP to a game, as its title starts and its description
# says. A game they are not coming to stays in their calendar, marked: an event
# sent as cancelled is one calendar apps delete.
ANSWERED = {
    "coming": ("Coming", "You said you're coming."),
    "maybe": ("Maybe", "You said maybe."),
    "not_coming": ("Not coming", "You said you're not coming."),
}
NOT_ANSWERED = "You haven't said whether you're coming."


@dataclass(frozen=True)
class Event:
    uid: str
    summary: str
    starts_at: datetime
    # None for a moment, such as a deadline, rather than a span.
    ends_at: datetime | None
    description: str
    url: str
    location: str = ""
    changed_at: datetime | None = None


def escaped(text: str) -> str:
    """Text as an iCalendar TEXT value: backslashes, semicolons, commas and line
    breaks escaped (RFC 5545 3.3.11)."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def folded(line: str) -> str:
    """A content line folded to at most 75 octets a line, each continuation
    starting with a space (RFC 5545 3.1), never splitting a character."""
    out: list[str] = []
    current = ""
    size = 0
    for char in line:
        width = len(char.encode())
        if size + width > 75:
            out.append(current)
            current, size = " ", 1
        current += char
        size += width
    out.append(current)
    return "\r\n".join(out)


def stamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def calendar(name: str, description: str, events: Iterable[Event], now: datetime) -> str:
    """The whole calendar, as text with CRLF line ends."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Horatio//Troupe calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escaped(name)}",
        f"X-WR-CALDESC:{escaped(description)}",
        f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH}",
        f"X-PUBLISHED-TTL:{REFRESH}",
    ]
    for event in sorted(events, key=lambda e: (e.starts_at, e.uid)):
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event.uid}",
            f"DTSTAMP:{stamp(now)}",
            f"DTSTART:{stamp(event.starts_at)}",
        ]
        if event.ends_at is not None:
            lines.append(f"DTEND:{stamp(event.ends_at)}")
        if event.changed_at is not None:
            lines.append(f"LAST-MODIFIED:{stamp(event.changed_at)}")
        lines += [f"SUMMARY:{escaped(event.summary)}", f"DESCRIPTION:{escaped(event.description)}"]
        if event.location:
            lines.append(f"LOCATION:{escaped(event.location)}")
        lines += [f"URL:{event.url}", "TRANSP:OPAQUE" if event.ends_at else "TRANSP:TRANSPARENT"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(folded(line) + "\r\n" for line in lines)


def site() -> str:
    return get_settings().public_url.rstrip("/")


def venue(troupe: Troupe) -> str:
    """Where the troupe plays: its venue's name, street address and region, as its
    profile has them. Only members have a feed, and they may see the address."""
    kept = troupe.profile.get("venue") or {}
    parts = [str(kept.get(key) or "").strip() for key in ("name", "address", "region")]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def troupe_events(
    db: Session, troupes: Sequence[Troupe], user_id: uuid.UUID, now: datetime
) -> list[Event]:
    """Each troupe's games, with the subscriber's own RSVP to each, and its
    cycles' due dates and grace ends, from `KEPT_FOR` ago on. A cycle still a
    draft is left out: players cannot see it, and its dates are the staff's plan
    until it opens."""
    if not troupes:
        return []
    by_id = {t.id: t for t in troupes}
    since = now - KEPT_FOR
    base = site()
    events: list[Event] = []
    games = list(
        db.scalars(
            select(ScheduledGame).where(
                ScheduledGame.troupe_id.in_(by_id), ScheduledGame.ends_at > since
            )
        )
    )
    rsvps = {
        r.game_id: r
        for r in db.scalars(
            select(GameRsvp).where(
                GameRsvp.user_id == user_id, GameRsvp.game_id.in_([g.id for g in games])
            )
        )
    }
    for game in games:
        troupe = by_id[game.troupe_id]
        page = f"{base}/troupes/{troupe.id}"
        rsvp = rsvps.get(game.id)
        summary = f"Game: {troupe.name}"
        if rsvp is None:
            description = f"{NOT_ANSWERED} Say on the troupe's page: {page}"
            changed_at = game.updated_at
        else:
            label, said = ANSWERED[rsvp.answer]
            summary = f"{label} · {summary}"
            description = f"{said} Change your answer on the troupe's page: {page}"
            # A new answer is a change to the event, as an edit to the game is, so
            # a calendar app that looks at when an event last changed takes it.
            changed_at = max(game.updated_at, rsvp.updated_at)
        events.append(
            Event(
                uid=f"game-{game.id}@horatio",
                summary=summary,
                starts_at=game.starts_at,
                ends_at=game.ends_at,
                description=description,
                url=page,
                location=venue(troupe),
                changed_at=changed_at,
            )
        )
    for cycle in db.scalars(
        select(DowntimeCycle).where(
            DowntimeCycle.troupe_id.in_(by_id),
            DowntimeCycle.status != "draft",
            DowntimeCycle.grace_ends_at > since,
        )
    ):
        troupe = by_id[cycle.troupe_id]
        page = f"{base}/troupes/{troupe.id}"
        events.append(
            Event(
                uid=f"downtimes-due-{cycle.id}@horatio",
                summary=f"Downtimes due: {cycle.name} ({troupe.name})",
                starts_at=cycle.closes_at,
                ends_at=None,
                description=(
                    "A downtime submitted after this is late."
                    if cycle.grace_ends_at > cycle.closes_at
                    else "Downtimes are not taken after this."
                ),
                url=page,
                changed_at=cycle.updated_at,
            )
        )
        if cycle.grace_ends_at > cycle.closes_at:
            events.append(
                Event(
                    uid=f"downtimes-grace-{cycle.id}@horatio",
                    summary=f"Downtimes accepted until: {cycle.name} ({troupe.name})",
                    starts_at=cycle.grace_ends_at,
                    ends_at=None,
                    description="The grace period ends: late downtimes are not taken after this.",
                    url=page,
                    changed_at=cycle.updated_at,
                )
            )
    return events
