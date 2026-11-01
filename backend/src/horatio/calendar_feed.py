"""Calendars a calendar app can subscribe to (issue #420): a troupe's scheduled
games and its downtime cycles' dates, written as iCalendar (RFC 5545).

Horatio keeps moments, not time zones: a game is entered in its storyteller's own
zone and kept as an instant, and everyone sees it in theirs. So each event is
written in UTC, and the calendar app shows it in the subscriber's own zone, as the
app itself does.

Nothing here names a person: no emails, no players, no characters. A game says
when and where it is; a cycle, when downtimes are due and when late ones stop
being taken.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.models import DowntimeCycle, ScheduledGame, Troupe

# How far back a feed reaches: past games and cycles stay in subscribers'
# calendars this long, rather than vanishing once they are over.
KEPT_FOR = timedelta(days=90)
# How often a calendar app should look again. Apps decide for themselves in the
# end (Google's every few hours, whatever this says).
REFRESH = "PT1H"


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


def troupe_events(db: Session, troupes: Sequence[Troupe], now: datetime) -> list[Event]:
    """Each troupe's games and its cycles' due dates and grace ends, from
    `KEPT_FOR` ago on. A cycle still a draft is left out: players cannot see it,
    and its dates are the staff's plan until it opens."""
    if not troupes:
        return []
    by_id = {t.id: t for t in troupes}
    since = now - KEPT_FOR
    base = site()
    events: list[Event] = []
    for game in db.scalars(
        select(ScheduledGame).where(
            ScheduledGame.troupe_id.in_(by_id), ScheduledGame.ends_at > since
        )
    ):
        troupe = by_id[game.troupe_id]
        page = f"{base}/troupes/{troupe.id}"
        events.append(
            Event(
                uid=f"game-{game.id}@horatio",
                summary=f"Game: {troupe.name}",
                starts_at=game.starts_at,
                ends_at=game.ends_at,
                description=f"Say whether you're coming: {page}",
                url=page,
                location=venue(troupe),
                changed_at=game.updated_at,
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
                    summary=f"Late downtimes close: {cycle.name} ({troupe.name})",
                    starts_at=cycle.grace_ends_at,
                    ends_at=None,
                    description="The grace period ends: late downtimes are not taken after this.",
                    url=page,
                    changed_at=cycle.updated_at,
                )
            )
    return events
