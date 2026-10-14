"""A troupe's titles, and who holds them."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import titles
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character
from horatio.permissions import TroupeAction

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["titles"])


class TitlesOut(BaseModel):
    # From the rule sets, available to every troupe.
    catalogue: list[str]
    # Added by this troupe.
    troupe: list[str]


class NewTitle(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class HeldTitles(BaseModel):
    titles: list[str]


def titles_out(db: DbSession, troupe_id: uuid.UUID) -> TitlesOut:
    return TitlesOut(
        catalogue=titles.catalogue_titles(db), troupe=titles.troupe_titles(db, troupe_id)
    )


@router.get("/titles")
def list_titles(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TitlesOut:
    staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    return titles_out(db, troupe_id)


@router.post("/titles", status_code=status.HTTP_201_CREATED)
def add_title(troupe_id: uuid.UUID, body: NewTitle, db: DbSession, user: CurrentUser) -> TitlesOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    titles.add_title(db, user, troupe, body.name)
    db.commit()
    return titles_out(db, troupe_id)


@router.delete("/titles/{name}")
def remove_title(troupe_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser) -> TitlesOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    titles.remove_title(db, user, troupe, name)
    db.commit()
    return titles_out(db, troupe_id)


@router.put("/characters/{character_id}/titles")
def set_titles(
    troupe_id: uuid.UUID,
    character_id: uuid.UUID,
    body: HeldTitles,
    db: DbSession,
    user: CurrentUser,
) -> HeldTitles:
    """Give a character in this troupe exactly these titles."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    character = db.get(Character, character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    held = titles.set_titles(db, user, troupe, character, body.titles)
    db.commit()
    return HeldTitles(titles=held)
