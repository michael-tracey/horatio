"""Blood bonds (horatio.bonds): the troupe's setting; its Bonds screen, for its
running staff, to record drinks and enter, break and tell of bonds, change or take
out a drink, and decide the drinks players report; and a character's Bonds card,
which shows each viewer only what they may know, and where its player reports a
drink, or confirms one the regnant's player recorded (#661)."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from horatio import auto_bonds, bonds, vinculum
from horatio.api.downtimes import staff_troupe
from horatio.api.influence_log import CharacterChoice
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.viewing import read_only
from horatio.models import BloodBond, BondReport, Character, Troupe, TroupeMembership, User
from horatio.permissions import TroupeAction, visible_character

router = APIRouter(tags=["bonds"])

Setting = Literal["off", "staff", "players_report", "players_manage"]
Source = Literal["game", "downtime", "staff"]
# Where a player says a drink happened.
PlayerSource = Literal["game", "downtime"]
Side = Literal["thrall", "regnant"]


class BloodBondsIn(BaseModel):
    # "off", "staff", "players_report" or "players_manage" (horatio.bonds).
    setting: Setting


class PartyIn(BaseModel):
    """One side of a bond: a character in the troupe, or a name only."""

    character_id: uuid.UUID | None = None
    name: str = Field(default="", max_length=bonds.LONGEST_NAME)


class DrinkIn(BaseModel):
    night: date
    # Where it was told: at a game, in a downtime, or to staff otherwise.
    source: Source = "staff"
    note: str = Field(default="", max_length=2000)
    # Why to record it though a full bond makes the thrall immune (#665).
    override: str = Field(default="", max_length=2000)


class MeetingIn(BaseModel):
    """The thrall and regnant met, which keeps a lesser bond from ending (#665)."""

    night: date
    source: Source = "staff"
    note: str = Field(default="", max_length=2000)


class NewDrinkIn(DrinkIn):
    thrall: PartyIn
    regnant: PartyIn


class EnterIn(BaseModel):
    thrall: PartyIn
    regnant: PartyIn
    # The level it stands at, from `night`.
    level: int = Field(ge=1, le=3)
    night: date
    reason: str = Field(max_length=2000)
    # Why to enter it though a full bond makes the thrall immune (#665).
    override: str = Field(default="", max_length=2000)


class BreakIn(BaseModel):
    reason: str = Field(max_length=2000)


class KnownIn(BaseModel):
    known: bool


class FadeIn(BaseModel):
    # The day a fading bond ends: today or before ends it now.
    fades_on: date
    reason: str = Field(max_length=2000)


class PartyOut(BaseModel):
    # The character, or None for a name only.
    character_id: uuid.UUID | None
    name: str
    # pc | npc, or None for a name only.
    kind: str | None


class BondEntryOut(BaseModel):
    id: uuid.UUID
    # drink | entered | dropped (with time, #665) | meeting | vaulderie (lowered a
    # step by a Vaulderie, #666)
    kind: str
    night: date
    source: Source
    # For a bond entered, the level it stood at; dropped or lowered, the level it fell to.
    level: int | None
    note: str
    # None for a drop Horatio made by itself.
    recorded_by: str | None
    at: datetime


class ChangeOut(BaseModel):
    """What time does next to a bond (#665): it drops to two drinks, or ends, on a day."""

    kind: Literal["drop", "end"]
    on: date
    # It is due: made now, or in "players_report", waiting for staff to confirm.
    due: bool


class BondOut(BaseModel):
    id: uuid.UUID
    thrall: PartyOut
    regnant: PartyOut
    # 1 to 3, from its log.
    level: int
    # active | fading | ended | broken
    status: str
    known_to_regnant: bool
    ended_at: datetime | None
    ended_reason: str
    # A fading bond's last day; and for one fading or faded, why ("regnant_died").
    fades_on: date | None = None
    fade_reason: str = ""
    # A faded bond's thrall's player was told that it faded; until then their
    # character's sheet shows it as it was.
    thrall_told: bool = False
    # Its thrall died, and the regnant's player still sees it as it was.
    kept_for_regnant: bool = False
    # The last night it was drunk from, if any drink is logged.
    last_drink: date | None
    # When the two last met as far as Horatio knows: a drink, a meeting logged, the bond
    # entered, or a game both checked in at (#665).
    last_met: date | None = None
    # What time does to it next, for a bond time can fade.
    next_change: ChangeOut | None = None
    entries: list[BondEntryOut]


class BondReportOut(BaseModel):
    """A drink a player reported, while it waits and after it is decided."""

    id: uuid.UUID
    troupe_id: uuid.UUID
    troupe_name: str
    # A drink, or a meeting (#665).
    kind: Literal["drink", "meeting"] = "drink"
    thrall: PartyOut
    regnant: PartyOut
    # Which side the reporting player's character is on.
    reported_as: Side
    night: date
    source: PlayerSource
    note: str
    # pending | approved | declined | withdrawn
    status: str
    # Who decides it: staff, or the thrall's player.
    waiting_on: Literal["staff", "thrall"]
    # Why it was declined.
    reason: str
    reported_by: str | None
    at: datetime
    # The reader reported it and can take it back while it waits.
    can_withdraw: bool
    # The reader is the thrall's player, asked to confirm it.
    can_confirm: bool


class TroupeBondsOut(BaseModel):
    setting: Setting
    # Every bond the troupe keeps, those still felt first, then by thrall.
    bonds: list[BondOut]
    # Its characters, to name on either side.
    characters: list[CharacterChoice]
    # Drinks players reported that are still waiting, oldest first.
    reports: list[BondReportOut] = []
    # The troupe allows the Sabbat, so keeps the Vinculum and its Vaulderie log (#666).
    vinculum: bool = False
    # Vaulderies players reported that wait for staff.
    vaulderies_waiting: int = 0


class ReportTroupeOut(BaseModel):
    """A troupe the character's player can report its drinks to."""

    id: uuid.UUID
    name: str
    setting: Setting
    # Who the player can name on the other side; anyone else is a name only.
    characters: list[CharacterChoice]


class ReportIn(BaseModel):
    troupe_id: uuid.UUID
    # The side the character is on: it drank (thrall), or was drunk from (regnant).
    side: Side
    # The other side: a player character in the troupe, or a name only.
    other: PartyIn
    night: date
    source: PlayerSource = "game"
    note: str = Field(default="", max_length=2000)


class ReportedOut(BaseModel):
    # recorded: it counts now; staff: it waits on running staff; thrall: on the
    # thrall's player.
    outcome: Literal["recorded", "staff", "thrall"]
    # The bond's level now, once recorded.
    level: int | None


class PlayerMeetingIn(BaseModel):
    night: date
    source: PlayerSource = "game"
    note: str = Field(default="", max_length=2000)


class BondAnswerIn(BaseModel):
    confirm: bool
    reason: str = Field(default="", max_length=2000)


class DecideIn(BaseModel):
    approve: bool
    reason: str = Field(default="", max_length=2000)


class EntryIn(BaseModel):
    night: date
    note: str = Field(default="", max_length=2000)


class EntryRemoveIn(BaseModel):
    reason: str = Field(max_length=2000)


class EntryRemovedOut(BaseModel):
    # The bond as it is now, or None when nothing was left in its log.
    bond: BondOut | None


class SheetBondOut(BaseModel):
    """A bond on a character's Bonds card: who is on the other side, and its level."""

    id: uuid.UUID
    # The regnant, for a bond the character is bound by; the thrall, for one it holds.
    name: str
    level: int
    # The reader can log a meeting on it, as the character's player in a troupe whose
    # players report or record bonds (#665).
    can_meet: bool = False


class CharacterBondsOut(BaseModel):
    # Those the character is bound to, as thrall.
    bound_to: list[SheetBondOut]
    # Those bound to it, as regnant: for its player, only those known to the regnant.
    bound_by: list[SheetBondOut]
    # The troupe whose Bonds screen the caller may open for it, if any.
    manage_troupe_id: uuid.UUID | None
    # For its player: the troupes they can report its drinks to.
    report_to: list[ReportTroupeOut] = []
    # For its player: the drinks they reported for it, and those waiting on them to
    # confirm; waiting first, then the latest few decided.
    reports: list[BondReportOut] = []


class KnownBondOut(BaseModel):
    # embrace | sire | domitor | retainer: why Horatio knows of it (#663); `sire` is
    # the sire the childe's sheet names, with no Embrace in play (#739).
    why: Literal["embrace", "sire", "domitor", "retainer"]
    thrall: PartyOut
    regnant: PartyOut
    # The level it stands at from the start: 1, or 3 for a full bond.
    level: int
    night: date
    reason: str


class FilledOut(BaseModel):
    # The bonds added, as the Bonds screen shows them.
    added: list[BondOut]


def party_out(character: Character | None, name: str) -> PartyOut:
    if character is None:
        return PartyOut(character_id=None, name=name, kind=None)
    return PartyOut(character_id=character.id, name=character.name, kind=character.kind)


def bond_out(db: DbSession, bond: BloodBond) -> BondOut:
    thrall, regnant = bonds.parties(db, bond)
    entries = bonds.entries_of(db, bond)
    users = {
        u.id: u.display_name
        for u in db.scalars(select(User).where(User.id.in_({e.recorded_by for e in entries})))
    }
    drinks = [e.night for e in entries if e.kind == "drink"]
    troupe = db.get_one(Troupe, bond.troupe_id)
    change = bonds.next_change(db, troupe, bond, entries)
    met = bonds.last_met(db, bond, entries) if bond.status in bonds.OPEN else None
    return BondOut(
        id=bond.id,
        thrall=party_out(thrall.character, thrall.name),
        regnant=party_out(regnant.character, regnant.name),
        level=bonds.level_of(entries),
        status=bond.status,
        known_to_regnant=bond.known_to_regnant,
        ended_at=bond.ended_at,
        ended_reason=bond.ended_reason,
        fades_on=bond.fades_on,
        fade_reason=bond.fade_reason,
        thrall_told=bond.thrall_told_at is not None,
        kept_for_regnant=bond.kept_for_regnant,
        last_drink=max(drinks) if drinks else None,
        last_met=met,
        next_change=ChangeOut(
            kind=change.kind,  # type: ignore[arg-type]  # drop or end
            on=change.on,
            due=change.on <= bonds.today(),
        )
        if change is not None
        else None,
        entries=[
            BondEntryOut(
                id=e.id,
                kind=e.kind,
                night=e.night,
                source=e.source,  # type: ignore[arg-type]  # checked by the database
                level=e.level,
                note=e.note,
                recorded_by=users.get(e.recorded_by) if e.recorded_by else None,
                at=e.created_at,
            )
            for e in entries
        ],
    )


def report_out(db: DbSession, user: User, report: BondReport) -> BondReportOut:
    thrall, regnant = bonds.report_parties(db, report)
    troupe = db.get_one(Troupe, report.troupe_id)
    by = db.get(User, report.reported_by)
    return BondReportOut(
        id=report.id,
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        kind=report.kind,  # type: ignore[arg-type]  # checked by the database
        thrall=party_out(thrall.character, thrall.name),
        regnant=party_out(regnant.character, regnant.name),
        reported_as=report.reported_as,  # type: ignore[arg-type]  # checked by the database
        night=report.night,
        source=report.source,  # type: ignore[arg-type]  # checked by the database
        note=report.note,
        status=report.status,
        waiting_on=report.waiting_on,  # type: ignore[arg-type]  # checked by the database
        reason=report.reason,
        reported_by=by.display_name if by else None,
        at=report.created_at,
        can_withdraw=bonds.can_withdraw(user, report),
        can_confirm=bonds.answers(user, report, thrall.character)
        and troupe.blood_bonds == "players_manage",
    )


def bonds_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, for its running staff, while it tracks bonds. Switched off, there
    is nothing to see."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_BONDS)
    if not bonds.tracked(troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe doesn't track blood bonds.")
    # Fading bonds whose day has come end before anyone looks at them.
    bonds.settle_fades(db, [troupe.id])
    return troupe


def troupe_bond(db: DbSession, troupe: Troupe, bond_id: uuid.UUID) -> BloodBond:
    bond = db.get(BloodBond, bond_id)
    if bond is None or bond.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such bond.")
    return bond


def side(db: DbSession, troupe: Troupe, given: PartyIn, *, regnant: bool) -> bonds.Party:
    return bonds.party(db, troupe, given.character_id, given.name, regnant=regnant)


@router.put("/troupes/{troupe_id}/blood-bonds")
def set_blood_bonds(
    troupe_id: uuid.UUID, body: BloodBondsIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """How far Horatio tracks the troupe's blood bonds. Off hides them everywhere;
    what was recorded is kept, and comes back when it is switched on again."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    bonds.set_setting(db, user, troupe, body.setting)
    db.commit()
    return troupe_out(db, user, troupe)


@router.get("/troupes/{troupe_id}/bonds")
def troupe_bonds(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeBondsOut:
    """Every bond the troupe keeps, with its log, for its running staff."""
    troupe = bonds_troupe(db, user, troupe_id)
    db.commit()
    found = [
        bond_out(db, b)
        for b in db.scalars(select(BloodBond).where(BloodBond.troupe_id == troupe.id))
    ]
    found.sort(
        key=lambda b: (
            b.status not in bonds.OPEN,
            b.thrall.name.casefold(),
            b.regnant.name.casefold(),
        )
    )
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe.id, TroupeMembership.left_at.is_(None)
    )
    characters = db.scalars(
        select(Character)
        .where(
            or_(Character.id.in_(members), Character.owner_troupe_id == troupe.id),
            Character.status != "retired",
        )
        .order_by(Character.name)
    )
    return TroupeBondsOut(
        setting=troupe.blood_bonds,  # type: ignore[arg-type]  # checked by the database
        bonds=found,
        characters=[
            CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=True) for c in characters
        ],
        reports=[report_out(db, user, r) for r in bonds.pending_reports(db, troupe)],
        vinculum=vinculum.on(troupe),
        vaulderies_waiting=len(vinculum.pending(db, troupe)) if vinculum.on(troupe) else 0,
    )


def known_out(item: auto_bonds.Known) -> KnownBondOut:
    return KnownBondOut(
        why=item.why,  # type: ignore[arg-type]  # one of auto_bonds' four
        thrall=party_out(item.thrall.character, item.thrall.name),
        regnant=party_out(item.regnant.character, item.regnant.name),
        level=item.level,
        night=item.night,
        reason=item.reason,
    )


@router.get("/troupes/{troupe_id}/bonds/known")
def known_bonds(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[KnownBondOut]:
    """The bonds Horatio can work out for the troupe that it doesn't keep yet: from its
    characters' Embraces and the sires their sheets name, ghouls' domitors and vampires'
    ghoul Retainers (#663, #739)."""
    troupe = bonds_troupe(db, user, troupe_id)
    found = auto_bonds.known(db, troupe)
    db.commit()
    return [known_out(item) for item in found]


@router.post("/troupes/{troupe_id}/bonds/known")
def fill_in_bonds(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> FilledOut:
    """Add every bond `known_bonds` lists, and say which were added."""
    troupe = bonds_troupe(db, user, troupe_id)
    added = auto_bonds.fill_in(db, user, troupe)
    db.commit()
    return FilledOut(added=[bond_out(db, bond) for bond in added])


@router.post("/troupes/{troupe_id}/bonds/drinks", status_code=status.HTTP_201_CREATED)
def record_drink(
    troupe_id: uuid.UUID, body: NewDrinkIn, db: DbSession, user: CurrentUser
) -> BondOut:
    """Log a drink the thrall took of the regnant's blood: on the bond between them,
    or a new one."""
    troupe = bonds_troupe(db, user, troupe_id)
    thrall = side(db, troupe, body.thrall, regnant=False)
    regnant = side(db, troupe, body.regnant, regnant=True)
    override = bonds.staff_immunity(db, troupe, thrall, regnant, body.override)
    bond = bonds.record_drink(db, user, troupe, thrall, regnant, body.night, body.source, body.note)
    bonds.log_override(db, user, bond, override)
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds/{bond_id}/drinks", status_code=status.HTTP_201_CREATED)
def add_drink(
    troupe_id: uuid.UUID, bond_id: uuid.UUID, body: DrinkIn, db: DbSession, user: CurrentUser
) -> BondOut:
    """Log another drink on a bond still felt."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    thrall, regnant = bonds.parties(db, bond)
    override = bonds.staff_immunity(db, troupe, thrall, regnant, body.override)
    bonds.add_drink(db, user, bond, body.night, body.source, body.note)
    bonds.log_override(db, user, bond, override)
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds/{bond_id}/meetings", status_code=status.HTTP_201_CREATED)
def add_meeting(
    troupe_id: uuid.UUID, bond_id: uuid.UUID, body: MeetingIn, db: DbSession, user: CurrentUser
) -> BondOut:
    """Log the thrall and regnant meeting, such as in a downtime: it keeps a lesser bond
    from ending (#665)."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    bonds.add_meeting(db, user, bond, body.night, body.source, body.note)
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds/{bond_id}/confirm-change")
def confirm_change(
    troupe_id: uuid.UUID, bond_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> BondOut:
    """Staff confirm the change time has brought a bond, in a troupe where players
    report and staff approve (#665): it drops to two drinks, or ends."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    bonds.confirm_change(db, user, troupe, bond)
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds", status_code=status.HTTP_201_CREATED)
def enter_bond(troupe_id: uuid.UUID, body: EnterIn, db: DbSession, user: CurrentUser) -> BondOut:
    """Enter a bond that already stands, such as one from before Horatio, at its
    level, with the reason."""
    troupe = bonds_troupe(db, user, troupe_id)
    thrall = side(db, troupe, body.thrall, regnant=False)
    regnant = side(db, troupe, body.regnant, regnant=True)
    override = bonds.staff_immunity(db, troupe, thrall, regnant, body.override)
    bond = bonds.enter_bond(db, user, troupe, thrall, regnant, body.level, body.night, body.reason)
    bonds.log_override(db, user, bond, override)
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds/{bond_id}/break")
def break_bond(
    troupe_id: uuid.UUID, bond_id: uuid.UUID, body: BreakIn, db: DbSession, user: CurrentUser
) -> BondOut:
    """Mark the bond broken, with the reason (p. 296)."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    bonds.break_bond(db, user, bond, body.reason)
    db.commit()
    return bond_out(db, bond)


@router.put("/troupes/{troupe_id}/bonds/{bond_id}/known")
def set_known(
    troupe_id: uuid.UUID, bond_id: uuid.UUID, body: KnownIn, db: DbSession, user: CurrentUser
) -> BondOut:
    """Whether the regnant's player is told of the bond, and sees it."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    bonds.set_known(db, user, bond, body.known)
    db.commit()
    return bond_out(db, bond)


@router.put("/troupes/{troupe_id}/bonds/{bond_id}/fade")
def set_fade(
    troupe_id: uuid.UUID, bond_id: uuid.UUID, body: FadeIn, db: DbSession, user: CurrentUser
) -> BondOut:
    """Move the day a fading bond ends, with the reason: to today or before, it ends
    now, as faded."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    bonds.set_fade(db, user, bond, body.fades_on, body.reason)
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds/{bond_id}/clear-kept")
def clear_kept(
    troupe_id: uuid.UUID, bond_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> BondOut:
    """Stop showing the regnant's player a bond whose thrall died."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    bonds.clear_kept(db, user, bond)
    db.commit()
    return bond_out(db, bond)


@router.patch("/troupes/{troupe_id}/bonds/{bond_id}/entries/{entry_id}")
def change_entry(
    troupe_id: uuid.UUID,
    bond_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: EntryIn,
    db: DbSession,
    user: CurrentUser,
) -> BondOut:
    """Change a drink's night or note in the bond's log, such as one a player recorded
    wrongly."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    bonds.change_entry(db, user, bond, bonds.entry_of(db, bond, entry_id), body.night, body.note)
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds/{bond_id}/entries/{entry_id}/remove")
def remove_entry(
    troupe_id: uuid.UUID,
    bond_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: EntryRemoveIn,
    db: DbSession,
    user: CurrentUser,
) -> EntryRemovedOut:
    """Take a drink out of the bond's log, with the reason. A bond left with nothing
    in its log goes too."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    kept = bonds.remove_entry(db, user, bond, bonds.entry_of(db, bond, entry_id), body.reason)
    db.commit()
    return EntryRemovedOut(bond=bond_out(db, bond) if kept else None)


@router.post("/troupes/{troupe_id}/bonds/reports/{report_id}/decide")
def decide_report(
    troupe_id: uuid.UUID, report_id: uuid.UUID, body: DecideIn, db: DbSession, user: CurrentUser
) -> BondReportOut:
    """Approve or decline a drink a player reported, still waiting: whether it waits
    on staff or on the thrall's player."""
    troupe = bonds_troupe(db, user, troupe_id)
    report = bonds.report_of(db, report_id)
    if report.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such drink is waiting.")
    bonds.staff_decide(db, user, report, body.approve, body.reason)
    db.commit()
    return report_out(db, user, report)


def players_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    character = visible_character(db, user, character_id)
    if not bonds.plays(user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only its player reports its drinks.")
    return character


def mine_report(db: DbSession, character: Character, report_id: uuid.UUID) -> BondReport:
    report = db.get(BondReport, report_id)
    if report is None or character.id not in (report.thrall_id, report.regnant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such drink.")
    troupe = db.get_one(Troupe, report.troupe_id)
    if not bonds.tracked(troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe doesn't track blood bonds.")
    return report


@router.post("/characters/{character_id}/bonds/reports", status_code=status.HTTP_201_CREATED)
def report_drink(
    character_id: uuid.UUID, body: ReportIn, db: DbSession, user: CurrentUser
) -> ReportedOut:
    """Its player reports a drink for the character: it drank of a vampire's blood,
    or a character drank of its blood. Whether it counts now or waits, and on whom,
    follows the troupe's setting (horatio.bonds)."""
    character = players_character(db, user, character_id)
    troupe = next(
        (t for t in bonds.report_troupes(db, user, character) if t.id == body.troupe_id), None
    )
    if troupe is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Players don't report drinks in that troupe.")
    other = bonds.other_side(
        db,
        troupe,
        character,
        body.other.character_id,
        body.other.name,
        regnant=body.side == "thrall",
    )
    done = bonds.report_drink(
        db, user, troupe, character, body.side, other, body.night, body.source, body.note
    )
    db.commit()
    if isinstance(done, BloodBond):
        return ReportedOut(outcome="recorded", level=bonds.level(db, done))
    return ReportedOut(outcome=done.waiting_on, level=None)  # type: ignore[arg-type]


@router.post(
    "/characters/{character_id}/bonds/{bond_id}/meetings", status_code=status.HTTP_201_CREATED
)
def report_meeting(
    character_id: uuid.UUID,
    bond_id: uuid.UUID,
    body: PlayerMeetingIn,
    db: DbSession,
    user: CurrentUser,
) -> ReportedOut:
    """Its player logs the character meeting the other side of a bond it is in (#665):
    it counts now, or waits on staff, by the troupe's setting (horatio.bonds)."""
    character = players_character(db, user, character_id)
    bond = db.get(BloodBond, bond_id)
    if bond is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such bond.")
    done = bonds.report_meeting(db, user, character, bond, body.night, body.source, body.note)
    db.commit()
    if isinstance(done, BloodBond):
        return ReportedOut(outcome="recorded", level=None)
    return ReportedOut(outcome="staff", level=None)


@router.post("/characters/{character_id}/bonds/reports/{report_id}/withdraw")
def withdraw_report(
    character_id: uuid.UUID, report_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> BondReportOut:
    """Take back a drink its player reported, while it waits."""
    character = players_character(db, user, character_id)
    report = mine_report(db, character, report_id)
    bonds.withdraw(db, user, report)
    db.commit()
    return report_out(db, user, report)


@router.post("/characters/{character_id}/bonds/reports/{report_id}/answer")
def answer_report(
    character_id: uuid.UUID,
    report_id: uuid.UUID,
    body: BondAnswerIn,
    db: DbSession,
    user: CurrentUser,
) -> BondReportOut:
    """The thrall's player confirms or declines a drink the regnant's player recorded."""
    character = players_character(db, user, character_id)
    report = mine_report(db, character, report_id)
    bonds.confirm(db, user, report, body.confirm, body.reason)
    db.commit()
    return report_out(db, user, report)


@router.get("/characters/{character_id}/bonds")
def character_bonds(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CharacterBondsOut:
    """The bonds still felt that the character is in, as the caller may know of
    them: all of them for the running staff of the troupe that keeps one; its
    player's own as thrall; and as regnant, only those known to the regnant. A
    fading bond shows to the thrall's player just as before, and one that has faded
    too, until they are told it faded; one whose thrall died, to the regnant's player
    who knew of it, until staff clear it (#662)."""
    character = visible_character(db, user, character_id)
    settle = not read_only(db)
    seen = bonds.seen_by(db, user, character, settle=settle)
    if settle:
        db.commit()
    bound_to: list[SheetBondOut] = []
    bound_by: list[SheetBondOut] = []
    manage: uuid.UUID | None = None
    for s in seen:
        bond, troupe, thrall, regnant = s.bond, s.troupe, s.thrall, s.regnant
        level = s.level
        meet = (
            bond.status == "active"
            and bonds.for_players(troupe)
            and character.status != "retired"
            and bonds.plays(user, character)
        )
        if bond.thrall_id == character.id:
            bound_to.append(
                SheetBondOut(id=bond.id, name=regnant.shown, level=level, can_meet=meet)
            )
        else:
            bound_by.append(SheetBondOut(id=bond.id, name=thrall.shown, level=level, can_meet=meet))
        if manage is None and bonds.can_manage(db, user, troupe):
            manage = troupe.id
    home_id = character.home_troupe_id or character.owner_troupe_id
    if manage is None and home_id is not None:
        # Staff open the Bonds screen from a sheet that has no bonds yet.
        home = db.get_one(Troupe, home_id)
        if bonds.tracked(home) and bonds.can_manage(db, user, home):
            manage = home.id
    report_to = [
        ReportTroupeOut(
            id=t.id,
            name=t.name,
            setting=t.blood_bonds,  # type: ignore[arg-type]  # checked by the database
            characters=[
                CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=True)
                for c in bonds.player_choices(db, t, character)
            ],
        )
        for t in bonds.report_troupes(db, user, character)
    ]
    return CharacterBondsOut(
        bound_to=bound_to,
        bound_by=bound_by,
        manage_troupe_id=manage,
        report_to=report_to,
        reports=[report_out(db, user, r) for r in bonds.visible_reports(db, user, character)],
    )
