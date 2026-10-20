"""Handles (issue #103): what people find and see each other by, instead of an
email, which only its owner and the custodian ever see.

A handle is 3 to 30 letters, numbers, underscores and hyphens, unique regardless
of case and shown as its owner typed it. Every account has one, chosen at
sign-up or made from the display name, and its owner can change it in Settings
at most once in 30 days. Changing only its case is not a change.

A handle someone changes from is held for them for 90 days: no one else can
take it, and finding someone by it still finds them, so links and memories of
it keep working. They can take it back themselves.
"""

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from itertools import count

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session

from horatio.audit import record
from horatio.models import FormerHandle, User
from horatio.sheets import conflict, unprocessable

HANDLE = re.compile(r"[A-Za-z0-9_-]{3,30}")
MAX_LENGTH = 30
# How often someone can change their handle, and how long an old one is held.
CHANGE_EVERY = timedelta(days=30)
HELD_FOR = timedelta(days=90)
# What a handle made from a name too short to make one starts as.
FALLBACK = "player"


def clean(handle: str) -> str:
    """The handle as typed, without surrounding spaces or a leading @. Refused
    unless it is one."""
    handle = handle.strip().removeprefix("@")
    if not HANDLE.fullmatch(handle):
        raise unprocessable("A handle is 3 to 30 letters, numbers, underscores and hyphens.")
    return handle


def holder(db: Session, handle: str) -> User | None:
    """Whoever has the handle, or held it in the last 90 days, regardless of case."""
    wanted = handle.strip().removeprefix("@").lower()
    current = db.scalar(select(User).where(func.lower(User.handle) == wanted))
    if current is not None:
        return current
    return db.scalar(
        select(User)
        .join(FormerHandle, FormerHandle.user_id == User.id)
        .where(func.lower(FormerHandle.handle) == wanted, FormerHandle.held_until > func.now())
        .order_by(FormerHandle.held_until.desc())
        .limit(1)
    )


def from_name(name: str) -> str:
    """A handle's worth of a display name: "Agnès Fairweather" is agnes_fairweather."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    made = re.sub(r"[^a-z0-9_-]+", "_", plain).strip("_-")[:MAX_LENGTH]
    return made if len(made) >= 3 else FALLBACK


def suggest(db: Session, name: str) -> str:
    """A free handle made from a display name: agnes, or agnes2 if that is taken."""
    base = from_name(name)
    for n in count(1):
        number = str(n) if n > 1 else ""
        handle = base[: MAX_LENGTH - len(number)] + number
        if holder(db, handle) is None:
            return handle
    raise AssertionError("unreachable")


def choose(db: Session, handle: str) -> str:
    """A handle chosen for a new account, if no one has it or holds it."""
    handle = clean(handle)
    if holder(db, handle) is not None:
        raise conflict(f"Someone already has the handle {handle}.")
    return handle


def next_change(user: User, now: datetime | None = None) -> datetime | None:
    """When the person can next change their handle; None if they can now."""
    if user.handle_changed_at is None:
        return None
    allowed = user.handle_changed_at + CHANGE_EVERY
    return allowed if allowed > (now or datetime.now(UTC)) else None


def change(db: Session, user: User, wanted: str) -> None:
    """Change the person's own handle, holding the old one for them."""
    handle = clean(wanted)
    if handle.lower() == user.handle.lower():
        user.handle = handle
        return
    wait = next_change(user)
    if wait is not None:
        raise conflict(f"You can change your handle again on {wait.day} {wait:%B %Y}.")
    other = holder(db, handle)
    if other is not None and other.id != user.id:
        raise conflict(f"Someone already has the handle {handle}.")
    now = datetime.now(UTC)
    # Taking back one of their own old handles: it is theirs again, not held.
    db.execute(
        delete(FormerHandle).where(
            FormerHandle.user_id == user.id, func.lower(FormerHandle.handle) == handle.lower()
        )
    )
    db.add(FormerHandle(user_id=user.id, handle=user.handle, held_until=now + HELD_FOR))
    record(db, user, "account.handle_changed", from_handle=user.handle, handle=handle)
    user.handle = handle
    user.handle_changed_at = now


def find(db: Session, q: str, limit: int = 10) -> list[User]:
    """People for a type-ahead: handles starting with `q` first, then display names
    with it in them."""
    q = q.strip().removeprefix("@").lower()
    if not q:
        return []
    by_handle = func.lower(User.handle).startswith(q, autoescape=True)
    return list(
        db.scalars(
            select(User)
            .where(or_(by_handle, func.lower(User.display_name).contains(q, autoescape=True)))
            .order_by(case((by_handle, 0), else_=1), func.lower(User.handle))
            .limit(limit)
        )
    )
