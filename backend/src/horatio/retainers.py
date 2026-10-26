"""Retainers (core book p. 104): the people who serve a character.

The Retainers background is bought once for each Retainer, each with its own
name (the trait's detail) and up to 5 dots, priced on its own (horatio.sheets).
Each one bought is listed here, with what the sheet does not hold: who they
are, whether they are lost, and the NPC staff linked to them, kept in a row of
the same name. One held without a name, from before Retainers were bought one
by one, is listed until it is named, with nothing kept for it.

Retainers a merit gives are listed too, with their own dots, and are not part
of the background. A row of the background's that no Retainer bought is named
for (listed before they were bought one by one) stays listed with its own dots
until it is removed; no new one can be added. A lost Retainer stays listed (the
book takes its dots away for a while, which staff decide). Staff alone link a
Retainer to an NPC.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, Retainer, Troupe, User
from horatio.permissions import (
    TroupeAction,
    allows,
    can_edit_character,
    can_view_character,
    troupe_role,
)
from horatio.sheets import sheet_rows

BACKGROUND = ("backgrounds", "Retainers")
# Each Retainer of the background has up to 5 dots (p. 104); a merit's can be higher.
MAX_DOTS = 5
MAX_MERIT_DOTS = 10
MAX_LISTED = 30


@dataclass
class Draft:
    """One Retainer as it is to be saved."""

    id: uuid.UUID | None
    name: str
    dots: int
    description: str
    from_merit: str
    lost: str | None
    lost_on: date | None
    npc_id: uuid.UUID | None


@dataclass(frozen=True)
class Listed:
    """One Retainer as listed: bought on the sheet (its name and dots are the
    sheet's), or from a merit or listed before, with the dots kept in its row."""

    row: Retainer | None
    name: str
    dots: int
    bought: bool


def rows(db: Session, character: Character) -> list[Retainer]:
    return list(
        db.scalars(
            select(Retainer)
            .where(Retainer.character_id == character.id)
            .order_by(Retainer.position, Retainer.created_at, Retainer.id)
        )
    )


def bought(db: Session, character: Character) -> list[tuple[str, int]]:
    """Each Retainer bought on the sheet: its name ("" for one held without) and dots."""
    return [
        (row.trait.detail, row.trait.rating or 0)
        for row in sheet_rows(db, character)
        if (row.category.key, row.definition.name) == BACKGROUND and (row.trait.rating or 0) > 0
    ]


def rating(db: Session, character: Character) -> int:
    """The Retainers background's dots, across every Retainer bought."""
    return sum(dots for _, dots in bought(db, character))


def read(db: Session, character: Character) -> list[Listed]:
    """The Retainers bought, in the sheet's order, then those from merits and any
    listed before, in the order they were saved."""
    kept = rows(db, character)
    named = {r.name: r for r in reversed(kept) if not r.from_merit}
    listed: list[Listed] = []
    used: set[uuid.UUID] = set()
    for name, dots in bought(db, character):
        row = named.get(name) if name else None
        if row is not None:
            used.add(row.id)
        listed.append(Listed(row, name, dots, bought=True))
    listed += [Listed(r, r.name, r.dots, bought=False) for r in kept if r.id not in used]
    return listed


def can_link(db: Session, user: User, character: Character) -> bool:
    """Staff who run the character's troupe: the only ones who link an NPC."""
    troupe_id = character.owner_troupe_id if character.kind == "npc" else character.home_troupe_id
    troupe = db.get(Troupe, troupe_id) if troupe_id else None
    if troupe is None:
        return user.is_custodian
    action = TroupeAction.MANAGE_NPCS if character.kind == "npc" else TroupeAction.APPROVE_CHANGES
    return allows(troupe_role(db, user, troupe), action, is_custodian=user.is_custodian)


def can_edit(db: Session, user: User, character: Character) -> bool:
    """A PC's player, or the staff who run its home troupe."""
    return can_edit_character(db, user, character) or can_link(db, user, character)


def viewable_npc(db: Session, user: User | None, retainer: Retainer) -> Character | None:
    if user is None or retainer.npc_id is None:
        return None
    npc = db.get(Character, retainer.npc_id)
    return npc if npc is not None and can_view_character(db, user, npc) else None


def _refuse(code: int, message: str) -> HTTPException:
    return HTTPException(code, message)


def _clean(db: Session, character: Character, drafts: list[Draft]) -> set[str]:
    """Check and tidy the drafts; the names of those bought on the sheet."""
    if len(drafts) > MAX_LISTED:
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "That is too many Retainers.")
    merits = {
        r.definition.name
        for r in sheet_rows(db, character)
        if r.category.key == "merits" and r.trait.rating != 0
    }
    held = dict(bought(db, character))
    # Rows of the background's listed before Retainers were bought one by one.
    before = {r.id for r in rows(db, character) if not r.from_merit and r.name not in held}
    names = [d.name.strip() for d in drafts if not d.from_merit.strip()]
    if len(set(names)) < len(names):
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give each Retainer its own name.")
    for d in drafts:
        d.name = d.name.strip()
        d.description = d.description.strip()
        d.from_merit = d.from_merit.strip()
        if not d.name:
            raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "Name each Retainer.")
        if not d.from_merit and d.name in held:
            d.dots = held[d.name]
        elif not d.from_merit and d.id not in before:
            raise _refuse(
                status.HTTP_409_CONFLICT,
                f"Buy {d.name} on the sheet first: each Retainer is bought on its own,"
                " with its own dots.",
            )
        top = MAX_MERIT_DOTS if d.from_merit else MAX_DOTS
        if not 1 <= d.dots <= top:
            raise _refuse(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{d.name} needs from 1 to {top} dots.",
            )
        if d.from_merit and d.from_merit not in merits:
            raise _refuse(
                status.HTTP_409_CONFLICT, f"{character.name} does not have {d.from_merit}."
            )
        if d.lost is None:
            d.lost_on = None
        elif d.lost_on is None:
            d.lost_on = date.today()
    return {name for name in held if name}


