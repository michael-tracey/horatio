"""Staff give a player's character a trait by exception: free, despite the rules, or both."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import sheets, trait_exceptions
from horatio.api.sheets import SheetOut, sheet_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe
from horatio.permissions import TroupeAction, require_troupe_action, visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["sheets"])


class GiveIn(BaseModel):
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    rating: int = Field(ge=1)
    # At no XP cost: its dots are free dots.
    free: bool = False
    # Give it even though it breaks the rules; a trial says which it breaks.
    despite: bool = False
    reason: str = Field(min_length=1, max_length=500)
    # Say what it would cost and break, saving nothing.
    trial: bool = False


class GiveOut(BaseModel):
    # Whether it was given: never on a trial, nor if refused.
    given: bool
    # XP it spends.
    cost: int
    # The rules it breaks, that it is (or would be) given despite.
    breaks: list[str]
    # Why it cannot be given (on a trial); refusals otherwise come as 409.
    refused: str | None
    sheet: SheetOut


@router.post("/give")
def give(character_id: uuid.UUID, body: GiveIn, db: DbSession, user: CurrentUser) -> GiveOut:
    """A storyteller or assistant storyteller of a player's character's home troupe
    gives it a trait, or raises one: free, despite the rules, or both, always with
    a reason. Nothing waits on approval; the player is told."""
    character = visible_character(db, user, character_id)
    if character.kind != "pc" or character.home_troupe_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Staff give traits only to a player's character in its home troupe.",
        )
    require_troupe_action(
        db, user, db.get_one(Troupe, character.home_troupe_id), TroupeAction.APPROVE_CHANGES
    )
    character = sheets.lock_character(db, character.id)
    given = trait_exceptions.give(
        db,
        user,
        character,
        (body.category, body.name, body.detail),
        body.rating,
        free=body.free,
        despite=body.despite,
        reason=body.reason.strip(),
        trial=body.trial,
    )
    if not body.trial:
        db.commit()
    return GiveOut(
        given=not body.trial,
        cost=given.cost,
        breaks=given.breaks,
        refused=given.refused,
        sheet=sheet_out(db, character),
    )
