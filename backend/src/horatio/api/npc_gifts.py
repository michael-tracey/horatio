"""Giving a sheeted NPC to a player (horatio.npc_gifts): staff give it to someone
who has signed up."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import npc_gifts
from horatio.api.character_moves import someone
from horatio.api.players import Someone
from horatio.api.troupes import existing_user
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe, User
from horatio.permissions import TroupeAction, can_view_character, require_troupe_action

router = APIRouter(tags=["npcs"])


class LinkedRetainer(BaseModel):
    # The character whose Retainer it is, and the Retainer's name.
    character_name: str
    name: str


class GivePreview(BaseModel):
    character_id: uuid.UUID
    character_name: str
    troupe_name: str
    # Who it would go to; None when no one is named yet.
    to_player: Someone | None
    # What its sheet costs at the troupe's prices: the "Imported" award, and its purchases.
    xp: int
    # Traits the troupe's costs don't price, kept as free dots.
    free: list[str]
    # Retainers linked to it, which are unlinked.
    retainers: list[LinkedRetainer]
    # Why it can't be given now, if it can't.
    refusal: str | None


class CarriedXp(BaseModel):
    # Unspent XP the player had banked elsewhere, written as its own award.
    carried_xp: int = Field(default=0, ge=0, le=npc_gifts.CARRIED_MAX)
    carried_reason: str = Field(default="", max_length=500)


class GiveIn(CarriedXp):
    # The new player's handle.
    handle: str


def givers_npc(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    """The NPC, if `user` may give it: the custodian, and its troupe's lead storyteller
    and storytellers."""
    npc = db.get(Character, character_id)
    if npc is None or not can_view_character(db, user, npc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    if npc.kind != "npc" or npc.owner_troupe_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{npc.name} is already a player's character."
        )
    require_troupe_action(db, user, db.get_one(Troupe, npc.owner_troupe_id), TroupeAction.GIVE_NPCS)
    return npc


def preview_out(found: npc_gifts.Preview) -> GivePreview:
    return GivePreview(
        character_id=found.npc.id,
        character_name=found.npc.name,
        troupe_name=found.troupe.name,
        to_player=someone(found.to_player) if found.to_player else None,
        xp=found.xp,
        free=found.free,
        retainers=[LinkedRetainer(character_name=c, name=n) for c, n in found.retainers],
        refusal=found.refusal,
    )


@router.get("/characters/{character_id}/give-to-player")
def preview_give(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser, handle: str | None = None
) -> GivePreview:
    """What giving the NPC to whoever has `handle` would do, for staff to confirm;
    without a handle, what giving it to anyone would."""
    npc = givers_npc(db, user, character_id)
    to_player = existing_user(db, handle) if handle else None
    return preview_out(npc_gifts.preview(db, npc, to_player))


@router.post("/characters/{character_id}/give-to-player", status_code=status.HTTP_204_NO_CONTENT)
def give_npc(character_id: uuid.UUID, body: GiveIn, db: DbSession, user: CurrentUser) -> None:
    """Give the sheeted NPC to whoever has the handle: it becomes their character, at
    home and accepted in the troupe, its XP balanced, plus any carried over."""
    npc = givers_npc(db, user, character_id)
    npc_gifts.give(
        db, user, npc, existing_user(db, body.handle), body.carried_xp, body.carried_reason
    )
    db.commit()
