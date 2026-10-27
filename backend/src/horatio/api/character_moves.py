"""The custodian moves a character from one player to another (horatio.character_moves):
first a preview of what will happen, then the move itself, with a reason."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import character_moves
from horatio.api.players import Someone
from horatio.api.troupes import existing_user
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, User
from horatio.permissions import Role, require_custodian

router = APIRouter(prefix="/characters/{character_id}/move", tags=["custodian"])


class MoveTroupe(BaseModel):
    id: uuid.UUID
    name: str


class OpenRequest(BaseModel):
    # What it asks, as the troupe's staff see it in their bell.
    summary: str
    troupe: MoveTroupe


class StaffRole(BaseModel):
    troupe: MoveTroupe
    role: Role


class MovePreview(BaseModel):
    character_id: uuid.UUID
    character_name: str
    retired: bool
    from_player: Someone
    to_player: Someone
    home_troupe: MoveTroupe | None
    visiting: list[MoveTroupe]
    # Its requests still waiting, which stay open for the new player.
    open_requests: list[OpenRequest]
    # The new player's roles on the staff of the character's troupes.
    staff_roles: list[StaffRole]
    # Why it can't be moved now, if it can't.
    refusal: str | None


class MoveIn(BaseModel):
    # The new player's handle.
    handle: str
    reason: str


def custodians_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    require_custodian(user)
    character = db.get(Character, character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    return character


def someone(user: User) -> Someone:
    return Someone(id=user.id, handle=user.handle, display_name=user.display_name)


def troupe_out(troupe: Troupe) -> MoveTroupe:
    return MoveTroupe(id=troupe.id, name=troupe.name)


@router.get("")
def preview_move(
    character_id: uuid.UUID, handle: str, db: DbSession, user: CurrentUser
) -> MovePreview:
    """What moving the character to whoever has `handle` would do, for the custodian
    to confirm."""
    character = custodians_character(db, user, character_id)
    found = character_moves.preview(db, character, existing_user(db, handle))
    return MovePreview(
        character_id=character.id,
        character_name=character.name,
        retired=character.status == "retired",
        from_player=someone(found.from_player),
        to_player=someone(found.to_player),
        home_troupe=troupe_out(found.home) if found.home else None,
        visiting=[troupe_out(t) for t in found.visiting],
        open_requests=[
            OpenRequest(summary=summary, troupe=troupe_out(t)) for summary, t in found.open_requests
        ],
        staff_roles=[StaffRole(troupe=troupe_out(t), role=role) for t, role in found.staff_roles],
        refusal=found.refusal,
    )


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
def move_character(character_id: uuid.UUID, body: MoveIn, db: DbSession, user: CurrentUser) -> None:
    """Give the character to whoever has the handle. Only the custodian can, and
    only with a reason."""
    character = custodians_character(db, user, character_id)
    character_moves.move(db, user, character, existing_user(db, body.handle), body.reason)
    db.commit()
