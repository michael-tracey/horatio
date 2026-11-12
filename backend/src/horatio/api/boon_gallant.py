"""Gallant for repaying a boon (horatio.boon_gallant, #693): answering the offer, by
the troupe's running staff from the ledger, or by the creditor's player (or staff)
from the Play View's Boons tab."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import boon_gallant, boons
from horatio.api.boons import (
    BoonOut,
    PlayBoonsOut,
    Text,
    full_out,
    in_play,
    ledger_troupe,
    play_ledger,
    play_out,
    player_sees,
    troupe_boon,
)
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Boon

router = APIRouter(tags=["boons"])


class GallantAnswerIn(BaseModel):
    # Give the debtor Gallant, or not.
    give: bool
    note: str = Text


def open_offer(db: DbSession, boon: Boon) -> boon_gallant.Offer:
    found = boon_gallant.offer(db, boon)
    if found is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No Gallant is offered for that boon, or it's answered."
        )
    return found


@router.post("/troupes/{troupe_id}/boons/{boon_id}/gallant")
def answer_gallant(
    troupe_id: uuid.UUID,
    boon_id: uuid.UUID,
    body: GallantAnswerIn,
    db: DbSession,
    user: CurrentUser,
) -> BoonOut:
    """Staff give the repaid boon's debtor Gallant, or decline to (pp. 402, 405)."""
    troupe = ledger_troupe(db, user, troupe_id)
    boon = troupe_boon(db, troupe, boon_id)
    found = open_offer(db, boon)
    if body.give:
        boon_gallant.give(db, user, troupe, boon, found, body.note)
    else:
        boon_gallant.decline(db, user, boon, found, body.note)
    db.commit()
    return full_out(db, user, troupe, boon)


@router.post("/characters/{character_id}/play-boons/{boon_id}/gallant")
def answer_play_gallant(
    character_id: uuid.UUID,
    boon_id: uuid.UUID,
    body: GallantAnswerIn,
    db: DbSession,
    user: CurrentUser,
) -> PlayBoonsOut:
    """The creditor's player, with Social Nobility, gives the debtor of a boon repaid
    to their character Gallant, or not (p. 405); staff may answer here too."""
    character, troupe = play_ledger(db, user, character_id)
    boon = troupe_boon(db, troupe, boon_id)
    if boon.creditor_id != character.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the player of the boon's creditor answers it here."
        )
    if not in_play(db, troupe, character):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{character.name} isn't in play in {troupe.name}."
        )
    found = open_offer(db, boon)
    staff = boons.can_manage(db, user, troupe)
    if not staff and not boon_gallant.player_answers(troupe, found, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"In {troupe.name}, staff answer this offer of Gallant."
        )
    as_character = None if staff else character
    if body.give:
        boon_gallant.give(db, user, troupe, boon, found, body.note, as_character=as_character)
    else:
        boon_gallant.decline(db, user, boon, found, body.note, as_character=as_character)
    db.commit()
    return play_out(db, user, troupe, character, player_sees(troupe, character))
