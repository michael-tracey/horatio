"""Departures as the court knows them (#749): what a player who keeps the boon ledger
in play, the Harpy (#688) or a Lesser Harpy (#689), may learn of who has left.

Why a character retired is out-of-character knowledge (horatio.leaving): Inactive
says only that its player stopped, nothing in game. Whether someone left at all is in
game only as far as the court knows it, and what the court knows is what the troupe's
Who's Who shows (horatio.whos_who): the retired characters its players chose to list
under "No longer with us", each with why it left.

So, as the court knows it, a character is:
- **in play** while it is, and while it is retired but not listed: the court hasn't
  heard (`ACTIVE`);
- **gone**, with why, when the Who's Who lists it as Final Death or Off-field;
- **gone**, without why, when it lists it as Inactive (`GONE`): Inactive is never
  shown as a reason.

Staff keep the full view (horatio.boons.standing). `listed` reads a troupe's list once;
`standing` and `departed` then answer for each character without the database, so a
ledger page asks once for all of its boons.
"""

import uuid
from collections.abc import Collection

from sqlalchemy.orm import Session

from horatio import whos_who
from horatio.models import Character, Troupe

ACTIVE = "active"
# Gone, as the court knows it, without a reason it would know (horatio.boons.DEPARTED).
GONE = "retired"
# The reasons the court may hear: those that say something in game.
IN_GAME = ("final_death", "off_field")


def listed(db: Session, troupe: Troupe) -> frozenset[uuid.UUID]:
    """The characters the troupe's Who's Who lists under "No longer with us"."""
    return frozenset(c.id for c in whos_who.departed(db, troupe))


def standing(character: Character | None, known: Collection[uuid.UUID]) -> str | None:
    """The character's standing as the court knows it, given the troupe's `listed`
    characters: "active", "final_death", "off_field", or "retired" (gone, without a
    reason the court would know). None for a name only."""
    if character is None:
        return None
    if character.status != "retired" or character.id not in known:
        return ACTIVE
    return character.left_reason if character.left_reason in IN_GAME else GONE


def departed(character: Character | None, known: Collection[uuid.UUID]) -> bool:
    """Gone from play, as the court knows it."""
    found = standing(character, known)
    return found is not None and found != ACTIVE


def departure_as_court_knows(db: Session, character: Character, troupe: Troupe) -> str | None:
    """One character's standing as the troupe's court knows it: for a single answer.
    For many, read `listed` once and ask `standing`."""
    return standing(character, listed(db, troupe))
