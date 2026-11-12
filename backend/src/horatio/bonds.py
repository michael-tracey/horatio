"""Blood bonds (#660; MET: VTM pp. 295-296, and the Errata's p. 295).

A troupe's Blood bonds setting says how far Horatio tracks them: "off", not at all
(the default); "staff", who record every drink; "players_report", where players
report their characters' drinks and running staff approve each in the troupe's
approvals queue; and "players_manage", where players record them and they count at
once (#661). Switched off, nothing of a bond shows anywhere, not even in the logs or
the approvals queue, but nothing is lost: it all comes back when it is switched on
again.

**Players' drinks** (#661). A player reports a drink only for their own character, on
either side: "I drank from X", as the thrall, or "X drank from me", as the regnant.
The other side is a player character in the troupe now, or a name only. Nobody can
bond someone else's character by themselves: in "players_manage" the thrall's player
records their own drinks at once, but a drink the regnant's player records waits for
the thrall's player to confirm it, or for staff when the thrall has no player (an NPC
or a name). A drink the regnant reported makes the bond known to the regnant, as its
player plainly knows of it. A report can't be for a night before either character was
made in Horatio, nor from a regnant other than the one a full bond binds the thrall
to: a full bond makes the thrall immune to others (the Errata's p. 295). Until it is
decided a report is a `BondReport`, seen by the player who made it, whoever decides
it, and the thrall's player once they are asked to confirm it: never the other side
otherwise. Running staff can still change or remove any drink in a bond's log.

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

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from horatio import audit, notifications, targets
from horatio.models import (
    Approval,
    AuditEvent,
    BloodBond,
    BondEntry,
    BondReport,
    Character,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.sheets import conflict, membership, memberships, unprocessable

# The troupe's setting, and what each is called.
SETTINGS = {
    "off": "Off",
    "staff": "Staff manages",
    "players_report": "Players report and staff approves",
    "players_manage": "Players manage",
}
# The settings in which players report or record drinks themselves.
PLAYER_MODES = ("players_report", "players_manage")
# Where a player says a drink happened.
PLAYER_SOURCES = ("game", "downtime")
# A drink a player reported, in the troupe's approvals queue.
APPROVAL_KIND = "bond_drink"
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
    shows until it is on again (but the custodian's search of the whole audit log):
    bonds' own, and the decisions on drinks reported."""
    return and_(
        or_(
            AuditEvent.action.startswith("bond."),
            and_(
                AuditEvent.action.startswith("approval."),
                AuditEvent.data["kind"].astext == APPROVAL_KIND,
            ),
        ),
        AuditEvent.troupe_id.in_(select(Troupe.id).where(Troupe.blood_bonds == "off")),
    )


