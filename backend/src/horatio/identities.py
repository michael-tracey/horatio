"""Alternate Identity (core pp. 98-99): a cover identity, bought once for each,
with its own name (the trait's detail) and dots, priced on its own
(horatio.sheets). Each is listed with what its rating means and, kept here by
its name, the sect or group that has Accepted it, if any (p. 310).
"""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import AlternateIdentity, Character, User
from horatio.sheets import sheet_rows

BACKGROUND = ("backgrounds", "Alternate Identity")

# What each rating stands up to, in short (p. 99).
LINES = {
    1: "Shallow: a driver's licence or the like, enough for a quick internet search.",
    2: "Well grounded: papers and records that hold up to a minor criminal investigation.",
    3: "Well established: a long history, friends and witnesses; it stands up to all but the"
    " toughest scrutiny.",
    4: "Built to infiltrate another clan or sect, with a living sire who claims you.",
    5: "A respected figure, in high office or swaying another clan or sect; it passes even"
    " supernatural checks.",
}
PAGE = "99"


@dataclass(frozen=True)
class Identity:
    name: str
    dots: int
    line: str
    accepted_by: str


def _kept(db: Session, character: Character) -> dict[str, AlternateIdentity]:
    return {
        r.name: r
        for r in db.scalars(
            select(AlternateIdentity).where(AlternateIdentity.character_id == character.id)
        )
    }


def read(db: Session, character: Character) -> list[Identity]:
    """Each identity bought, in the sheet's order ("" for one held without a name)."""
    kept = _kept(db, character)
    found: list[Identity] = []
    for row in sheet_rows(db, character):
        if (row.category.key, row.definition.name) != BACKGROUND or not row.trait.rating:
            continue
        name, dots = row.trait.detail, row.trait.rating
        held = kept.get(name) if name else None
        found.append(Identity(name, dots, LINES[min(dots, 5)], held.accepted_by if held else ""))
    return found


def accept(db: Session, user: User, character: Character, accepted: dict[str, str]) -> None:
    """Say which sect or group has Accepted each named identity ("" for none)."""
    named = {i.name for i in read(db, character) if i.name}
    kept = _kept(db, character)
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    for name, by in accepted.items():
        if name not in named:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{character.name} has no Alternate Identity called {name or 'that'}.",
            )
        by = by.strip()
        row = kept.get(name)
        if (row.accepted_by if row else "") == by:
            continue
        if row is None:
            row = AlternateIdentity(character_id=character.id, name=name)
            db.add(row)
        row.accepted_by = by
        audit.record(
            db,
            user,
            "identity.accepted" if by else "identity.unaccepted",
            character_id=character.id,
            troupe_id=troupe_id,
            name=name,
            by=by,
        )
    db.flush()
