"""Blood bonds (#660; MET: VTM pp. 295-296, and the Errata's p. 295).

A troupe's Blood bonds setting says how far Horatio tracks them: "off", not at all
(the default); "staff", who record every drink; and two modes for players,
"players_report" and "players_manage", defined here and built in #661; until then
they work as "staff". Switched off, nothing of a bond shows anywhere, not even in
the logs, but nothing is lost: it all comes back when it is switched on again.

A bond is a thrall's to a regnant. Either side is a character (a PC or an NPC) or,
for someone not in Horatio, a name only, as a location's controller is. Its level
is never typed in: it comes from its log of drinks (`level_of`), one for each
separate night, up to three, a full bond. Forming a full bond wipes away every
lesser bond the thrall has (p. 295). Staff can also enter a bond that already
stands, such as one from before Horatio, at its level with a reason, and break
one with a reason (p. 296).

Who sees a bond: the troupe's running staff, all of them; the thrall's player,
their own character's; the regnant's player, only once staff mark it known to the
regnant. Nobody else, anywhere. Every change goes in the troupe's log and the
thrall's own log.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from horatio import audit
from horatio.models import AuditEvent, BloodBond, BondEntry, Character, Troupe, User
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.sheets import conflict, membership, unprocessable

# The troupe's setting, and what each is called.
SETTINGS = {
    "off": "Off",
    "staff": "Staff manages",
    "players_report": "Players report and staff approves",
    "players_manage": "Players manage",
}
# A bond still felt: fading is, until it ends (#662).
OPEN = ("active", "fading")
SOURCES = {"game": "at a game", "downtime": "in a downtime", "staff": "told to staff"}
FULL = 3
LEVELS = {1: "one drink", 2: "two drinks", 3: "a full bond"}
# Most a name, a note or a reason may be.
LONGEST_NAME = 200


@dataclass(frozen=True)
class Party:
    """One side of a bond: a character, or a name only."""

    character: Character | None
    name: str

    @property
    def shown(self) -> str:
        return self.character.name if self.character is not None else self.name


def tracked(troupe: Troupe) -> bool:
    return troupe.blood_bonds != "off"


def set_setting(db: Session, user: User, troupe: Troupe, setting: str) -> None:
    """Change how far the troupe tracks blood bonds. Switching it off hides them
    everywhere; what was recorded is kept, and comes back when it is on again."""
    if setting not in SETTINGS:
        raise unprocessable(f"Blood bonds is one of {', '.join(SETTINGS)}.")
    if troupe.blood_bonds == setting:
        return
    troupe.blood_bonds = setting
    audit.record(db, user, "house.blood_bonds", troupe_id=troupe.id, setting=SETTINGS[setting])


def can_manage(db: Session, user: User, troupe: Troupe) -> bool:
    """The troupe's running staff, and the custodian: they see all its bonds."""
    if troupe.archived_at is not None and not user.is_custodian:
        return False
    return allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_BONDS, is_custodian=user.is_custodian
    )


def plays(user: User, character: Character | None) -> bool:
    return character is not None and character.kind == "pc" and character.player_id == user.id


def shown_to(
    db: Session,
    user: User,
    bond: BloodBond,
    troupe: Troupe,
    thrall: Character | None,
    regnant: Character | None,
) -> bool:
    """Whether `user` may know of the bond: nobody while the troupe's setting is off;
    otherwise its running staff, the thrall's player, and the regnant's player once
    it is known to the regnant."""
    if not tracked(troupe):
        return False
    return (
        can_manage(db, user, troupe)
        or plays(user, thrall)
        or (bond.known_to_regnant and plays(user, regnant))
    )


def hidden_events() -> ColumnElement[bool]:
    """The log entries about bonds in troupes whose setting is off, which no log
    shows until it is on again (but the custodian's search of the whole audit log)."""
    return and_(
        AuditEvent.action.startswith("bond."),
        AuditEvent.troupe_id.in_(select(Troupe.id).where(Troupe.blood_bonds == "off")),
    )


# --- who may be on each side ------------------------------------------------------------


def in_troupe(db: Session, troupe: Troupe, character: Character) -> bool:
    """A character the troupe's staff can name in a bond: one of its NPCs, or a
    character in it now, at home or visiting."""
    if character.kind == "npc":
        return character.owner_troupe_id == troupe.id
    return membership(db, character, troupe.id) is not None


def is_vampire(character: Character) -> bool:
    if character.kind == "npc":
        return character.npc_kind == "vampire"
    return character.splat == "vampire"