def hidden_approvals() -> ColumnElement[bool]:
    """Drinks reported to troupes whose setting is off: kept, but in no queue, count
    or task until it is on again."""
    return and_(
        Approval.kind == APPROVAL_KIND,
        Approval.troupe_id.in_(select(Troupe.id).where(Troupe.blood_bonds == "off")),
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


def end(db: Session, user: User | None, bond: BloodBond, status: str, reason: str) -> None:
    bond.status = status
    bond.ended_at = datetime.now(UTC)
    bond.ended_by = user.id if user else None
    bond.ended_reason = reason
    # Ended any other way than by fading (`faded` sets it back), it didn't fade.
    bond.fades_on = None
    bond.fade_reason = ""


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


# --- fading when a side meets Final Death (#662) ----------------------------------------
#
# "If a regnant is killed, the bond will slowly fade over the next month" (p. 296). The
# thrall still feels it all that month, so nothing the thrall's player sees changes:
# their character's Bonds card shows it as before, and the fade goes only in the
# troupe's log, which running staff keep (never the thrall's own log). Running staff
# see the truth at once, with the day it ends, and can move that day with a reason. On
# that day it ends as faded; the thrall's player is told only that it has faded, with
# the troupe's next downtime results (`tell_faded`), and until then their sheet still
# shows it. Off-field and Inactive regnants are left alone: bonds that fade with time
# and distance are #665. A thrall's Final Death ends its bonds; a regnant's player who
# knew of one goes on seeing it until staff clear it, for the regnant has no sense of
# the death.

# How long a dead regnant's bond takes to fade (p. 296: "over the next month").
FADE_DAYS = 30
# Why a bond fades.
REGNANT_DIED = "regnant_died"
FADE_REASONS = {REGNANT_DIED: "its regnant met Final Death"}
FINAL_DEATH = "final_death"


def today() -> date:
    return datetime.now(UTC).date()


def staff_log(db: Session, user: User | None, action: str, bond: BloodBond, **data: str) -> None:
    """Into the troupe's log only, which its running staff keep: never the thrall's own
    log, which the thrall's player reads."""
    thrall, regnant = parties(db, bond)
    audit.record(
        db,
        user,
        action,
        troupe_id=bond.troupe_id,
        character_id=None,
        thrall=thrall.shown,
        regnant=regnant.shown,
        bond_id=bond.id,
        **data,
    )


def tracked_bonds(db: Session, *conditions: ColumnElement[bool]) -> list[BloodBond]:
    """Bonds matching `conditions` in troupes that track bonds: switched off, none of
    the fading runs (it catches up when switched on again)."""
    return list(
        db.scalars(
            select(BloodBond)
            .where(
                *conditions,
                BloodBond.troupe_id.in_(select(Troupe.id).where(Troupe.blood_bonds != "off")),
            )
            .order_by(BloodBond.created_at)
        )
    )


def start_fading(db: Session, user: User, regnant: Character) -> None:
    """The regnant met Final Death: each bond still felt where they are the regnant
    starts to fade, ending FADE_DAYS from today."""
    ends = today() + timedelta(days=FADE_DAYS)
    for bond in tracked_bonds(db, BloodBond.regnant_id == regnant.id, BloodBond.status == "active"):
        bond.status = "fading"
        bond.fades_on = ends
        bond.fade_reason = REGNANT_DIED
        db.flush()
        staff_log(db, user, "bond.fading", bond, ends=when(ends), why=FADE_REASONS[REGNANT_DIED])


def stop_fading(db: Session, user: User, regnant: Character) -> None:
    """The regnant didn't meet Final Death after all (staff changed why it left): its
    bonds still fading are felt as before. Those already faded stay ended."""
    for bond in tracked_bonds(
        db,
        BloodBond.regnant_id == regnant.id,
        BloodBond.status == "fading",
        BloodBond.fade_reason == REGNANT_DIED,
    ):
        bond.status = "active"
        bond.fades_on = None
        bond.fade_reason = ""
        db.flush()
        staff_log(db, user, "bond.fading_stopped", bond)


def thrall_died(db: Session, user: User, thrall: Character) -> None:
    """The thrall met Final Death: each bond it still felt ends. A regnant's player who
    knew of a bond goes on seeing it as it was until staff clear it."""
    for bond in tracked_bonds(db, BloodBond.thrall_id == thrall.id, BloodBond.status.in_(OPEN)):
        end(db, user, bond, "ended", "Its thrall met Final Death.")
        bond.kept_for_regnant = bond.known_to_regnant
        # The thrall is gone: there is no one to tell that it faded.
        bond.thrall_told_at = bond.ended_at
        db.flush()
        log(db, user, "bond.thrall_died", bond)


def final_death(db: Session, user: User, character: Character) -> None:
    """A character met Final Death (horatio.leaving): as a regnant, its bonds fade; as
    a thrall, its bonds end."""
    start_fading(db, user, character)
    thrall_died(db, user, character)


def leaving_changed(
    db: Session, user: User, character: Character, was: str | None, now: str | None
) -> None:
    """Why a retired character left was changed: to Final Death, as if it died now;
    from it, its bonds still fading are felt again."""
    if was == now:
        return
    if now == FINAL_DEATH:
        final_death(db, user, character)
    elif was == FINAL_DEATH:
        stop_fading(db, user, character)


def faded(db: Session, bond: BloodBond, user: User | None = None) -> None:
    """The bond has faded: it ends. The thrall's player is told with the next downtime
    results; a thrall with no player has no one to tell."""
    thrall, _ = parties(db, bond)
    why = bond.fade_reason
    end(db, user, bond, "ended", f"Faded: {FADE_REASONS.get(why, 'it faded')}.")
    bond.fade_reason = why
    if thrall.character is None or thrall.character.kind != "pc":
        bond.thrall_told_at = bond.ended_at
    db.flush()
    staff_log(db, user, "bond.faded", bond)


def settle_fades(db: Session, troupe_ids: Sequence[uuid.UUID] | None = None) -> None:
    """End every fading bond whose day has come: those of `troupe_ids`, or all."""
    conditions: list[ColumnElement[bool]] = [
        BloodBond.status == "fading",
        BloodBond.fades_on <= today(),
    ]
    if troupe_ids is not None:
        conditions.append(BloodBond.troupe_id.in_(troupe_ids))
    for bond in tracked_bonds(db, *conditions):
        faded(db, bond)


def set_fade(db: Session, user: User, bond: BloodBond, ends: date, reason: str) -> None:
    """Running staff move the day a fading bond ends, with the reason: to today or
    before, it ends now, as faded."""
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for changing when the bond fades.")
    if bond.status != "fading" or bond.fades_on is None:
        raise conflict("That bond isn't fading.")
    was = bond.fades_on
    if ends <= today():
        staff_log(
            db, user, "bond.fade_changed", bond, ends=when(today()), was=when(was), reason=reason
        )
        faded(db, bond, user)
        return
    if ends == was:
        return
    bond.fades_on = ends
    db.flush()
    staff_log(db, user, "bond.fade_changed", bond, ends=when(ends), was=when(was), reason=reason)


def untold(db: Session, troupe: Troupe) -> list[BloodBond]:
    """Bonds of the troupe that faded and whose thrall's player isn't told yet."""
    return list(
        db.scalars(
            select(BloodBond)
            .where(
                BloodBond.troupe_id == troupe.id,
                BloodBond.status == "ended",
                BloodBond.fade_reason != "",
                BloodBond.thrall_told_at.is_(None),
            )
            .order_by(BloodBond.ended_at)
        )
    )


def tell_faded(db: Session, staff: User, troupe: Troupe) -> int:
    """With the troupe's downtime results (horatio.responses.deliver_cycle), tell each
    thrall's player whose bond has faded that it has: only that, never why. Returns
    how many were told."""
    if not tracked(troupe):
        return 0
    settle_fades(db, [troupe.id])
    told = 0
    for bond in untold(db, troupe):
        thrall, regnant = parties(db, bond)
        bond.thrall_told_at = datetime.now(UTC)
        if thrall.character is not None and thrall.character.kind == "pc":
            notifications.notify(
                db,
                [thrall.character.player_id],
                "sheet.bond",
                f"{thrall.character.name}'s bond to {regnant.shown} has faded.",
                f"/characters/{thrall.character.id}",
                troupe_id=troupe.id,
                character_id=thrall.character.id,
            )
            log(db, staff, "bond.faded_told", bond)
            told += 1
    db.flush()
    return told


def clear_kept(db: Session, user: User, bond: BloodBond) -> None:
    """Running staff stop showing the regnant's player a bond whose thrall died."""
    if not bond.kept_for_regnant:
        return
    bond.kept_for_regnant = False
    db.flush()
    staff_log(db, user, "bond.kept_cleared", bond)


def as_felt(
    user: User, bond: BloodBond, thrall: Character | None, regnant: Character | None
) -> bool:
    """A bond that has ended which a player still sees as it was: the thrall's player,
    until told it faded; the regnant's player who knew of it, while its thrall's death
    is kept from them."""
    if bond.status != "ended":
        return False
    if bond.fade_reason and bond.thrall_told_at is None and plays(user, thrall):
        return True
    return bond.kept_for_regnant and plays(user, regnant)


# --- staff change a drink -------------------------------------------------------------


def entry_of(db: Session, bond: BloodBond, entry_id: uuid.UUID) -> BondEntry:
    entry = db.get(BondEntry, entry_id)
    if entry is None or entry.bond_id != bond.id:
        raise unprocessable("That isn't in this bond's log.")
    return entry


def change_entry(
    db: Session, user: User, bond: BloodBond, entry: BondEntry, night: date, note: str
) -> None:
    """Change a drink's night or note, or a bond entered's: for staff, who keep every
    bond, such as one a player recorded wrongly. The level is worked out again; if it
    becomes a full bond, the thrall's lesser bonds are wiped away."""
    check_night(night)
    note = note.strip()
    if entry.kind == "entered" and not note:
        raise unprocessable("Give a reason for entering the bond.")
    if (entry.night, entry.note) == (night, note):
        return
    before = level(db, bond)
    was = entry.night
    entry.night = night
    entry.note = note
    db.flush()
    after = level(db, bond)
    log(
        db,
        user,
        "bond.entry_changed",
        bond,
        night=when(night),
        was=when(was),
        level=LEVELS.get(after, LEVELS[1]),
    )
    if bond.status in OPEN and before < FULL <= after:
        wipe_lesser(db, user, bond)


def remove_entry(db: Session, user: User, bond: BloodBond, entry: BondEntry, reason: str) -> bool:
    """Take a drink, or a bond entered, out of the bond's log, with the reason: for
    staff, such as one a player recorded that didn't happen. A bond left with nothing
    in its log is removed too. Lesser bonds a full bond wiped away stay ended; staff
    can enter them again. Whether the bond is still there."""
    reason = reason.strip()
    if not reason:
        raise unprocessable("Give a reason for taking it out of the log.")
    night = entry.night
    db.delete(entry)
    db.flush()
    left = entries_of(db, bond)
    log(
        db,
        user,
        "bond.entry_removed",
        bond,
        night=when(night),
        reason=reason,
        level=LEVELS[level_of(left)] if left else "no bond",
    )
    if left:
        return True
    db.delete(bond)
    db.flush()
    return False


# --- players' drinks (#661) -------------------------------------------------------------


def for_players(troupe: Troupe) -> bool:
    return troupe.blood_bonds in PLAYER_MODES


def report_troupes(db: Session, user: User, character: Character) -> list[Troupe]:
    """The troupes the character's player can report its drinks to: those it is in
    now, still running, whose setting lets players report or record drinks."""
    if not plays(user, character) or character.status == "retired":
        return []
    ids = [m.troupe_id for m in memberships(db, character)]
    return [
        t
        for t in db.scalars(select(Troupe).where(Troupe.id.in_(ids)).order_by(Troupe.name))
        if t.archived_at is None and for_players(t)
    ]


def player_choices(db: Session, troupe: Troupe, character: Character) -> list[Character]:
    """Whom a player can name on the other side: the troupe's player characters now,
    home or visiting, not retired, but their own. Anyone else is a name only."""
    return targets.choices(db, troupe.id, character)


def other_side(
    db: Session,
    troupe: Troupe,
    mine: Character,
    character_id: uuid.UUID | None,
    name: str,
    *,
    regnant: bool,
) -> Party:
    """The other side as a player named it: one of `player_choices`, or a name only."""
    if character_id is not None and character_id not in {
        c.id for c in player_choices(db, troupe, mine)
    }:
        side = "regnant" if regnant else "thrall"
        raise unprocessable(f"The {side} isn't a player character in this troupe.")
    return party(db, troupe, character_id, name, regnant=regnant)


def immune_to(db: Session, troupe: Troupe, thrall: Party, regnant: Party) -> str | None:
    """Why a new drink can't bind the thrall to the regnant: a full bond the thrall
    holds to someone else makes them immune to other bonds until it drops (the
    Errata's p. 295). Players can't record past it; for staff it comes with #665."""
    if thrall.character is not None:
        same_thrall = BloodBond.thrall_id == thrall.character.id
    else:
        same_thrall = and_(
            BloodBond.troupe_id == troupe.id,
            BloodBond.thrall_id.is_(None),
            func.lower(BloodBond.thrall_name) == thrall.name.lower(),
        )
    for bond in db.scalars(
        select(BloodBond).where(same_thrall, BloodBond.status.in_(OPEN)).order_by(BloodBond.id)
    ):
        holder = parties(db, bond)[1]
        if (holder.character, holder.name.lower()) == (regnant.character, regnant.name.lower()):
            continue
        if level(db, bond) >= FULL:
            return (
                f"{thrall.shown} has a full bond to {holder.shown}, which makes them immune "
                "to other bonds until it drops (Errata, p. 295)."
            )
    return None


def check_player_night(night: date, *characters: Character | None) -> None:
    """Not a night to come, nor one before either character was made in Horatio: with a
    day's grace, as `check_night` gives, since the night is the player's own date and
    the character was made at a moment kept in UTC."""
    check_night(night)
    for character in characters:
        made = character.created_at.astimezone(UTC).date() if character is not None else None
        if character is not None and made is not None and night < made - timedelta(days=1):
            raise unprocessable(f"That night is before {character.name} was made in Horatio.")


def report_parties(db: Session, report: BondReport) -> tuple[Party, Party]:
    thrall = db.get(Character, report.thrall_id) if report.thrall_id else None
    regnant = db.get(Character, report.regnant_id) if report.regnant_id else None
    return Party(thrall, report.thrall_name), Party(regnant, report.regnant_name)


def reporter(db: Session, report: BondReport) -> Character | None:
    """The character whose player made the report."""
    thrall, regnant = report_parties(db, report)
    return (thrall if report.reported_as == "thrall" else regnant).character


def log_report(db: Session, user: User, action: str, report: BondReport, **data: str) -> None:
    """Into the troupe's log, and the log of the character it was reported for, never
    the other side's: they learn of it only as the bond itself shows them."""
    thrall, regnant = report_parties(db, report)
    mine = reporter(db, report)
    audit.record(
        db,
        user,
        action,
        troupe_id=report.troupe_id,
        character_id=mine.id if mine else None,
        character_name=thrall.shown,
        regnant=regnant.shown,
        night=when(report.night),
        report_id=report.id,
        **data,
    )


def report_drink(
    db: Session,
    user: User,
    troupe: Troupe,
    mine: Character,
    reported_as: str,
    other: Party,
    night: date,
    source: str,
    note: str,
) -> BondReport | BloodBond:
    """A player's drink for their own character, `mine`, on the side `reported_as`:
    the bond it was recorded on, when it counts at once; otherwise the report, waiting
    on staff or on the thrall's player."""
    if not for_players(troupe):
        raise conflict("This troupe's staff record its blood bonds; players don't.")
    if not plays(user, mine) or mine.status == "retired" or not in_troupe(db, troupe, mine):
        raise unprocessable("Players report drinks only for their own characters in the troupe.")
    if reported_as not in ("thrall", "regnant"):
        raise unprocessable("Say whether your character drank, or was drunk from.")
    if source not in PLAYER_SOURCES:
        raise unprocessable(f"Where it happened is one of {', '.join(PLAYER_SOURCES)}.")
    if reported_as == "regnant" and not is_vampire(mine):
        raise unprocessable(f"{mine.name} isn't a vampire: only a vampire's blood binds.")
    me = Party(mine, "")
    thrall, regnant = (me, other) if reported_as == "thrall" else (other, me)
    check_player_night(night, mine, other.character)
    refused = immune_to(db, troupe, thrall, regnant)
    if refused:
        raise conflict(refused)
    note = note.strip()
    if troupe.blood_bonds == "players_manage" and (
        reported_as == "thrall" or plays(user, thrall.character)
    ):
        bond = record_drink(db, user, troupe, thrall, regnant, night, source, note)
        if plays(user, regnant.character):
            set_known(db, user, bond, True)
        return bond
    asks_thrall = (
        troupe.blood_bonds == "players_manage"
        and thrall.character is not None
        and thrall.character.kind == "pc"
    )
    report = BondReport(
        troupe_id=troupe.id,
        thrall_id=thrall.character.id if thrall.character else None,
        thrall_name=thrall.name,
        regnant_id=regnant.character.id if regnant.character else None,
        regnant_name=regnant.name,
        reported_as=reported_as,
        night=night,
        source=source,
        note=note,
        waiting_on="thrall" if asks_thrall else "staff",
        reported_by=user.id,
    )
    if not asks_thrall:
        approval = Approval(
            character_id=mine.id,
            troupe_id=troupe.id,
            kind=APPROVAL_KIND,
            requested_by=user.id,
            player_note=note,
        )
        db.add(approval)
        db.flush()
        report.approval_id = approval.id
    db.add(report)
    db.flush()
    log_report(db, user, "bond.reported", report, source=SOURCES[source])
    if report.approval_id is not None:
        notifications.approval_waiting(db, db.get_one(Approval, report.approval_id))
    else:
        assert thrall.character is not None
        notifications.notify(
            db,
            [thrall.character.player_id],
            "sheet.bond",
            f"{regnant.shown}'s player says {thrall.shown} drank their blood on "
            f"{when(night)}: confirm or decline it on the sheet.",
            f"/characters/{thrall.character.id}",
            troupe_id=troupe.id,
            character_id=thrall.character.id,
        )
    return report


def report_of(db: Session, report_id: uuid.UUID) -> BondReport:
    report = db.get(BondReport, report_id)
    if report is None:
        raise unprocessable("No such drink is waiting.")
    return report


def report_for_approval(db: Session, approval: Approval) -> BondReport | None:
    return db.scalar(select(BondReport).where(BondReport.approval_id == approval.id))


def accept(db: Session, user: User, report: BondReport) -> BloodBond:
    """Log the report's drink, approved by staff or confirmed by the thrall's player."""
    if report.status != "pending":
        raise conflict(f"That drink is already {report.status}.")
    troupe = db.get_one(Troupe, report.troupe_id)
    if not tracked(troupe):
        raise conflict("This troupe doesn't track blood bonds now.")
    thrall, regnant = report_parties(db, report)
    refused = immune_to(db, troupe, thrall, regnant)
    if refused:
        raise conflict(refused)
    bond = record_drink(db, user, troupe, thrall, regnant, report.night, report.source, report.note)
    if report.reported_as == "regnant":
        set_known(db, user, bond, True)
    report.status = "approved"
    report.decided_by = user.id
    report.decided_at = datetime.now(UTC)
    report.bond_id = bond.id
    db.flush()
    return bond


def refuse(db: Session, user: User, report: BondReport, reason: str) -> None:
    if report.status != "pending":
        raise conflict(f"That drink is already {report.status}.")
    report.status = "declined"
    report.decided_by = user.id
    report.decided_at = datetime.now(UTC)
    report.reason = reason.strip()
    db.flush()


def tell_reporter(db: Session, report: BondReport, summary: str) -> None:
    mine = reporter(db, report)
    if mine is None or mine.kind != "pc":
        return
    notifications.notify(
        db,
        [mine.player_id],
        "sheet.bond",
        summary,
        f"/characters/{mine.id}",
        troupe_id=report.troupe_id,
        character_id=mine.id,
    )


def drink_line(db: Session, report: BondReport) -> str:
    """The drink, as its reporter would say it: "Agnes drinking Viktor's blood on 3 Nov 2026"."""
    thrall, regnant = report_parties(db, report)
    return f"{thrall.shown} drinking {regnant.shown}'s blood on {when(report.night)}"


def approved(db: Session, staff: User, approval: Approval) -> None:
    """Staff approved a drink a player reported: it goes in the bond's log
    (horatio.sheets.decide)."""
    report = report_for_approval(db, approval)
    if report is None:
        raise conflict("This drink is no longer there; decline this instead.")
    accept(db, staff, report)
    tell_reporter(db, report, f"The storytellers approved {drink_line(db, report)}.")


def declined(db: Session, staff: User, approval: Approval, note: str) -> None:
    """Staff declined a drink a player reported: the player is told why."""
    report = report_for_approval(db, approval)
    if report is None:
        return
    refuse(db, staff, report, note)
    why = f": {report.reason}" if report.reason else "."
    tell_reporter(db, report, f"The storytellers declined {drink_line(db, report)}{why}")


def withdrawn(db: Session, approval: Approval) -> None:
    """The player took back a drink waiting on staff."""
    report = report_for_approval(db, approval)
    if report is not None and report.status == "pending":
        report.status = "withdrawn"
        report.decided_at = datetime.now(UTC)
        db.flush()


def can_withdraw(user: User, report: BondReport) -> bool:
    return report.status == "pending" and report.reported_by == user.id


def withdraw(db: Session, user: User, report: BondReport) -> None:
    """The player who reported a drink takes it back while it waits: through the
    approvals queue when it is in it, which logs it."""
    if not can_withdraw(user, report):
        raise conflict("Only a drink you reported, still waiting, can be withdrawn.")
    if report.approval_id is not None:
        from horatio import sheets  # imports this module

        sheets.withdraw(db, user, db.get_one(Approval, report.approval_id))
        return
    report.status = "withdrawn"
    report.decided_at = datetime.now(UTC)
    db.flush()
    log_report(db, user, "bond.report_withdrawn", report)


def left_troupe(db: Session, character: Character, troupe: Troupe) -> None:
    """A character leaving the troupe takes back the drinks its player reported there
    that wait on a thrall's player (those waiting on staff go with its requests)."""
    for report in db.scalars(
        select(BondReport).where(
            BondReport.troupe_id == troupe.id,
            BondReport.status == "pending",
            BondReport.waiting_on == "thrall",
            or_(
                and_(BondReport.reported_as == "thrall", BondReport.thrall_id == character.id),
                and_(BondReport.reported_as == "regnant", BondReport.regnant_id == character.id),
            ),
        )
    ):
        report.status = "withdrawn"
        report.decided_at = datetime.now(UTC)


def answers(user: User, report: BondReport, thrall: Character | None) -> bool:
    """Whether `user` is the thrall's player asked to confirm the report."""
    return report.waiting_on == "thrall" and report.status == "pending" and plays(user, thrall)


def confirm(db: Session, user: User, report: BondReport, yes: bool, reason: str = "") -> None:
    """The thrall's player confirms a drink the regnant's player recorded, and it
    counts, or declines it, and the regnant's player is told. Only while the troupe
    lets players manage their drinks; otherwise staff decide it on the Bonds screen."""
    thrall = report_parties(db, report)[0].character
    if not answers(user, report, thrall):
        raise conflict("That drink isn't waiting on you.")
    troupe = db.get_one(Troupe, report.troupe_id)
    if troupe.blood_bonds != "players_manage":
        raise conflict("The troupe's staff decide this drink now, on its Bonds screen.")
    if yes:
        accept(db, user, report)
        log_report(db, user, "bond.report_confirmed", report)
        tell_reporter(db, report, f"The thrall's player confirmed {drink_line(db, report)}.")
    else:
        refuse(db, user, report, reason)
        log_report(db, user, "bond.report_declined", report, reason=report.reason)
        why = f": {report.reason}" if report.reason else "."
        tell_reporter(db, report, f"The thrall's player declined {drink_line(db, report)}{why}")


def staff_decide(db: Session, staff: User, report: BondReport, yes: bool, reason: str) -> None:
    """Staff decide a drink still waiting, from the Bonds screen: through the
    approvals queue when it is in it, so both agree."""
    if report.status != "pending":
        raise conflict(f"That drink is already {report.status}.")
    if report.approval_id is not None:
        from horatio import sheets  # imports this module

        sheets.decide(db, staff, db.get_one(Approval, report.approval_id), yes, reason.strip())
        return
    if yes:
        accept(db, staff, report)
        log_report(db, staff, "bond.report_approved", report)
        tell_reporter(db, report, f"The storytellers approved {drink_line(db, report)}.")
    else:
        refuse(db, staff, report, reason)
        log_report(db, staff, "bond.report_declined", report, reason=report.reason)
        why = f": {report.reason}" if report.reason else "."
        tell_reporter(db, report, f"The storytellers declined {drink_line(db, report)}{why}")


def visible_reports(db: Session, user: User, character: Character) -> list[BondReport]:
    """Reports on the character's card: those its player made for it, and those
    waiting on its player to confirm as thrall; pending first, then the latest few
    decided, so the player sees why one was declined."""
    if not plays(user, character):
        return []
    rows = db.scalars(
        select(BondReport)
        .where(
            BondReport.troupe_id.in_(select(Troupe.id).where(Troupe.blood_bonds != "off")),
            or_(
                and_(
                    BondReport.reported_by == user.id,
                    or_(
                        and_(
                            BondReport.reported_as == "thrall",
                            BondReport.thrall_id == character.id,
                        ),
                        and_(
                            BondReport.reported_as == "regnant",
                            BondReport.regnant_id == character.id,
                        ),
                    ),
                ),
                and_(
                    BondReport.waiting_on == "thrall",
                    BondReport.thrall_id == character.id,
                    BondReport.status == "pending",
                ),
            ),
        )
        .order_by(BondReport.created_at.desc())
    ).all()
    pending = [r for r in rows if r.status == "pending"]
    decided = [r for r in rows if r.status in ("approved", "declined")][:RECENT_DECIDED]
    return [*reversed(pending), *decided]


# How many decided reports a card keeps showing.
RECENT_DECIDED = 5


def pending_reports(db: Session, troupe: Troupe) -> list[BondReport]:
    """Drinks waiting in the troupe, for its Bonds screen, oldest first."""
    return list(
        db.scalars(
            select(BondReport)
            .where(BondReport.troupe_id == troupe.id, BondReport.status == "pending")
            .order_by(BondReport.created_at)
        )
    )
