"""Reviewing boons (horatio.boon_reviews, #687): the troupe's review setting, the
review queue for its running staff, accepting and rejecting boons that wait for
review, flags raised and cleared, and linking a name to a character."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import boon_harpy, boon_reviews, boons
from horatio.api.boons import (
    BoonOut,
    boon_out,
    characters_of,
    choices_for,
    flag_out,
    full_out,
    harpy_choices,
    troupe_boon,
    users_of,
)
from horatio.api.downtimes import staff_troupe
from horatio.api.influence_log import CharacterChoice
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.boon_harpy import Keeper
from horatio.models import BoonFlag, Character, Troupe, User
from horatio.permissions import TroupeAction

router = APIRouter(tags=["boons"])

Note = Field(default="", max_length=boons.LONGEST_TEXT)


class BoonReviewIn(BaseModel):
    # Boons players report wait for review; off, they stand at once.
    hold: bool


class BoonReviewOut(BaseModel):
    # Every boon waiting for review or with a flag raised, oldest first, each with its
    # flags.
    boons: list[BoonOut]
    # The characters the reviewer may link a name to (a Harpy, #688, only those
    # players may know).
    characters: list[CharacterChoice] = []


class AcceptIn(BaseModel):
    note: str = Note


class RejectIn(BaseModel):
    # Why it isn't accepted: its reporter sees it.
    reason: str = Field(max_length=boons.LONGEST_TEXT)


class FlagIn(BaseModel):
    # Why it needs a ruling.
    note: str = Field(max_length=boons.LONGEST_TEXT)


class ClearIn(BaseModel):
    note: str = Note


class LinkIn(BaseModel):
    side: Literal["debtor", "creditor"]
    character_id: uuid.UUID
    # On every boon in the ledger that names it, not only this one.
    everywhere: bool = False
    note: str = Note


class LinkOut(BaseModel):
    # How many boons now name the character.
    linked: int
    # Boons naming the name where the character is already on the other side.
    skipped: int


def review_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> tuple[Troupe, Keeper]:
    """The troupe, for those who review its boons, while it keeps a ledger, and who
    `user` reviews as: its running staff, or a Harpy given the review queue (#688)."""
    troupe = db.get(Troupe, troupe_id)
    keeper = boon_harpy.keeper(db, user, troupe, "submissions") if troupe is not None else None
    if troupe is None or keeper is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    if not boons.tracked(troupe):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This troupe doesn't keep a boon ledger.")
    return troupe, keeper


@router.put("/troupes/{troupe_id}/boon-review")
def set_boon_review(
    troupe_id: uuid.UUID, body: BoonReviewIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """Whether boons the troupe's players report wait for review before they stand."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    boon_reviews.set_review(db, user, troupe, body.hold)
    db.commit()
    return troupe_out(db, user, troupe)


@router.get("/troupes/{troupe_id}/boon-review")
def review_queue(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BoonReviewOut:
    """The review queue: every boon waiting for review or with a flag raised."""
    troupe, keeper = review_troupe(db, user, troupe_id)
    found = boon_reviews.queue(db, troupe)
    flags = boon_reviews.raised(db, [b.id for b in found])
    users = users_of(db, [*(b.submitted_by for b in found), *(f.raised_by for f in flags)])
    characters = characters_of(db, found)
    out: list[BoonOut] = []
    for b in found:
        row = boon_out(b, characters, users, keeper=keeper)
        row.flags = [flag_out(f, users) for f in flags if f.boon_id == b.id]
        out.append(row)
    return BoonReviewOut(boons=out, characters=choices_for(db, troupe, keeper))


@router.post("/troupes/{troupe_id}/boons/{boon_id}/accept")
def accept(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: AcceptIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """A boon waiting for review stands: it was reviewed, perhaps edited first."""
    troupe, keeper = review_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    boon_reviews.accept(db, user, boon, body.note, keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/reject")
def reject(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: RejectIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """A boon waiting for review isn't accepted, with a reason its reporter sees."""
    troupe, keeper = review_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    boon_reviews.reject(db, user, boon, body.reason, keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/flags", status_code=status.HTTP_201_CREATED)
def flag(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: FlagIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Flag a boon by hand for a ruling, with a note."""
    troupe, keeper = review_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    boon_reviews.flag(db, user, boon, body.note, keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boon-flags/{flag_id}/clear")
def clear(
    troupe_id: uuid.UUID, flag_id: uuid.UUID, body: ClearIn, db: DbSession, user: CurrentUser
) -> BoonOut:
    """Clear a flag, with an optional note: the name is right as it is, say."""
    troupe, keeper = review_troupe(db, user, troupe_id)
    found = db.get(BoonFlag, flag_id)
    boon = troupe_boon(db, troupe, found.boon_id) if found is not None else None
    if found is None or boon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such flag.")
    boon_reviews.clear(db, user, found, body.note, keeper.character)
    db.commit()
    return full_out(db, user, troupe, boon, keeper)


@router.post("/troupes/{troupe_id}/boons/{boon_id}/link")
def link(
    troupe_id: uuid.UUID, boon_id: uuid.UUID, body: LinkIn, db: DbSession, user: CurrentUser
) -> LinkOut:
    """Put a character in place of a name on a boon, or on every boon naming it."""
    troupe, keeper = review_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    character = db.get(Character, body.character_id)
    if character is None or (
        not keeper.staff and character.id not in {c.id for c in harpy_choices(db, troupe)}
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such character.")
    linked, skipped = boon_reviews.link(
        db,
        user,
        troupe,
        boon,
        body.side,
        character,
        body.everywhere,
        body.note,
        keeper.character,
    )
    db.commit()
    return LinkOut(linked=linked, skipped=skipped)