def party(
    db: Session,
    troupe: Troupe,
    character_id: uuid.UUID | None,
    name: str,
    *,
    regnant: bool,
) -> Party:
    """The thrall or the regnant as staff named them: a character of the troupe's,
    or a name only. A regnant is a vampire, whose blood binds."""
    side = "regnant" if regnant else "thrall"
    name = name.strip()
    if (character_id is None) == (not name):
        raise unprocessable(f"Name the {side}: a character, or a name only.")
    if character_id is None:
        if len(name) > LONGEST_NAME:
            raise unprocessable(f"A name is at most {LONGEST_NAME} characters.")
        return Party(None, name)
    character = db.get(Character, character_id)
    if character is None or not in_troupe(db, troupe, character):
        raise unprocessable(f"The {side} isn't a character in this troupe.")
    if regnant and not is_vampire(character):
        raise unprocessable(f"{character.name} isn't a vampire: only a vampire's blood binds.")
    return Party(character, "")


def parties(db: Session, bond: BloodBond) -> tuple[Party, Party]:
    """The bond's thrall and regnant."""
    thrall = db.get(Character, bond.thrall_id) if bond.thrall_id else None
    regnant = db.get(Character, bond.regnant_id) if bond.regnant_id else None
    return Party(thrall, bond.thrall_name), Party(regnant, bond.regnant_name)


# --- the level, from the log -------------------------------------------------------------


def level_of(entries: Sequence[BondEntry]) -> int:
    """The bond's level, 1 to 3, from its log, night by night: a drink on a night not
    already counted adds one, up to a full bond; drinks on one night count once (p.
    295). A bond entered by staff stands at its level from its night, whatever was
    drunk before."""
    level = 0
    nights: set[date] = set()
    # A night's drinks before a bond entered on it: entering says where it stood after.
    for entry in sorted(entries, key=lambda e: (e.night, e.kind == "entered")):
        if entry.kind == "entered":
            level = entry.level or 0
        elif entry.night not in nights:
            nights.add(entry.night)
            level = min(FULL, level + 1)
    return level


def entries_of(db: Session, bond: BloodBond) -> list[BondEntry]:
    """Its log, oldest night first."""
    return list(
        db.scalars(
            select(BondEntry)
            .where(BondEntry.bond_id == bond.id)
            .order_by(BondEntry.night, BondEntry.created_at)
        )
    )


def level(db: Session, bond: BloodBond) -> int:
    return level_of(entries_of(db, bond))


# --- changes --------------------------------------------------------------------------


def same(
    id_column: InstrumentedAttribute[uuid.UUID | None],
    name_column: InstrumentedAttribute[str],
    side: Party,
) -> ColumnElement[bool]:
    if side.character is not None:
        return id_column == side.character.id
    return and_(id_column.is_(None), func.lower(name_column) == side.name.lower())


def open_bond(db: Session, troupe: Troupe, thrall: Party, regnant: Party) -> BloodBond | None:
    """The bond the troupe keeps between the two that is still felt, if any."""
    return db.scalars(
        select(BloodBond).where(
            BloodBond.troupe_id == troupe.id,
            BloodBond.status.in_(OPEN),
            same(BloodBond.thrall_id, BloodBond.thrall_name, thrall),
            same(BloodBond.regnant_id, BloodBond.regnant_name, regnant),
        )
    ).first()


def new_bond(db: Session, user: User, troupe: Troupe, thrall: Party, regnant: Party) -> BloodBond:
    if (thrall.character, thrall.name.lower()) == (regnant.character, regnant.name.lower()):
        raise unprocessable("A character can't be bound to themself.")
    bond = BloodBond(
        troupe_id=troupe.id,
        thrall_id=thrall.character.id if thrall.character else None,
        thrall_name=thrall.name,
        regnant_id=regnant.character.id if regnant.character else None,
        regnant_name=regnant.name,
        created_by=user.id,
    )
    db.add(bond)
    db.flush()
    return bond


def check_night(night: date) -> None:
    # A day's grace, for a game still going past midnight somewhere.
    if night > datetime.now(UTC).date() + timedelta(days=1):
        raise unprocessable("That night hasn't come yet.")


def log(db: Session, user: User, action: str, bond: BloodBond, **data: str) -> None:
    """Into the troupe's log, and the thrall's own if it is a character."""
    thrall, regnant = parties(db, bond)
    audit.record(
        db,
        user,
        action,
        troupe_id=bond.troupe_id,
        character_id=bond.thrall_id,
        character_name=thrall.shown,
        regnant=regnant.shown,
        bond_id=bond.id,
        **data,
    )


def when(night: date) -> str:
    return f"{night.day} {night:%b %Y}"


