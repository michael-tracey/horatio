"""A troupe's time zone (#1211): where its games' days fall, and its NPCs' days end.

Its storytellers choose one from the IANA list, as each person chooses their own in
Settings (horatio.preferences). A troupe that hasn't, as every troupe made before it
had none, uses its lead storyteller's, and UTC while they haven't chosen one either.
A new troupe starts with the zone of whoever made or asked for it, or their browser's.

Game times are kept as moments, never as a zone's clock (horatio.calendar_feed), so a
change of zone moves no game: it changes which day each falls on, here.

Everything that needs a troupe's zone asks here: `name` and `zone` for one troupe,
`names` for many at once, and `column` inside a query.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from zoneinfo import ZoneInfo, available_timezones

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from horatio import audit, preferences
from horatio.models import Troupe, User

UTC_NAME = "UTC"


@dataclass(frozen=True)
class Zones:
    # The troupe's zone now: the one its staff chose, else `default`.
    zone: str
    # Its zone with none chosen: its lead storyteller's, else UTC.
    default: str


def checked(value: str | None) -> str | None:
    """A zone as given, trimmed; None for none ("" clears it). 422 for one Horatio
    doesn't know."""
    value = (value or "").strip()
    if not value:
        return None
    if value not in available_timezones():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{value} is not a time zone Horatio knows."
        )
    return value


def words(zone: str) -> str:
    """A zone as people read it: "America/New York"."""
    return zone.replace("_", " ")


def lead_zone(user: User | None) -> str:
    """A lead storyteller's own zone, or UTC for one who chose none."""
    return (preferences.read(user).time_zone if user else None) or UTC_NAME


def names(db: Session, troupes: Sequence[Troupe]) -> dict[uuid.UUID, Zones]:
    """Each troupe's zone and its default, by its id, asking the database once for all
    their leads."""
    lead_ids = {t.lead_user_id for t in troupes}
    leads = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_(lead_ids)))} if lead_ids else {}
    )
    found: dict[uuid.UUID, Zones] = {}
    for t in troupes:
        default = lead_zone(leads.get(t.lead_user_id))
        found[t.id] = Zones(t.time_zone or default, default)
    return found


def name(db: Session, troupe: Troupe) -> str:
    """The troupe's zone, such as "America/New_York"."""
    return troupe.time_zone or lead_zone(db.get(User, troupe.lead_user_id))


def zone(db: Session, troupe: Troupe | None) -> ZoneInfo:
    """The troupe's zone, to put a moment on its clock; UTC with no troupe."""
    return ZoneInfo(name(db, troupe) if troupe else UTC_NAME)


def column() -> ColumnElement[str]:
    """The troupe's zone in a query over `troupes`, as `name` decides it."""
    lead = (
        select(User.preferences["time_zone"].astext)
        .where(User.id == Troupe.lead_user_id)
        .correlate(Troupe)
        .scalar_subquery()
    )
    return func.coalesce(Troupe.time_zone, lead, UTC_NAME)


def set_zone(db: Session, user: User, troupe: Troupe, value: str | None) -> None:
    """Set the troupe's zone, or with None or "", clear it to use its lead's. The
    caller checks who may."""
    value = checked(value)
    if value == troupe.time_zone:
        return
    troupe.time_zone = value
    if value is None:
        audit.record(
            db, user, "troupe.time_zone_cleared", troupe_id=troupe.id, zone=words(name(db, troupe))
        )
    else:
        audit.record(db, user, "troupe.time_zone_set", troupe_id=troupe.id, zone=words(value))
