"""A character's Retainers: the list under the background, with who may edit and link."""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from horatio import retainers, sheets
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, User
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["retainers"])


class RetainerOut(BaseModel):
    # None for a Retainer bought on the sheet with nothing kept for it yet.
    id: uuid.UUID | None
    # The name, and the dots: for one bought on the sheet, its detail ("" for one
    # held without a name) and rating there.
    name: str
    dots: int
    bought: bool
    description: str
    # The merit that gave it; empty for the background's own.
    from_merit: str
    lost: str | None  # released | killed
    lost_on: date | None
    # The NPC it is linked to, for those who can see that NPC.
    npc_id: uuid.UUID | None
    npc_name: str | None


class RetainersOut(BaseModel):
    # The Retainers background's dots, across every Retainer bought.
    rating: int
    retainers: list[RetainerOut]
    can_edit: bool
    can_link: bool


class RetainerIn(BaseModel):
    # Present for a Retainer already listed.
    id: uuid.UUID | None = None
    # One bought on the sheet is named as it was bought there, and its dots are the sheet's.
    name: str = Field(min_length=1, max_length=200)
    dots: int
    description: str = Field(default="", max_length=500)
    from_merit: str = Field(default="", max_length=100)
    lost: str | None = Field(default=None, pattern="^(released|killed)$")
    lost_on: date | None = None
    npc_id: uuid.UUID | None = None


class RetainersIn(BaseModel):
    retainers: list[RetainerIn] = Field(max_length=retainers.MAX_LISTED)


def listed(db: Session, entries: list[retainers.Listed], viewer: User | None) -> list[RetainerOut]:
    out: list[RetainerOut] = []
    for e in entries:
        r = e.row
        npc = retainers.viewable_npc(db, viewer, r) if r else None
        out.append(
            RetainerOut(
                id=r.id if r else None,
                name=e.name,
                dots=e.dots,
                bought=e.bought,
                description=r.description if r else "",
                from_merit=r.from_merit if r else "",
                lost=r.lost if r else None,
                lost_on=r.lost_on if r else None,
                npc_id=npc.id if npc else None,
                npc_name=npc.name if npc else None,
            )
        )
    return out


def retainers_out(db: Session, character: Character, user: User) -> RetainersOut:
    return RetainersOut(
        rating=retainers.rating(db, character),
        retainers=listed(db, retainers.read(db, character), user),
        can_edit=retainers.can_edit(db, user, character),
        can_link=retainers.can_link(db, user, character),
    )


@router.get("/retainers")
def read_retainers(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> RetainersOut:
    return retainers_out(db, visible_character(db, user, character_id), user)


@router.put("/retainers")
def save_retainers(
    character_id: uuid.UUID, body: RetainersIn, db: DbSession, user: CurrentUser
) -> RetainersOut:
    """Replace the list. The player edits descriptions and losses, and the names
    and dots of those not bought on the sheet; staff do the same and alone link
    an NPC."""
    character = visible_character(db, user, character_id)
    if not retainers.can_edit(db, user, character):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the character's player or its staff can change this."
        )
    character = sheets.lock_character(db, character.id)
    retainers.replace(
        db,
        user,
        character,
        [retainers.Draft(**r.model_dump()) for r in body.retainers],
        link=retainers.can_link(db, user, character),
    )
    db.commit()
    return retainers_out(db, character, user)
