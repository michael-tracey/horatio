"""Giving a sheeted NPC to a player (horatio.npc_gifts): staff give it to someone
directly, or make a claim link for whoever opens it to claim it."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from horatio import npc_gifts, pictures
from horatio.api.character_moves import someone
from horatio.api.characters import CharacterOut, character_out
from horatio.api.players import Someone
from horatio.api.troupes import existing_user
from horatio.auth.deps import CurrentUser, DbSession, MaybeUser
from horatio.models import Character, NpcClaim, Troupe, User
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
    # Who it would go to; None when no one is named yet (a claim link).
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


class ClaimLinkOut(BaseModel):
    expires_at: datetime
    made_by: Someone
    carried_xp: int
    carried_reason: str


class MadeClaimLink(BaseModel):
    # The link itself: shown once, as only its hash is kept.
    url: str
    expires_at: datetime


class ClaimOut(BaseModel):
    """What a claim link is for, for whoever opens it, signed in or not."""

    character_name: str
    troupe_name: str
    clan: str | None
    # Its portrait, through the link (add "/96.webp" and so on), or None.
    picture: str | None
    expires_at: datetime
    carried_xp: int
    # Whether the person looking is signed in, and so can claim it now.
    signed_in: bool


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
    without a handle, what giving it to anyone would (for a claim link)."""
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


def link_out(db: DbSession, row: NpcClaim) -> ClaimLinkOut:
    return ClaimLinkOut(
        expires_at=row.expires_at,
        made_by=someone(db.get_one(User, row.created_by_id)),
        carried_xp=row.carried_xp,
        carried_reason=row.carried_reason,
    )


@router.get("/characters/{character_id}/claim-link")
def read_claim_link(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> ClaimLinkOut | None:
    """The NPC's open claim link, if it has one: when it expires, and who made it."""
    row = npc_gifts.live_claim(db, givers_npc(db, user, character_id))
    return link_out(db, row) if row is not None else None


@router.post("/characters/{character_id}/claim-link", status_code=status.HTTP_201_CREATED)
def make_claim_link(
    character_id: uuid.UUID, body: CarriedXp, db: DbSession, user: CurrentUser
) -> MadeClaimLink:
    """A new claim link for the NPC, for 30 days, replacing any it had. The link is
    shown only now."""
    npc = givers_npc(db, user, character_id)
    token, expires_at = npc_gifts.make_claim(db, user, npc, body.carried_xp, body.carried_reason)
    db.commit()
    return MadeClaimLink(url=npc_gifts.claim_url(token), expires_at=expires_at)


@router.delete("/characters/{character_id}/claim-link", status_code=status.HTTP_204_NO_CONTENT)
def cancel_claim_link(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    npc_gifts.cancel_claim(db, user, givers_npc(db, user, character_id))
    db.commit()


def live_claim(db: DbSession, token: str) -> tuple[NpcClaim, Character]:
    row = npc_gifts.claim_for(db, token)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "This claim link has expired or been used. Ask the troupe for a new one.",
        )
    return row, db.get_one(Character, row.character_id)


@router.get("/claims/{token}")
def read_claim(token: str, db: DbSession, user: MaybeUser) -> ClaimOut:
    """The character a claim link is for: its name, troupe and portrait. Anyone with
    the link may see them, so they can sign up to claim it."""
    row, npc = live_claim(db, token)
    troupe = db.get_one(Troupe, npc.owner_troupe_id)
    return ClaimOut(
        character_name=npc.name,
        troupe_name=troupe.name,
        clan=character_out(db, npc).clan,
        picture=f"/api/claims/{token}/pictures/{npc.picture_id}" if npc.picture_id else None,
        expires_at=row.expires_at,
        carried_xp=row.carried_xp,
        signed_in=user is not None,
    )


@router.get("/claims/{token}/pictures/{picture_id}/{name}", response_class=FileResponse)
def claim_picture(token: str, picture_id: uuid.UUID, name: str, db: DbSession) -> FileResponse:
    """One of the portrait's files, through the claim link."""
    _, npc = live_claim(db, token)
    root = pictures.upload_dir()
    path = (
        pictures.picture_file(root, npc.id, picture_id, name)
        if root is not None and npc.picture_id == picture_id
        else None
    )
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    return FileResponse(
        path,
        media_type="image/jpeg" if name.endswith(".jpg") else "image/webp",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/claims/{token}")
def claim(token: str, db: DbSession, user: CurrentUser) -> CharacterOut:
    """Claim the character: it becomes yours, at home and accepted in its troupe."""
    npc = npc_gifts.claim(db, user, token)
    db.commit()
    return character_out(db, npc)
