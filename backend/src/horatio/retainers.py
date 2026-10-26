"""Retainers (core book p. 104): the people who serve a character, listed with
their own dots under the Retainers background.

The dots across the listed Retainers should add up to the background's rating;
the list never changes the rating, and a lost Retainer stays listed (the book
takes its dots away for a while, which staff decide). Retainers a merit gives
are listed too, but are not counted in the background's dots. Staff alone link
a Retainer to an NPC.
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


def read(db: Session, character: Character) -> list[Retainer]:
    return list(
        db.scalars(
            select(Retainer)
            .where(Retainer.character_id == character.id)
            .order_by(Retainer.position, Retainer.created_at, Retainer.id)
        )
    )


def rating(db: Session, character: Character) -> int:
    """The Retainers background's rating on the sheet."""
    for row in sheet_rows(db, character):
        if (row.category.key, row.definition.name) == BACKGROUND:
            return row.trait.rating or 0
    return 0


def counted(retainers: list[Retainer]) -> int:
    """The dots the background's rating should match: those not from a merit."""
    return sum(r.dots for r in retainers if not r.from_merit)


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


def _clean(db: Session, character: Character, drafts: list[Draft]) -> None:
    if len(drafts) > MAX_LISTED:
        raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "That is too many Retainers.")
    merits = {
        r.definition.name
        for r in sheet_rows(db, character)
        if r.category.key == "merits" and r.trait.rating != 0
    }
    for d in drafts:
        d.name = d.name.strip()
        d.description = d.description.strip()
        d.from_merit = d.from_merit.strip()
        if not d.name:
            raise _refuse(status.HTTP_422_UNPROCESSABLE_CONTENT, "Name each Retainer.")
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


def _link(db: Session, character: Character, npc_id: uuid.UUID) -> None:
    npc = db.get(Character, npc_id)
    troupe_id = character.owner_troupe_id if character.kind == "npc" else character.home_troupe_id
    if npc is None or npc.kind != "npc" or troupe_id is None or npc.owner_troupe_id != troupe_id:
        raise _refuse(
            status.HTTP_409_CONFLICT, "A Retainer links to an NPC of the character's home troupe."
        )


def replace(
    db: Session, user: User, character: Character, drafts: list[Draft], *, link: bool
) -> list[Retainer]:
    """Save the whole list, logging what changed. Without `link`, each kept
    Retainer keeps the NPC it had and a new one has none."""
    _clean(db, character, drafts)
    held = {r.id: r for r in read(db, character)}
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
        if was[:3] != (row.name, row.dots, row.description):
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
