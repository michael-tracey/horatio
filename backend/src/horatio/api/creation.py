"""Character creation: the picks a new character places, and finishing creation."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import creation
from horatio.api.sheets import players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}/creation", tags=["creation"])


class PickedTrait(BaseModel):
    name: str
    detail: str
    # The pick's rating, or the points it used.
    pick: int


class PoolOut(BaseModel):
    category: str
    category_name: str
    # The picks' rating; 0 for a budget of points.
    rating: int
    kind: str  # picks | points
    allowed: int
    used: int
    remaining: int
    # A fact each trait must have to take a pick here, such as "in_clan".
    restriction: str | None
    traits: list[PickedTrait]


class CreationOut(BaseModel):
    complete: bool
    pools: list[PoolOut]


class Pick(BaseModel):
    category: str
    name: str
    detail: str = Field(default="", max_length=200)
    # The pick to use; ignored for merits and flaws, which use their point value.
    rating: int = Field(default=1, ge=1)


class CategoryPick(BaseModel):
    name: str
    detail: str = Field(default="", max_length=200)
    # Ignored for merits and flaws, which use their point value.
    rating: int = Field(default=1, ge=1)


class CategoryPicks(BaseModel):
    picks: list[CategoryPick]


class Unpick(BaseModel):
    category: str
    name: str
    detail: str = ""


def creation_out(db: DbSession, character: Character) -> CreationOut:
    pools = creation.pools(db, character)
    catalogue = creation.rules_for(db, character).rule_set.categories
    return CreationOut(
        complete=character.creation_completed_at is not None,
        pools=[
            PoolOut(
                category=p.category,
                category_name=catalogue[p.category].name,
                rating=p.rating,
                kind=p.kind,
                allowed=p.allowed,
                used=p.used,
                remaining=p.remaining,
                restriction=p.restriction,
                traits=[
                    PickedTrait(
                        name=r.definition.name,
                        detail=r.trait.detail,
                        pick=r.trait.creation_pick or 0,
                    )
                    for r in p.traits
                ],
            )
            for p in sorted(pools.values(), key=lambda p: (p.category, -p.rating))
        ],
    )


@router.get("")
def read_creation(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CreationOut:
    return creation_out(db, visible_character(db, user, character_id))


@router.put("/picks")
def place_pick(
    character_id: uuid.UUID, body: Pick, db: DbSession, user: CurrentUser
) -> CreationOut:
    character = players_character(db, user, character_id)
    creation.place_pick(db, user, character, body.category, body.name, body.detail, body.rating)
    db.commit()
    return creation_out(db, character)


@router.put("/categories/{category}")
def set_category_picks(
    character_id: uuid.UUID, category: str, body: CategoryPicks, db: DbSession, user: CurrentUser
) -> CreationOut:
    """Replace every creation pick in one category at once: one step of the wizard."""
    character = players_character(db, user, character_id)
    creation.set_category_picks(
        db,
        user,
        character,
        category,
        [creation.PickSpec(name=p.name, rating=p.rating, detail=p.detail) for p in body.picks],
    )
    db.commit()
    return creation_out(db, character)


@router.post("/picks/remove")
def remove_pick(
    character_id: uuid.UUID, body: Unpick, db: DbSession, user: CurrentUser
) -> CreationOut:
    character = players_character(db, user, character_id)
    creation.remove_pick(db, user, character, body.category, body.name, body.detail)
    db.commit()
    return creation_out(db, character)


@router.post("/complete")
def complete(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CreationOut:
    character = players_character(db, user, character_id)
    creation.complete(db, user, character)
    db.commit()
    return creation_out(db, character)
