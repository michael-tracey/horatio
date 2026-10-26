"""A character's Retainers: the list under the background, with who may edit and link."""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from horatio import retainers, sheets
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Retainer, User
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["retainers"])


class RetainerOut(BaseModel):
    id: uuid.UUID
    name: str
    dots: int
    description: str
    # The merit that gave it; empty for the background's own.
    from_merit: str
    lost: str | None  # released | killed
    lost_on: date | None
    # The NPC it is linked to, for those who can see that NPC.
    npc_id: uuid.UUID | None
    npc_name: str | None


class RetainersOut(BaseModel):
    # The Retainers background's rating, and the dots the listed Retainers add up to.
    rating: int
    total: int
    retainers: list[RetainerOut]
    can_edit: bool
    can_link: bool


class RetainerIn(BaseModel):
    # Present for a Retainer already listed.
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    dots: int
    description: str = Field(default="", max_length=500)
    from_merit: str = Field(default="", max_length=100)
    lost: str | None = Field(default=None, pattern="^(released|killed)$")
    lost_on: date | None = None
    npc_id: uuid.UUID | None = None


class RetainersIn(BaseModel):
    retainers: list[RetainerIn] = Field(max_length=retainers.MAX_LISTED)


def listed(db: Session, rows: list[Retainer], viewer: User | None) -> list[RetainerOut]:
    out: list[RetainerOut] = []
    for r in rows:
        npc = retainers.viewable_npc(db, viewer, r)
        out.append(
            RetainerOut(
                id=r.id,
                name=r.name,
                dots=r.dots,
                description=r.description,
                from_merit=r.from_merit,
                lost=r.lost,
                lost_on=r.lost_on,
                npc_id=npc.id if npc else None,
                npc_name=npc.name if npc else None,
            )
        )
    return out


def retainers_out(db: Session, character: Character, user: User) -> RetainersOut:
    rows = retainers.read(db, character)
    return RetainersOut(
        rating=retainers.rating(db, character),
        total=retainers.counted(rows),
        retainers=listed(db, rows, user),
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
    """Replace the list. The player edits names, descriptions, dots and losses;
    staff do the same and alone link an NPC."""
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
