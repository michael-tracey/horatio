"""Boonbreakers, and the status a debtor loses for ignoring a great boon
(horatio.boonbreakers; #717): for the troupe's running staff, and a Harpy with the
full ledger (#688)."""

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import boonbreakers, boons
from horatio.api.boons import (
    BoonOut,
    BoonPartyOut,
    boon_out,
    characters_of,
    full_out,
    ledger_troupe,
    party_out,
    troupe_boon,
)
from horatio.auth.deps import CurrentUser, DbSession
from horatio.boon_harpy import Keeper
from horatio.models import Boon, Boonbreaker, Character, Troupe

router = APIRouter(tags=["boons"])

AppealTo = Literal["harpy", "court"]
Outcome = Literal["granted", "refused"]


class AppealOut(BaseModel):
    to: AppealTo
    outcome: Outcome
    # A court's votes against the Boonbreaker, where given.
    against: int | None
    note: str
    # What the book says follows, for staff to carry out (p. 398).
    follows: str
    on: date
    # The Harpy it was recorded as, or "the Harpy" for staff.
    by: str


class BoonbreakerOut(BaseModel):
    id: uuid.UUID
    character: BoonPartyOut
    note: str
    declared_at: datetime
    # The Harpy who declared it, as their character; None for staff.
    declared_as: str | None
    refused: BoonOut | None
    # The boons the declaration made void, as they stand now.
    voided: list[BoonOut]
    restored: list[uuid.UUID]
    # They hold Disgraced for it now.
    disgraced: bool
    appeals: list[AppealOut]
    lifted_at: datetime | None
    lifted_note: str


class BoonbreakersOut(BaseModel):
    marks: list[BoonbreakerOut]


class BoonbreakerPreviewOut(BaseModel):
    # The open boons a declaration would make void, oldest first.
    boons: list[BoonOut]
    owed_by: int
    owed_to: int


class DeclareIn(BaseModel):
    character_id: uuid.UUID
    refused_boon_id: uuid.UUID | None = None
    note: str = Field(max_length=boons.LONGEST_TEXT)


class AppealIn(BaseModel):
    to: AppealTo
    outcome: Outcome
    against: int | None = Field(default=None, ge=0, le=boonbreakers.COURT[1])
    note: str = Field(default="", max_length=boons.LONGEST_TEXT)
    on: date | None = None
    # On mercy: the voided boons to stand again (the book doesn't say they do).
    restore: list[uuid.UUID] = Field(default=[], max_length=boons.MOST_ROWS)


class StatusLossIn(BaseModel):
    # The status was taken with the status tools; false, none will be.
    taken: bool
    note: str = Field(default="", max_length=boons.LONGEST_TEXT)


def mark_out(
    db: DbSession, mark: Boonbreaker, keeper: Keeper, marked: set[uuid.UUID]
) -> BoonbreakerOut:
    character = db.get(Character, mark.character_id)
    ids = [uuid.UUID(i) for i in mark.voided]
    if mark.refused_boon_id is not None:
        ids.append(mark.refused_boon_id)
    found: Mapping[uuid.UUID, Boon] = {
        b.id: b for b in (db.get(Boon, i) for i in dict.fromkeys(ids)) if b is not None
    }
    characters = characters_of(db, found.values())
    as_harpy = db.get(Character, mark.declared_as_id) if mark.declared_as_id else None

    def one(boon_id: uuid.UUID) -> BoonOut | None:
        boon = found.get(boon_id)
        return (
            boon_out(boon, characters, {}, keeper=keeper, marked=marked)
            if boon is not None
            else None
        )

    who = party_out(character, "", keeper.court)
    who.boonbreaker = mark.lifted_at is None
    return BoonbreakerOut(
        id=mark.id,
        character=who,
        note=mark.note,
        declared_at=mark.created_at,
        declared_as=as_harpy.name if as_harpy is not None else None,
        refused=one(mark.refused_boon_id) if mark.refused_boon_id is not None else None,
        voided=[out for i in mark.voided if (out := one(uuid.UUID(i))) is not None],
        restored=[uuid.UUID(i) for i in mark.restored],
        disgraced=mark.held_status_id is not None,
        appeals=[AppealOut(**a) for a in mark.appeals],
        lifted_at=mark.lifted_at,
        lifted_note=mark.lifted_note,
    )


