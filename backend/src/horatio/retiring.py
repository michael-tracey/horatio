"""What retiring a character could tell others before they should know (issue #748).

Retiring is the player's to do (horatio.leaving), but some of what it shows reaches
other players: the Who's Who lists the character under "No longer with us" with why
it left, remembrances ask its whole home troupe for a memory of it, and a withdrawal
of its dots from a shared background shows the other sharers it left. At Final Death
that can tell a thrall its regnant is dead while the bond still fades unfelt (MET: VTM
p. 296, issue #662). #659's audit lists these.

This gathers what the dialog warns of, as the person retiring may know it: the
troupe's running staff see every bond and shared background; the character's player
only the bonds known to the regnant, and the shared backgrounds it puts dots in. A
warning never blocks: whether to list it, and when, stays theirs.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from horatio import bonds, shared_backgrounds
from horatio.models import Character, Troupe, User


@dataclass
class Thrall:
    """A bond the character is the regnant of, still felt: at Final Death it fades
    over a month, and its thrall feels it all the while. One already fading still
    counts, since listing a dead regnant then is what tells the thrall."""

    name: str
    troupe: str


@dataclass
class Sharers:
    """A shared background the character still has dots in, and the others there."""

    name: str
    background: str
    troupe: str
    others: list[str]


@dataclass
class Retiring:
    thralls: list[Thrall] = field(default_factory=list)
    shared: list[Sharers] = field(default_factory=list)
    # The person is its troupe's running staff (or the custodian): they keep the
    # Who's Who listing, remembrances and shared backgrounds' logs.
    staff: bool = False


def troupe_of(db: Session, character: Character) -> Troupe | None:
    """Its home troupe, or the troupe an NPC belongs to."""
    troupe_id: uuid.UUID | None = character.home_troupe_id or character.owner_troupe_id
    return db.get(Troupe, troupe_id) if troupe_id else None


def what_it_would_tell(db: Session, user: User, character: Character) -> Retiring:
    """The bonds and shared backgrounds that retiring `character` could give away,
    as `user` may know of them. Reads only: a fade past its day is left to whoever
    next writes (bonds.seen_by without settling)."""
    found = Retiring()
    troupe = troupe_of(db, character)
    found.staff = user.is_custodian or (troupe is not None and bonds.can_manage(db, user, troupe))
    for seen in bonds.seen_by(db, user, character, settle=False):
        regnant = seen.regnant.character
        if regnant is not None and regnant.id == character.id and seen.bond.status in bonds.OPEN:
            found.thralls.append(Thrall(seen.thrall.shown, seen.troupe.name))
    for shared in shared_backgrounds.of_character(db, character.id):
        if not shared_backgrounds.can_see(db, user, shared):
            continue
        standing = shared_backgrounds.standing(shared_backgrounds.entries(db, shared))
        if standing.dots_of(character.id) <= 0:
            continue
        others = [s.name for s in standing.sharers if s.character_id != character.id and s.dots > 0]
        if others:
            home = db.get_one(Troupe, shared.troupe_id)
            found.shared.append(Sharers(shared.name, shared.background, home.name, others))
    return found
