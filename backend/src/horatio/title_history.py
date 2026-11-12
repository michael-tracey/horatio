"""Title history: who held each title in a troupe, and when (#712).

Horatio keeps the titles held now in `CharacterTitle`, and nothing of when. Each
holding is also kept here as a `TitleHolding`, from when it began to when it ended,
so a troupe can see its court over time. horatio.titles writes it at every change:

- a title begins **given** (by staff) or **chosen** (by the character's player);
- it ends **taken** (by staff), **given_up** (by the player), **retired** (retiring
  gives up every title), **left** (the character left the troupe, or the troupe
  closed), **removed** (the troupe removed a title of its own), or **deleted** (the
  character was deleted; the holding stays under its name).

Holdings from before this was kept were recovered from the audit log by the
migration that began it (0186_title_history.replay), and marked `backfilled`.

Real dates are always kept; staff may add the in-game dates.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.orm import Session

from horatio import social_age
from horatio.models import (
    AuditEvent,
    Character,
    HeldStatus,
    TitleHolding,
    Troupe,
    TroupeMembership,
)
from horatio.sheets import rules_for

# --- as titles change ---------------------------------------------------------------------------


def began(db: Session, troupe_id: uuid.UUID, character: Character, name: str, how: str) -> None:
    """The character began to hold `name` in the troupe, given or chosen."""
    db.add(
        TitleHolding(
            troupe_id=troupe_id,
            character_id=character.id,
            character_name=character.name,
            name=name,
            began_at=func.now(),
            began_how=how,
        )
    )
    db.flush()


def ended(
    db: Session,
    how: str,
    *,
    troupe_id: uuid.UUID | None = None,
    character_id: uuid.UUID | None = None,
    names: Iterable[str] | None = None,
) -> None:
    """The holdings still open that match end now, `how`: those of the character, in
    the troupe, of these titles; whichever of the three are given."""
    open_: list[ColumnElement[bool]] = [TitleHolding.ended_at.is_(None)]
    if troupe_id is not None:
        open_.append(TitleHolding.troupe_id == troupe_id)
    if character_id is not None:
        open_.append(TitleHolding.character_id == character_id)
    if names is not None:
        open_.append(TitleHolding.name.in_(list(names)))
    db.execute(
        update(TitleHolding)
        .where(*open_)
        .values(ended_at=func.now(), ended_how=how)
        .execution_options(synchronize_session=False)
    )
    db.flush()


# --- the court over time --------------------------------------------------------------------------

# The status changes the log records: one gained, and the ways one goes.
GAINED = "status.added"
LOST_ONE = ("status.spent", "status.removed", "status.expired", "status.given_up")
LOST_MANY = ("status.lost", "status.cleared")


@dataclass(frozen=True)
class StatusPoint:
    """How many fleeting and negative status a character held from `at` on."""

    at: datetime
    fleeting: int
    negative: int


@dataclass(frozen=True)
class StatusLine:
    character_id: uuid.UUID
    name: str
    clan: str | None
    points: list[StatusPoint]
    gained: int
    lost: int


def holdings(db: Session, troupe: Troupe) -> list[TitleHolding]:
    """Every holding of a title in the troupe, oldest first."""
    return list(
        db.scalars(
            select(TitleHolding)
            .where(TitleHolding.troupe_id == troupe.id)
            .order_by(TitleHolding.began_at, TitleHolding.id)
        )
    )


def members(db: Session, troupe: Troupe) -> list[uuid.UUID]:
    """The troupe's characters now, home and visiting, for clan colours."""
    return list(
        db.scalars(
            select(TroupeMembership.character_id).where(
                TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
            )
        )
    )


def status_type(rules: Mapping[str, Any], seen: Mapping[str, str], name: str) -> str:
    """ "fleeting" or "negative": as the log said when it was gained, else as the rules say."""
    if name in seen:
        return seen[name]
    found = rules.get(name)
    return str(getattr(found, "type", "Fleeting")).lower()


def status_lines(db: Session, troupe: Troupe) -> list[StatusLine]:
    """Each home character's fleeting and negative status over time, worked back
    from what it holds now through the log: a gain before now was one fewer held
    before it, a loss one more. Status lives on the character, so its whole log
    counts, wherever it was gained."""
    home = list(
        db.scalars(
            select(Character).where(
                Character.home_troupe_id == troupe.id, Character.status == "active"
            )
        )
    )
    if not home:
        return []
    ids = [c.id for c in home]
    held: dict[uuid.UUID, list[str]] = {i: [] for i in ids}
    for character_id, name in db.execute(
        select(HeldStatus.character_id, HeldStatus.name).where(HeldStatus.character_id.in_(ids))
    ):
        held[character_id].append(name)
    events = list(
        db.execute(
            select(
                AuditEvent.character_id, AuditEvent.action, AuditEvent.data, AuditEvent.created_at
            )
            .where(
                AuditEvent.character_id.in_(ids),
                AuditEvent.action.in_((GAINED, *LOST_ONE, *LOST_MANY)),
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        )
    )
    standing = social_age.standings(db, ids)
    out: list[StatusLine] = []
    for character in sorted(home, key=lambda c: c.name):
        mine = [e for e in events if e.character_id == character.id]
        if not mine and not held[character.id]:
            continue
        rules = rules_for(db, character).rule_set.statuses
        seen = {
            str(e.data.get("status")): str(e.data.get("type") or "fleeting")
            for e in mine
            if e.action == GAINED and e.data.get("status")
        }
        count = {"fleeting": 0, "negative": 0}
        for name in held[character.id]:
            kind = status_type(rules, seen, name)
            if kind in count:
                count[kind] += 1
        # Newest first: what it holds after each change is what it holds now with
        # every later change undone.
        after: list[StatusPoint] = []
        gained = lost = 0
        for e in mine:
            after.append(StatusPoint(e.created_at, count["fleeting"], count["negative"]))
            if e.action == GAINED:
                names, step = [str(e.data.get("status") or "")], -1
                gained += 1
            elif e.action in LOST_ONE:
                names, step = [str(e.data.get("status") or "")], 1
                lost += 1
            else:
                names = [n.strip() for n in str(e.data.get("statuses") or "").split(",")]
                names, step = [n for n in names if n], 1
                lost += len(names)
            for name in names:
                kind = status_type(rules, seen, name)
                if kind in count:
                    count[kind] = max(0, count[kind] + step)
        # What it held before the first change, from when the character was made.
        first = StatusPoint(character.created_at, count["fleeting"], count["negative"])
        points = [first, *reversed(after)]
        clan = standing[character.id].clan if character.id in standing else None
        out.append(StatusLine(character.id, character.name, clan, points, gained, lost))
    return out
