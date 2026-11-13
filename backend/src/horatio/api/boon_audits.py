"""Audits of a character's boons (horatio.boon_audits, #690): made from the troupe's
ledger by its staff, its Harpy or a Lesser Harpy allowed to, kept as they were, and
given to a character whose player reads them in the Play View."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import boon_audits, boons
from horatio.api.boons import Kind, choices_for, ledger_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.boon_harpy import Keeper, keeper
from horatio.models import BoonAudit, Character, Troupe, User
from horatio.permissions import visible_character

router = APIRouter(tags=["boons"])

CourtStanding = Literal["active", "final_death", "off_field", "gone"]
AuditStatus = Literal["standing", "settled", "departed"]
AuditSettled = Literal["called_in", "forgiven", "ignored"]


class BoonAuditIn(BaseModel):
    # Whose boons.
    character_id: uuid.UUID
    # Given at once to this player character, if named.
    given_to_id: uuid.UUID | None = None


class BoonAuditGiveIn(BaseModel):
    character_id: uuid.UUID


class BoonAuditLineOut(BaseModel):
    other: str
    kind: Kind
    made_on: date
    reason: str
    conditions: str
    status: AuditStatus
    settled_how: AuditSettled | None = None


class BoonAuditSummaryOut(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    troupe_name: str
    # When it was made: what it shows is the ledger as it was then.
    made_at: datetime
    # Whose boons.
    name: str
    # Who made it: the character it was made as, or "The troupe's staff".
    made_by: str
    # Who it was given to, and when; None until it is.
    given_to: str | None
    given_at: datetime | None
    # The caller may give it now: they made it, and it hasn't been given.
    can_give: bool = False


class BoonAuditOut(BoonAuditSummaryOut):
    clan: str | None
    age: str | None
    # As the court knows it (horatio.boon_audits.court_standing, horatio.court_knows).
    standing: CourtStanding | None
    # Standing boons they owe and are owed (departed ones too), and what they weigh.
    owes_count: int
    owed_count: int
    owes_weight: float
    owed_weight: float
    owes: list[BoonAuditLineOut]
    owed: list[BoonAuditLineOut]


class BoonAuditChoice(BaseModel):
    id: uuid.UUID
    name: str


class TroupeBoonAuditsOut(BaseModel):
    troupe_id: uuid.UUID
    # The caller may make audits here.
    can_audit: bool
    audits: list[BoonAuditSummaryOut]
    # Whose boons can be audited: the ledger's characters.
    subjects: list[BoonAuditChoice]
    # Who an audit can be given to: player characters in play.
    recipients: list[BoonAuditChoice]


def maker_of(db: DbSession, found: BoonAudit) -> str:
    if found.as_character_id is None:
        return "The troupe's staff"
    character = db.get(Character, found.as_character_id)
    return character.name if character is not None else "Someone no longer in Horatio"


def summary_out(
    db: DbSession, found: BoonAudit, troupe: Troupe, keeper_: Keeper | None
) -> BoonAuditSummaryOut:
    given = db.get(Character, found.given_to_id) if found.given_to_id else None
    return BoonAuditSummaryOut(
        id=found.id,
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        made_at=found.created_at,
        name=str(found.contents.get("name", "")),
        made_by=maker_of(db, found),
        given_to=given.name if given is not None else None,
        given_at=found.given_at,
        can_give=keeper_ is not None and boon_audits.may_give(keeper_, found),
    )


def audit_out(
    db: DbSession, found: BoonAudit, troupe: Troupe, keeper_: Keeper | None
) -> BoonAuditOut:
    c: dict[str, Any] = found.contents
    return BoonAuditOut(
        **summary_out(db, found, troupe, keeper_).model_dump(),
        clan=c.get("clan"),
        age=c.get("age"),
        standing=c.get("standing"),
        owes_count=c.get("owes_count", 0),
        owed_count=c.get("owed_count", 0),
        owes_weight=c.get("owes_weight", 0.0),
        owed_weight=c.get("owed_weight", 0.0),
        owes=[BoonAuditLineOut(**line) for line in c.get("owes", [])],
        owed=[BoonAuditLineOut(**line) for line in c.get("owed", [])],
    )


def troupe_character(db: DbSession, troupe: Troupe, character_id: uuid.UUID) -> Character:
    character = db.get(Character, character_id)
    if character is None or not boons.in_troupe(db, troupe, character):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character in this troupe.")
    return character


def subjects(db: DbSession, troupe: Troupe, keeper_: Keeper) -> list[BoonAuditChoice]:
    """The characters whose boons the caller can audit: those the ledger can name, as
    they pick them for a boon (a Harpy picks among player characters and the NPCs the
    ledger names already)."""
    return [
        BoonAuditChoice(id=c.id, name=c.name)
        for c in choices_for(db, troupe, keeper_)
        if c.in_troupe
    ]


@router.get("/troupes/{troupe_id}/boon-audits")
def troupe_audits(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeBoonAuditsOut:
    """The troupe's audits the caller sees, newest first, and whom they can audit and
    give one to: for its staff, and a Harpy or Lesser Harpy who may perform audits."""
    troupe, found = ledger_troupe(db, user, troupe_id, "audit")
    return TroupeBoonAuditsOut(
        troupe_id=troupe.id,
        can_audit="audit" in found.can,
        audits=[
            summary_out(db, a, troupe, found) for a in boon_audits.of_troupe(db, troupe, found)
        ],
        subjects=subjects(db, troupe, found),
        recipients=[
            BoonAuditChoice(id=c.id, name=c.name) for c in boon_audits.recipients(db, troupe)
        ],
    )


@router.post("/troupes/{troupe_id}/boon-audits", status_code=status.HTTP_201_CREATED)
def make_audit(
    troupe_id: uuid.UUID, body: BoonAuditIn, db: DbSession, user: CurrentUser
) -> BoonAuditOut:
    """Audit a character's boons as the ledger holds them now; given at once to a
    player character, if named."""
    troupe, found = ledger_troupe(db, user, troupe_id, "audit")
    if body.character_id not in {s.id for s in subjects(db, troupe, found)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character to audit.")
    character = troupe_character(db, troupe, body.character_id)
    to = troupe_character(db, troupe, body.given_to_id) if body.given_to_id else None
    made = boon_audits.make(db, user, troupe, found, character, to)
    db.commit()
    return audit_out(db, made, troupe, found)


def troupe_audit(db: DbSession, troupe: Troupe, keeper_: Keeper, audit_id: uuid.UUID) -> BoonAudit:
    found = db.get(BoonAudit, audit_id)
    if found is None or found.troupe_id != troupe.id or not boon_audits.seen_by(keeper_, found):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such audit.")
    return found


@router.post("/troupes/{troupe_id}/boon-audits/{audit_id}/give")
def give_audit(
    troupe_id: uuid.UUID,
    audit_id: uuid.UUID,
    body: BoonAuditGiveIn,
    db: DbSession,
    user: CurrentUser,
) -> BoonAuditOut:
    """Give an audit to a player character in play in the troupe, once."""
    troupe, found = ledger_troupe(db, user, troupe_id, "audit")
    made = troupe_audit(db, troupe, found, audit_id)
    to = troupe_character(db, troupe, body.character_id)
    boon_audits.give(db, user, troupe, found, made, to)
    db.commit()
    return audit_out(db, made, troupe, found)


def reader(db: DbSession, user: User, found: BoonAudit) -> Keeper | None | bool:
    """Whether `user` may read the audit: as one who keeps the troupe's ledger (the
    Keeper), or as the player of the character it was given to (True). False else."""
    troupe = db.get(Troupe, found.troupe_id)
    if troupe is None or not boons.tracked(troupe):
        return False
    found_keeper = keeper(db, user, troupe, "audit")
    if found_keeper is not None and boon_audits.seen_by(found_keeper, found):
        return found_keeper
    if found.given_to_id is not None:
        given = db.get(Character, found.given_to_id)
        if given is not None and given.player_id == user.id:
            return True
    return False


@router.get("/boon-audits/{audit_id}")
def read_audit(audit_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BoonAuditOut:
    """One audit, as it was made: for whoever keeps the troupe's ledger and may see it,
    and for the player of the character it was given to."""
    found = db.get(BoonAudit, audit_id)
    who = reader(db, user, found) if found is not None else False
    if found is None or who is False:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such audit.")
    troupe = db.get(Troupe, found.troupe_id)
    assert troupe is not None  # checked by reader
    return audit_out(db, found, troupe, who if isinstance(who, Keeper) else None)


@router.get("/characters/{character_id}/boon-audits")
def character_audits(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[BoonAuditSummaryOut]:
    """The audits given to the character, newest first: for its player, and the staff
    of the troupe each was made in."""
    character = visible_character(db, user, character_id)
    out: list[BoonAuditSummaryOut] = []
    for found in boon_audits.given_to(db, character):
        troupe = db.get(Troupe, found.troupe_id)
        if troupe is None:
            continue
        if character.player_id != user.id and not boons.can_manage(db, user, troupe):
            continue
        out.append(summary_out(db, found, troupe, None))
    return out
