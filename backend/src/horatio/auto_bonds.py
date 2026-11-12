"""Blood bonds Horatio knows without anyone recording them (#663), while the troupe's
Blood bonds setting isn't off (horatio.bonds).

- **The Embrace**: every childe has a one-drink bond to their sire, for the Embrace
  itself takes a drink of the sire's blood (MET: VTM p. 295). An Embrace made in play
  (horatio.embrace) adds it, on the night of the Embrace.
- **The sire on the sheet** (#739): a vampire whose sire is given on the character
  (horatio.sire_lines, #707) but who has no Embrace in play has the same bond to that
  sire. It is only ever filled in, from the day the character was made in Horatio: the
  sire field says who, never when. A sire kept from players stays so: the bond is the
  childe's own, which their player sees as they see their sire, and the regnant's
  player sees it only once staff mark it known.
- **Domitors**: a ghoul is bound to their domitor (p. 296, "Playing a Ghoul"), fully:
  a ghoul changes domitor only once the old bond has faded, by "achieving a full blood
  bond to the new vampire". Setting a ghoul's domitor (horatio.domitors) adds a full
  bond to them; changing it ends the bond to the old one, as the book has it faded
  already, and adds the new. A ghoul made before any troupe accepted it gets its bond
  when its home troupe accepts it.
- **Retainers**: a ghoul Retainer is a ghoul like any other, bound fully to the
  vampire it serves, the character whose Retainer it is. The thrall is the NPC staff
  linked to the Retainer, or the Retainer by name; linking it later moves the bond to
  the NPC. Only a vampire's Retainers: a ghoul's own ghoul Retainer has no blood of its
  master's to drink.

Each is entered as a bond already standing, at its level, with the book's reason, as
running staff would enter one (`bonds.enter_bond`), and logged as added by Horatio.
None is added where the two already have a bond still felt, where a full bond to
someone else makes the thrall immune (the Errata's p. 295), or where either side is
retired. Characters made before the setting was switched on get theirs only when the
troupe's running staff choose to fill them in (`known` and `fill_in`), from the list
of what would be added.

A bond Horatio adds keeps the troupe's secrecy: the thrall's player sees it, as their
own; the regnant's player does only once staff mark it known, but for a Retainer's,
whose regnant's player made the Retainer a ghoul themself.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from horatio import bonds
from horatio.models import BloodBond, BondEntry, Character, Embrace, Retainer, Troupe, User
from horatio.rules.splats import SPLATS

EMBRACE = "embrace"
SIRE = "sire"
DOMITOR = "domitor"
RETAINER = "retainer"
# How deep each kind of bond stands from the start, and the book's reason.
LEVELS = {EMBRACE: 1, SIRE: 1, DOMITOR: bonds.FULL, RETAINER: bonds.FULL}
REASONS = {
    EMBRACE: "Every childe has a one-drink bond to their sire, from the Embrace (p. 295).",
    SIRE: "Every childe has a one-drink bond to their sire, from the Embrace (p. 295).",
    DOMITOR: "A ghoul is fully bound to their domitor (p. 296).",
    RETAINER: "A ghoul Retainer is fully bound to the vampire they serve (p. 296).",
}
DOMITOR_MOVED = "Bound to a new domitor: the bond to the old one had faded (p. 296)."


@dataclass(frozen=True)
class Known:
    """A bond Horatio can work out: whose to whom, why, and from which night."""

    why: str
    thrall: bonds.Party
    regnant: bonds.Party
    night: date

    @property
    def level(self) -> int:
        return LEVELS[self.why]

    @property
    def reason(self) -> str:
        return REASONS[self.why]


def troupe_of(db: Session, character: Character) -> Troupe | None:
    """The troupe whose bonds the character's go in: an NPC's own troupe, or a PC's
    home troupe once one has accepted it. None while it has neither, or while that
    troupe doesn't track bonds."""
    troupe_id = character.owner_troupe_id if character.kind == "npc" else character.home_troupe_id
    troupe = db.get(Troupe, troupe_id) if troupe_id is not None else None
    if troupe is None or not bonds.tracked(troupe):
        return None
    return troupe


def side(db: Session, troupe: Troupe, character: Character | None, name: str) -> bonds.Party:
    """One side as the troupe names it: the character, if it is one of the troupe's;
    otherwise by name, as for anyone not in it."""
    if character is not None and bonds.in_troupe(db, troupe, character):
        return bonds.Party(character, "")
    return bonds.Party(None, (character.name if character is not None else name).strip())


def retired(party: bonds.Party) -> bool:
    return party.character is not None and party.character.status == "retired"


def is_ghoul(character: Character) -> bool:
    return SPLATS[character.splat].has_domitor


def day_of(moment: datetime) -> date:
    return moment.astimezone(UTC).date()