def record_drink(
    db: Session,
    user: User,
    troupe: Troupe,
    thrall: Party,
    regnant: Party,
    night: date,
    source: str,
    note: str,
) -> BloodBond:
    """Log a drink the thrall took of the regnant's blood: on the bond between them
    still felt, or on a new one. Reaching a full bond wipes away the thrall's lesser
    bonds."""
    if source not in SOURCES:
        raise unprocessable(f"Where it was told is one of {', '.join(SOURCES)}.")
    check_night(night)
    bond = open_bond(db, troupe, thrall, regnant) or new_bond(db, user, troupe, thrall, regnant)
    return add_drink(db, user, bond, night, source, note)


def add_drink(
    db: Session, user: User, bond: BloodBond, night: date, source: str, note: str
) -> BloodBond:
    """Log a drink on a bond still felt."""
    if bond.status not in OPEN:
        raise conflict("That bond has ended: record the drink as a new bond.")
    if source not in SOURCES:
        raise unprocessable(f"Where it was told is one of {', '.join(SOURCES)}.")
    check_night(night)
    before = level(db, bond)
    db.add(
        BondEntry(
            bond_id=bond.id,
            kind="drink",
            night=night,
            source=source,
            note=note.strip(),
            recorded_by=user.id,
        )
    )
    db.flush()
    after = level(db, bond)
    log(
        db,
        user,
        "bond.drink",
        bond,
        night=when(night),
        source=SOURCES[source],
        level=LEVELS[after],
        again="" if after > before or after == FULL else " (a drink that night already counted)",
    )
    if before < FULL <= after:
        wipe_lesser(db, user, bond)
    return bond


def enter_bond(
    db: Session,
    user: User,
    troupe: Troupe,
    thrall: Party,
    regnant: Party,
    at: int,
    night: date,
    reason: str,
) -> BloodBond:
    """Enter a bond that already stands, such as one from before Horatio, at its
    level from a night, with the reason."""
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for entering the bond.")
    if at not in LEVELS:
        raise unprocessable("A bond is one to three drinks.")
    check_night(night)
    if open_bond(db, troupe, thrall, regnant) is not None:
        raise conflict(
            f"{thrall.shown} is already bound to {regnant.shown}: add a drink to that bond."
        )
    bond = new_bond(db, user, troupe, thrall, regnant)
    db.add(
        BondEntry(
            bond_id=bond.id,
            kind="entered",
            night=night,
            source="staff",
            level=at,
            note=reason,
            recorded_by=user.id,
        )
    )
    db.flush()
    log(db, user, "bond.entered", bond, level=LEVELS[at], night=when(night), reason=reason)
    if at == FULL:
        wipe_lesser(db, user, bond)
    return bond


def wipe_lesser(db: Session, user: User, full: BloodBond) -> None:
    """A full bond wipes away every lesser bond its thrall has (p. 295): each ends,
    in its own troupe's log."""
    thrall, regnant = parties(db, full)
    if thrall.character is not None:
        same_thrall = BloodBond.thrall_id == thrall.character.id
    else:
        same_thrall = and_(
            BloodBond.troupe_id == full.troupe_id,
            BloodBond.thrall_id.is_(None),
            func.lower(BloodBond.thrall_name) == thrall.name.lower(),
        )
    others = db.scalars(
        select(BloodBond).where(same_thrall, BloodBond.status.in_(OPEN), BloodBond.id != full.id)
    )
    for other in others:
        if level(db, other) >= FULL:
            continue
        end(db, user, other, "ended", f"Wiped away by the full bond to {regnant.shown}.")
        log(db, user, "bond.wiped", other, full=regnant.shown)


def end(db: Session, user: User, bond: BloodBond, status: str, reason: str) -> None:
    bond.status = status
    bond.ended_at = datetime.now(UTC)
    bond.ended_by = user.id
    bond.ended_reason = reason


def break_bond(db: Session, user: User, bond: BloodBond, reason: str) -> None:
    """Mark the bond broken, as the book allows, though it is hard (p. 296)."""
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for breaking the bond.")
    if bond.status not in OPEN:
        raise conflict("That bond has already ended.")
    end(db, user, bond, "broken", reason)
    db.flush()
    log(db, user, "bond.broken", bond, reason=reason)


def set_known(db: Session, user: User, bond: BloodBond, known: bool) -> None:
    """Whether the regnant's player is told of the bond, and sees it."""
    if bond.known_to_regnant == known:
        return
    bond.known_to_regnant = known
    db.flush()
    log(db, user, "bond.known", bond, known="known" if known else "not known")