def the_harpy(db: DbSession, user: CurrentUser, troupe_id: uuid.UUID) -> tuple[Troupe, Keeper]:
    """Staff, or the Harpy with the full ledger: declaring a Boonbreaker, and mercy,
    are the Harpy's (p. 397), not a Lesser Harpy's (#689)."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "edit")
    if keeper.role == "talon":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the Harpy, or staff, declare a Boonbreaker."
        )
    return troupe, keeper


def a_mark(db: DbSession, troupe: Troupe, mark_id: uuid.UUID) -> Boonbreaker:
    mark = db.get(Boonbreaker, mark_id)
    if mark is None or mark.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such Boonbreaker.")
    return mark


def a_character(db: DbSession, character_id: uuid.UUID) -> Character:
    character = db.get(Character, character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    return character


@router.get("/troupes/{troupe_id}/boonbreakers")
def troupe_boonbreakers(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BoonbreakersOut:
    """Everyone marked a Boonbreaker in the troupe's ledger, standing marks first."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "view")
    marked = boonbreakers.marked(db, troupe.id)
    return BoonbreakersOut(
        marks=[mark_out(db, m, keeper, marked) for m in boonbreakers.marks_of(db, troupe)]
    )


@router.get("/troupes/{troupe_id}/boonbreakers/preview")
def boonbreaker_preview(
    troupe_id: uuid.UUID, character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> BoonbreakerPreviewOut:
    """What declaring the character a Boonbreaker would make void, before it's done."""
    troupe, keeper = the_harpy(db, user, troupe_id)
    character = a_character(db, character_id)
    found = boonbreakers.preview(db, troupe, character)
    characters = characters_of(db, found.boons)
    marked = boonbreakers.marked(db, troupe.id)
    return BoonbreakerPreviewOut(
        boons=[boon_out(b, characters, {}, keeper=keeper, marked=marked) for b in found.boons],
        owed_by=found.owed_by,
        owed_to=found.owed_to,
    )


@router.post("/troupes/{troupe_id}/boonbreakers", status_code=status.HTTP_201_CREATED)
def declare_boonbreaker(
    troupe_id: uuid.UUID, body: DeclareIn, db: DbSession, user: CurrentUser
) -> BoonbreakerOut:
    """Declare a character a Boonbreaker (p. 397): their open boons void, both ways,
    and Disgraced while the mark stands."""
    troupe, keeper = the_harpy(db, user, troupe_id)
    character = a_character(db, body.character_id)
    mark = boonbreakers.declare(
        db, user, troupe, keeper, character, body.note, body.refused_boon_id
    )
    db.commit()
    return mark_out(db, mark, keeper, boonbreakers.marked(db, troupe.id))


@router.post("/troupes/{troupe_id}/boonbreakers/{mark_id}/appeals")
def appeal_boonbreaker(
    troupe_id: uuid.UUID, mark_id: uuid.UUID, body: AppealIn, db: DbSession, user: CurrentUser
) -> BoonbreakerOut:
    """An appeal for mercy and its outcome (p. 398). Granted, the mark is lifted and
    the boons named in `restore` stand again."""
    troupe, keeper = the_harpy(db, user, troupe_id)
    mark = a_mark(db, troupe, mark_id)
    boonbreakers.appeal(
        db,
        user,
        troupe,
        keeper,
        mark,
        body.to,
        body.outcome,
        body.note,
        body.against,
        body.on,
        body.restore,
    )
    db.commit()
    return mark_out(db, mark, keeper, boonbreakers.marked(db, troupe.id))


@router.post("/troupes/{troupe_id}/boons/{boon_id}/status-loss")
def answer_status_loss(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: StatusLossIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """For a great boon its debtor formally ignored (p. 395): staff or the Harpy took
    the status they lost, with the status tools, or won't."""
    troupe, keeper = ledger_troupe(db, user, troupe_id, "edit")
    boon = troupe_boon(db, troupe, boon_id)
    boonbreakers.answer_loss(db, user, boon, body.taken, body.note, keeper)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)