def wanted(db: Session, troupe: Troupe, known: Known) -> bool:
    """Whether the bond is still to add: the two aren't one, aren't retired, have no
    bond still felt between them, and the thrall isn't immune to it."""
    thrall, regnant = known.thrall, known.regnant
    if not thrall.shown or not regnant.shown:
        return False
    if (thrall.character, thrall.name.lower()) == (regnant.character, regnant.name.lower()):
        return False
    if retired(thrall) or retired(regnant):
        return False
    if regnant.character is not None and not bonds.is_vampire(regnant.character):
        return False
    if bonds.open_bond(db, troupe, thrall, regnant) is not None:
        return False
    return bonds.immune_to(db, troupe, thrall, regnant) is None


def add(db: Session, user: User, troupe: Troupe, known: Known) -> BloodBond | None:
    """Enter the bond, if it is still to add; the bond, or None."""
    if not bonds.tracked(troupe) or not wanted(db, troupe, known):
        return None
    bond = bonds.new_bond(db, user, troupe, known.thrall, known.regnant)
    # The regnant's player made their Retainer a ghoul: they plainly know of it.
    bond.known_to_regnant = known.why == RETAINER
    db.add(
        BondEntry(
            bond_id=bond.id,
            kind="entered",
            night=min(known.night, bonds.today()),
            source="staff",
            level=known.level,
            note=known.reason,
            recorded_by=user.id,
        )
    )
    db.flush()
    bonds.log(
        db,
        user,
        "bond.automatic",
        bond,
        level=bonds.LEVELS[known.level],
        night=bonds.when(known.night),
        reason=known.reason,
    )
    if known.level == bonds.FULL:
        bonds.wipe_lesser(db, user, bond)
    return bond


# --- as things happen --------------------------------------------------------------------


def embraced(
    db: Session,
    user: User,
    childe: Character,
    sire: Character | None,
    sire_name: str,
    night: date,
) -> BloodBond | None:
    """A ghoul was Embraced in play: the childe's one-drink bond to their sire."""
    troupe = troupe_of(db, childe)
    if troupe is None:
        return None
    known = Known(EMBRACE, side(db, troupe, childe, ""), side(db, troupe, sire, sire_name), night)
    return add(db, user, troupe, known)


def sire_known(db: Session, troupe: Troupe, childe: Character) -> Known | None:
    """A vampire's one-drink bond to the sire its sheet names (#707), from the day it
    was made in Horatio; None for one with no sire given."""
    if not bonds.is_vampire(childe) or (childe.sire_id is None and not childe.sire_name.strip()):
        return None
    sire = db.get(Character, childe.sire_id) if childe.sire_id is not None else None
    return Known(
        SIRE,
        side(db, troupe, childe, ""),
        side(db, troupe, sire, childe.sire_name),
        day_of(childe.created_at),
    )


def domitor_known(db: Session, troupe: Troupe, ghoul: Character) -> Known | None:
    """The ghoul's full bond to their domitor, from today."""
    if not is_ghoul(ghoul) or (ghoul.domitor_id is None and not ghoul.domitor_name.strip()):
        return None
    domitor = db.get(Character, ghoul.domitor_id) if ghoul.domitor_id is not None else None
    return Known(
        DOMITOR,
        side(db, troupe, ghoul, ""),
        side(db, troupe, domitor, ghoul.domitor_name),
        bonds.today(),
    )


def domitor_changed(
    db: Session,
    user: User,
    ghoul: Character,
    was_id: uuid.UUID | None,
    was_name: str,
) -> None:
    """The ghoul's domitor was set: the bond to the one before ends, as faded before
    the change (p. 296), and the ghoul is fully bound to the new one."""
    troupe = troupe_of(db, ghoul)
    if troupe is None:
        return
    if (was_id, was_name.strip().lower()) != (ghoul.domitor_id, ghoul.domitor_name.strip().lower()):
        was = db.get(Character, was_id) if was_id is not None else None
        if was is not None or was_name.strip():
            old = bonds.open_bond(
                db, troupe, side(db, troupe, ghoul, ""), side(db, troupe, was, was_name)
            )
            if old is not None:
                bonds.end(db, user, old, "ended", DOMITOR_MOVED)
                db.flush()
                bonds.log(db, user, "bond.domitor_moved", old, reason=DOMITOR_MOVED)
    known = domitor_known(db, troupe, ghoul)
    if known is not None:
        add(db, user, troupe, known)


def retainer_known(db: Session, troupe: Troupe, owner: Character, row: Retainer) -> Known | None:
    """A vampire's ghoul Retainer's full bond to them."""
    if not row.ghoul or not bonds.is_vampire(owner):
        return None
    npc = db.get(Character, row.npc_id) if row.npc_id is not None else None
    return Known(
        RETAINER,
        side(db, troupe, npc, row.name),
        side(db, troupe, owner, ""),
        day_of(row.created_at),
    )


