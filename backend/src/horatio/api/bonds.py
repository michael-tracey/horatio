"""Blood bonds (horatio.bonds): the troupe's setting; its Bonds screen, for its
running staff, to record drinks and enter, break and tell of bonds; and a
character's Bonds card, which shows each viewer only what they may know."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from horatio import bonds
from horatio.api.downtimes import staff_troupe
from horatio.api.influence_log import CharacterChoice
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import BloodBond, Character, Troupe, TroupeMembership, User
from horatio.permissions import TroupeAction, visible_character

router = APIRouter(tags=["bonds"])

Setting = Literal["off", "staff", "players_report", "players_manage"]
Source = Literal["game", "downtime", "staff"]


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


class BreakIn(BaseModel):
    reason: str = Field(max_length=2000)


class KnownIn(BaseModel):
    known: bool


class PartyOut(BaseModel):
    # The character, or None for a name only.
    character_id: uuid.UUID | None
    name: str
    # pc | npc, or None for a name only.
    kind: str | None


class BondEntryOut(BaseModel):
    id: uuid.UUID
    # drink | entered
    kind: str
    night: date
    source: Source
    # For a bond entered: the level it stood at.
    level: int | None
    note: str
    recorded_by: str | None
    at: datetime


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
    # The last night it was drunk from, if any drink is logged.
    last_drink: date | None
    entries: list[BondEntryOut]


class TroupeBondsOut(BaseModel):
    setting: Setting
    # Every bond the troupe keeps, those still felt first, then by thrall.
    bonds: list[BondOut]
    # Its characters, to name on either side.
    characters: list[CharacterChoice]


class SheetBondOut(BaseModel):
    """A bond on a character's Bonds card: who is on the other side, and its level."""

    id: uuid.UUID
    # The regnant, for a bond the character is bound by; the thrall, for one it holds.
    name: str
    level: int


class CharacterBondsOut(BaseModel):
    # Those the character is bound to, as thrall.
    bound_to: list[SheetBondOut]
    # Those bound to it, as regnant: for its player, only those known to the regnant.
    bound_by: list[SheetBondOut]
    # The troupe whose Bonds screen the caller may open for it, if any.
    manage_troupe_id: uuid.UUID | None


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
    return BondOut(
        id=bond.id,
        thrall=party_out(thrall.character, thrall.name),
        regnant=party_out(regnant.character, regnant.name),
        level=bonds.level_of(entries),
        status=bond.status,
        known_to_regnant=bond.known_to_regnant,
        ended_at=bond.ended_at,
        ended_reason=bond.ended_reason,
        last_drink=max(drinks) if drinks else None,
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


def bonds_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, for its running staff, while it tracks bonds. Switched off, there
    is nothing to see."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_BONDS)
    if not bonds.tracked(troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe doesn't track blood bonds.")
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
    )


@router.post("/troupes/{troupe_id}/bonds/drinks", status_code=status.HTTP_201_CREATED)
def record_drink(
    troupe_id: uuid.UUID, body: NewDrinkIn, db: DbSession, user: CurrentUser
) -> BondOut:
    """Log a drink the thrall took of the regnant's blood: on the bond between them,
    or a new one."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = bonds.record_drink(
        db,
        user,
        troupe,
        side(db, troupe, body.thrall, regnant=False),
        side(db, troupe, body.regnant, regnant=True),
        body.night,
        body.source,
        body.note,
    )
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds/{bond_id}/drinks", status_code=status.HTTP_201_CREATED)
def add_drink(
    troupe_id: uuid.UUID, bond_id: uuid.UUID, body: DrinkIn, db: DbSession, user: CurrentUser
) -> BondOut:
    """Log another drink on a bond still felt."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = troupe_bond(db, troupe, bond_id)
    bonds.add_drink(db, user, bond, body.night, body.source, body.note)
    db.commit()
    return bond_out(db, bond)


@router.post("/troupes/{troupe_id}/bonds", status_code=status.HTTP_201_CREATED)
def enter_bond(troupe_id: uuid.UUID, body: EnterIn, db: DbSession, user: CurrentUser) -> BondOut:
    """Enter a bond that already stands, such as one from before Horatio, at its
    level, with the reason."""
    troupe = bonds_troupe(db, user, troupe_id)
    bond = bonds.enter_bond(
        db,
        user,
        troupe,
        side(db, troupe, body.thrall, regnant=False),
        side(db, troupe, body.regnant, regnant=True),
        body.level,
        body.night,
        body.reason,
    )
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


@router.get("/characters/{character_id}/bonds")
def character_bonds(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CharacterBondsOut:
    """The bonds still felt that the character is in, as the caller may know of
    them: all of them for the running staff of the troupe that keeps one; its
    player's own as thrall; and as regnant, only those known to the regnant."""
    character = visible_character(db, user, character_id)
    found = db.scalars(
        select(BloodBond)
        .where(
            or_(BloodBond.thrall_id == character.id, BloodBond.regnant_id == character.id),
            BloodBond.status.in_(bonds.OPEN),
        )
        .order_by(BloodBond.created_at)
    ).all()
    troupes = {
        t.id: t
        for t in db.scalars(select(Troupe).where(Troupe.id.in_({b.troupe_id for b in found})))
    }
    bound_to: list[SheetBondOut] = []
    bound_by: list[SheetBondOut] = []
    manage: uuid.UUID | None = None
    for bond in found:
        troupe = troupes[bond.troupe_id]
        thrall, regnant = bonds.parties(db, bond)
        if not bonds.shown_to(db, user, bond, troupe, thrall.character, regnant.character):
            continue
        level = bonds.level(db, bond)
        if bond.thrall_id == character.id:
            bound_to.append(SheetBondOut(id=bond.id, name=regnant.shown, level=level))
        else:
            bound_by.append(SheetBondOut(id=bond.id, name=thrall.shown, level=level))
        if manage is None and bonds.can_manage(db, user, troupe):
            manage = troupe.id
    home_id = character.home_troupe_id or character.owner_troupe_id
    if manage is None and home_id is not None:
        # Staff open the Bonds screen from a sheet that has no bonds yet.
        home = db.get_one(Troupe, home_id)
        if bonds.tracked(home) and bonds.can_manage(db, user, home):
            manage = home.id
    return CharacterBondsOut(bound_to=bound_to, bound_by=bound_by, manage_troupe_id=manage)