def _link(db: Session, character: Character, npc_id: uuid.UUID) -> None:
    npc = db.get(Character, npc_id)
    troupe_id = character.owner_troupe_id if character.kind == "npc" else character.home_troupe_id
    if npc is None or npc.kind != "npc" or troupe_id is None or npc.owner_troupe_id != troupe_id:
        raise _refuse(
            status.HTTP_409_CONFLICT, "A Retainer links to an NPC of the character's home troupe."
        )


def replace(
    db: Session, user: User, character: Character, drafts: list[Draft], *, link: bool
) -> list[Listed]:
    """Save the whole list, logging what changed. Without `link`, each kept
    Retainer keeps the NPC it had and a new one has none."""
    on_sheet = _clean(db, character, drafts)
    held = {r.id: r for r in rows(db, character)}
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    log = {"character_id": character.id, "troupe_id": troupe_id}
    kept: set[uuid.UUID] = set()
    for position, d in enumerate(drafts):
        row = held.get(d.id) if d.id else None
        if row is None:
            row = Retainer(character_id=character.id, name=d.name, dots=d.dots)
            db.add(row)
            was = None
        else:
            was = (row.name, row.dots, row.description, row.lost, row.npc_id)
            kept.add(row.id)
        row.position = position
        row.name, row.dots, row.description = d.name, d.dots, d.description
        row.from_merit, row.lost, row.lost_on = d.from_merit, d.lost, d.lost_on
        if link:
            if d.npc_id is not None and d.npc_id != row.npc_id:
                _link(db, character, d.npc_id)
            row.npc_id = d.npc_id
        db.flush()
        facts = {"name": row.name, "dots": row.dots}
        if was is None:
            audit.record(db, user, "retainer.added", **log, **facts)
            if row.npc_id:
                audit.record(db, user, "retainer.linked", **log, **facts)
            continue
        # A bought Retainer's dots change on the sheet, whose own log has them.
        moved = was[1] != row.dots and (bool(d.from_merit) or d.name not in on_sheet)
        if (was[0], was[2]) != (row.name, row.description) or moved:
            audit.record(db, user, "retainer.changed", **log, **facts, was=was[0], was_dots=was[1])
        if was[3] != row.lost and row.lost:
            audit.record(db, user, "retainer.lost", **log, **facts, how=row.lost)
        elif was[3] != row.lost:
            audit.record(db, user, "retainer.restored", **log, **facts)
        if was[4] != row.npc_id:
            audit.record(
                db, user, "retainer.linked" if row.npc_id else "retainer.unlinked", **log, **facts
            )
    for retainer_id, row in held.items():
        if retainer_id not in kept:
            audit.record(db, user, "retainer.removed", **log, name=row.name, dots=row.dots)
            db.delete(row)
    db.flush()
    return read(db, character)