def move_to_npc(db: Session, user: User, troupe: Troupe, owner: Character, row: Retainer) -> None:
    """A Retainer bound by name was linked to an NPC: its bond goes to the NPC."""
    if row.npc_id is None:
        return
    npc = db.get(Character, row.npc_id)
    if npc is None or not bonds.in_troupe(db, troupe, npc):
        return
    regnant = side(db, troupe, owner, "")
    named = bonds.open_bond(db, troupe, bonds.Party(None, row.name.strip()), regnant)
    if named is None or bonds.open_bond(db, troupe, bonds.Party(npc, ""), regnant) is not None:
        return
    named.thrall_id = npc.id
    named.thrall_name = ""
    db.flush()
    bonds.log(db, user, "bond.retainer_linked", named, retainer=row.name)


def retainers_saved(db: Session, user: User, owner: Character) -> None:
    """The character's Retainers were saved: each ghoul Retainer of a vampire is fully
    bound to them, its bond following it to the NPC it is linked to."""
    troupe = troupe_of(db, owner)
    if troupe is None or not bonds.is_vampire(owner):
        return
    for row in db.scalars(select(Retainer).where(Retainer.character_id == owner.id)):
        known = retainer_known(db, troupe, owner, row)
        if known is None:
            continue
        move_to_npc(db, user, troupe, owner, row)
        add(db, user, troupe, known)


def accepted(db: Session, user: User, character: Character) -> None:
    """A troupe accepted the character as home: the bonds it already holds by rule, a
    ghoul's to their domitor and a vampire's ghoul Retainers' to them, go in its
    bonds."""
    troupe = troupe_of(db, character)
    if troupe is None:
        return
    known = domitor_known(db, troupe, character)
    if known is not None:
        add(db, user, troupe, known)
    retainers_saved(db, user, character)


# --- filling in what the troupe already holds --------------------------------------------


def members(db: Session, troupe: Troupe) -> list[Character]:
    """The troupe's characters still played: its NPCs, and those at home in it."""
    return list(
        db.scalars(
            select(Character)
            .where(
                Character.status == "active",
                or_(
                    Character.owner_troupe_id == troupe.id,
                    and_(Character.kind == "pc", Character.home_troupe_id == troupe.id),
                ),
            )
            .order_by(Character.name)
        )
    )


def known(db: Session, troupe: Troupe) -> list[Known]:
    """Every bond Horatio can work out for the troupe that it doesn't keep yet: its
    characters' Embraces, the sires their sheets name where no Embrace was made in play,
    ghouls' domitors, and vampires' ghoul Retainers."""
    found: list[Known] = []
    seen: set[tuple[object, str, object, str]] = set()

    def keep(item: Known | None) -> None:
        if item is None or not wanted(db, troupe, item):
            return
        key = (
            item.thrall.character,
            item.thrall.name.lower(),
            item.regnant.character,
            item.regnant.name.lower(),
        )
        if key not in seen:
            seen.add(key)
            found.append(item)

    characters = members(db, troupe)
    by_id = {c.id: c for c in characters}
    embraced: set[uuid.UUID] = set()
    for record in db.scalars(
        select(Embrace)
        .where(Embrace.result == "vampire", Embrace.character_id.in_(list(by_id)))
        .order_by(Embrace.embraced_on, Embrace.id)
    ):
        embraced.add(record.character_id)
        sire = db.get(Character, record.sire_id) if record.sire_id is not None else None
        childe = by_id[record.character_id]
        keep(
            Known(
                EMBRACE,
                side(db, troupe, childe, ""),
                side(db, troupe, sire, record.sire_name),
                record.embraced_on,
            )
        )
    for character in characters:
        # An Embrace in play already gives the childe theirs, from its night.
        if character.id not in embraced:
            keep(sire_known(db, troupe, character))
    for character in characters:
        domitor = domitor_known(db, troupe, character)
        if domitor is not None:
            keep(Known(DOMITOR, domitor.thrall, domitor.regnant, day_of(character.created_at)))
    for character in characters:
        if not bonds.is_vampire(character):
            continue
        for row in db.scalars(select(Retainer).where(Retainer.character_id == character.id)):
            keep(retainer_known(db, troupe, character, row))
    return found


def fill_in(db: Session, user: User, troupe: Troupe) -> list[BloodBond]:
    """Add every bond `known` lists, lesser ones first so a full bond wipes them as it
    would have; the bonds added."""
    added: list[BloodBond] = []
    for item in sorted(known(db, troupe), key=lambda k: (k.level, k.night)):
        bond = add(db, user, troupe, item)
        if bond is not None:
            added.append(bond)
    return added
