import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import deletion
from horatio.auth.deps import CurrentUser, DbSession
from horatio.creation import grant_starting_traits
from horatio.models import Character, RuleSet
from horatio.permissions import can_edit_character, visible_character
from horatio.sheets import lock_character, rules_for, start_character

router = APIRouter(prefix="/characters", tags=["characters"])


class CharacterOut(BaseModel):
    id: uuid.UUID
    player_id: uuid.UUID
    splat: str
    name: str
    status: str
    home_troupe_id: uuid.UUID | None
    creation_complete: bool
    kind: str  # pc | npc
    # The troupe an NPC belongs to.
    owner_troupe_id: uuid.UUID | None


class NewCharacter(BaseModel):
    splat: str
    name: str = Field(min_length=1, max_length=200)


class CharacterChanges(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def character_out(character: Character) -> CharacterOut:
    return CharacterOut(
        id=character.id,
        player_id=character.player_id,
        splat=character.splat,
        name=character.name,
        status=character.status,
        home_troupe_id=character.home_troupe_id,
        creation_complete=character.creation_completed_at is not None,
        kind=character.kind,
        owner_troupe_id=character.owner_troupe_id,
    )


def editable_character(db: DbSession, user: CurrentUser, character_id: uuid.UUID) -> Character:
    character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can change it.")
    if character.status == "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, "This character is retired.")
    return character


@router.get("")
def my_characters(db: DbSession, user: CurrentUser) -> list[CharacterOut]:
    characters = db.scalars(
        select(Character)
        .where(Character.player_id == user.id, Character.kind == "pc")
        .order_by(Character.name)
    )
    return [character_out(c) for c in characters]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_character(body: NewCharacter, db: DbSession, user: CurrentUser) -> CharacterOut:
    """Players build characters on their own, outside any troupe."""
    if db.scalar(select(RuleSet.id).where(RuleSet.splat == body.splat)) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No rules for {body.splat!r}.")
    character = Character(player_id=user.id, splat=body.splat, name=body.name)
    db.add(character)
    db.flush()
    start_character(db, user, character)
    grant_starting_traits(db, rules_for(db, character), character)
    db.commit()
    db.refresh(character)
    return character_out(character)


@router.get("/{character_id}")
def read_character(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CharacterOut:
    return character_out(visible_character(db, user, character_id))


@router.patch("/{character_id}")
def change_character(
    character_id: uuid.UUID, body: CharacterChanges, db: DbSession, user: CurrentUser
) -> CharacterOut:
    character = editable_character(db, user, character_id)
    character.name = body.name
    db.commit()
    return character_out(character)


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Delete a character for good. It must be in no troupe: leaving each one first
    is what tells those troupes' storytellers."""
    character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player can delete it.")
    deletion.delete_character(db, user, lock_character(db, character.id))
    db.commit()


@router.post("/{character_id}/retire")
def retire_character(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CharacterOut:
    """Characters are never deleted, only retired."""
    character = editable_character(db, user, character_id)
    character.status = "retired"
    db.commit()
    return character_out(character)
