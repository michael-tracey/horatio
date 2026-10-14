"""NPCs: a troupe's own characters, built quickly by its storytellers and assistants."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import npcs, sheets
from horatio.api.characters import CharacterOut, character_out
from horatio.api.downtimes import staff_troupe
from horatio.api.sheets import players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, RuleSet
from horatio.permissions import TroupeAction

router = APIRouter(tags=["npcs"])


class NewNpc(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    splat: str = "vampire"
    # Build through the creation wizard rather than setting ratings directly.
    wizard: bool = False


class Rating(BaseModel):
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    # Null for an unrated choice such as a clan; 0 removes a rated trait.
    rating: int | None = Field(default=None, ge=0)


class TallyLineOut(BaseModel):
    category: str
    name: str
    detail: str
    rating: int
    cost: int | None
    note: str


class Tally(BaseModel):
    total: int
    lines: list[TallyLineOut]


@router.get("/troupes/{troupe_id}/npcs")
def list_npcs(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[CharacterOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_NPCS)
    found = db.scalars(
        select(Character)
        .where(Character.kind == "npc", Character.owner_troupe_id == troupe_id)
        .order_by(Character.name)
    )
    return [character_out(c) for c in found]


@router.post("/troupes/{troupe_id}/npcs", status_code=status.HTTP_201_CREATED)
def create_npc(
    troupe_id: uuid.UUID, body: NewNpc, db: DbSession, user: CurrentUser
) -> CharacterOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_NPCS)
    if db.scalar(select(RuleSet.id).where(RuleSet.splat == body.splat)) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No rules for {body.splat!r}.")
    npc = npcs.create_npc(db, user, troupe, body.splat, body.name, body.wizard)
    db.commit()
    return character_out(npc)


@router.put("/characters/{character_id}/npc/ratings")
def set_rating(character_id: uuid.UUID, body: Rating, db: DbSession, user: CurrentUser) -> Tally:
    """Set one of an NPC's traits straight to a rating, and get the new tally."""
    npc = players_character(db, user, character_id)
    with sheets.checked(db, npc, user):
        npcs.set_rating(db, user, npc, body.category, body.name, body.detail, body.rating)
    db.commit()
    return tally(character_id, db, user)


@router.get("/characters/{character_id}/npc/tally")
def tally(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Tally:
    """What the NPC's sheet would be worth in experience under its troupe's rules."""
    npc = players_character(db, user, character_id)
    if npc.kind != "npc":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only NPCs have a tally.")
    total, lines = npcs.tally(db, npc)
    return Tally(
        total=total,
        lines=[
            TallyLineOut(
                category=line.category,
                name=line.name,
                detail=line.detail,
                rating=line.rating,
                cost=line.cost,
                note=line.note,
            )
            for line in lines
        ],
    )
