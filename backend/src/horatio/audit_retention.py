"""Keeping the audit log from growing without end (#1062): each day the delivery
worker deletes the debug and info events older than the custodian's retention for
their level (horatio.audit), oldest first. A round deletes at most `MOST`, so it is
short and holds few rows locked; what is left waits for the next round.

Notice events are never deleted, and neither is any event whose action is notice
now, even one recorded at a lower level before its action became notice: features
read those back as history. The custodian sees on Custodian › Site when the last
purge ran and how many it deleted.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import AuditEvent, ServerSetting

LAST = "audit_purge"
EVERY = timedelta(days=1)
# Rows one delete takes, and the most one round of the worker deletes; what is
# left waits for the next round, seconds later.
BATCH = 2000
MOST = 10_000


@dataclass
class Purge:
    at: datetime
    deleted: dict[str, int] = field(default_factory=dict)
    # False while more was due than one round deletes.
    finished: bool = True

    @property
    def total(self) -> int:
        return sum(self.deleted.values())


def now() -> datetime:
    """The current time; tests replace this."""
    return datetime.now(UTC)


def last(db: Session) -> Purge | None:
    """The last purge, or None before the first."""
    row = db.get(ServerSetting, LAST)
    value: Any = row.value if row is not None else None
    if not isinstance(value, dict) or "at" not in value:
        return None
    return Purge(
        at=datetime.fromisoformat(value["at"]),
        deleted={k: int(v) for k, v in value.get("deleted", {}).items()},
        finished=bool(value.get("finished", True)),
    )


def purge(db: Session, at: datetime) -> Purge:
    """Delete up to `MOST` events past their level's retention, oldest first."""
    chosen = audit.settings(db)
    done = Purge(at=at)
    room = MOST
    for of in ("debug", "info"):
        days = chosen.days(of)
        if days is None:
            continue
        cutoff = at - timedelta(days=days)
        count = 0
        while room > 0:
            size = min(BATCH, room)
            due = (
                select(AuditEvent.id)
                .where(
                    AuditEvent.level == of,
                    AuditEvent.created_at < cutoff,
                    AuditEvent.action.not_in(audit.NOTICE),
                )
                .order_by(AuditEvent.created_at, AuditEvent.id)
                .limit(size)
            )
            gone = db.execute(delete(AuditEvent).where(AuditEvent.id.in_(due.scalar_subquery())))
            deleted = int(getattr(gone, "rowcount", 0) or 0)
            count += deleted
            room -= deleted
            if deleted < size:
                break
        else:
            done.finished = False
        if count:
            done.deleted[of] = count
    return done


def purge_due(db: Session, at: datetime | None = None) -> Purge | None:
    """Purge if a day has passed since the last one, or the last left some for
    later; record it, and commit. None if not due, or another worker is at it."""
    at = at or now()
    # One worker at a time, until this transaction ends.
    if not db.scalar(select(func.pg_try_advisory_xact_lock(func.hashtext(LAST)))):
        return None
    before = last(db)
    if before is not None and before.finished and at - before.at < EVERY:
        return None
    done = purge(db, at)
    if before is not None and not before.finished:
        # Carrying on with the last: count it all as one.
        for of, count in before.deleted.items():
            done.deleted[of] = done.deleted.get(of, 0) + count
    value = {
        "at": done.at.isoformat(),
        "deleted": done.deleted,
        "finished": done.finished,
    }
    row = db.get(ServerSetting, LAST)
    if row is None:
        db.add(ServerSetting(key=LAST, value=value))
    else:
        row.value = value
    db.commit()
    return done


def purge_due_now() -> None:
    """`purge_due` in a session of its own, for the delivery worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        purge_due(db)
