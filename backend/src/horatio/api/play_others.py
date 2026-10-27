"""Others at the game, on the Play View's Status tab (horatio.play_others): another
character's status, as one of its sect knows it, and learning its details with
Leadership. Each route is the viewer's character's, which must be Accepted; what it
sees of the other is only what its sect and its Leadership allow."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from horatio import play_others, sheets
from horatio.api.sect_status import EndingOut, ending_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import User
from horatio.permissions import visible_character

router = APIRouter(tags=["play"])


class OtherOut(BaseModel):
    """Another character at the game. Of another sect, only its name and sect."""

    character_id: uuid.UUID
    name: str
    kind: str
    sect: str | None
    same_sect: bool
    # Of the viewer's sect: the sect's name for Accepted, and its titles in the troupe.
    accepted: str | None
    titles: list[str]


class SeenOut(BaseModel):
    """One status the other carries into its game. Its details (patron, where, the
    story) are there only when `known`: a negative status, or a fleeting one the
    viewer has learned about with Leadership."""

    key: str
    name: str
    type: str
    # Spent at the other's game.
    spent: bool
    # Fleeting status, whose details Leadership learns.
    learnable: bool
    known: bool
    # The viewer's tap that learned it, which Undo takes back.
    learned_by: uuid.UUID | None
    held_id: uuid.UUID | None
    patron: str | None
    place: str | None
    story: str | None
    ending: EndingOut | None
    # A negative status the viewer's player gave: they may remove it early.
    removable: bool


class OtherStatusOut(BaseModel):
    other: OtherOut
    # None for another sect's character, whose status the viewer does not know.
    status: list[SeenOut] | None


class LearnIn(BaseModel):
    # The device's id for the tap spending the Leadership use.
    id: uuid.UUID
    # The status, as `SeenOut.key` names it.
    key: str = Field(min_length=1, max_length=200)


def other_out(other: play_others.Other) -> OtherOut:
    return OtherOut(
        character_id=other.character.id,
        name=other.character.name,
        kind=other.character.kind,
        sect=other.sect,
        same_sect=other.same_sect,
        accepted=other.accepted,
        titles=list(other.titles),
    )


def seen_out(s: play_others.Seen) -> SeenOut:
    return SeenOut(
        key=s.key,
        name=s.name,
        type=s.type,
        spent=s.spent,
        learnable=s.learnable,
        known=s.known,
        learned_by=s.learned_by,
        held_id=s.held_id,
        patron=s.patron.words if s.known and s.patron else None,
        place=s.place if s.known else None,
        story=s.story if s.known else None,
        ending=ending_out(s.ending) if s.known and s.ending else None,
        removable=s.removable,
    )


def status_out(
    db: Session, user: User, viewer: play_others.Viewer, other: play_others.Other
) -> OtherStatusOut:
    return OtherStatusOut(
        other=other_out(other),
        status=[seen_out(s) for s in play_others.seen(db, user, viewer, other)]
        if other.same_sect
        else None,
    )


def viewer_of(db: Session, user: User, character_id: uuid.UUID) -> play_others.Viewer:
    return play_others.viewing(db, visible_character(db, user, character_id))


@router.get("/characters/{character_id}/play/others")
def list_others(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[OtherOut]:
    """The others at the character's game: its troupe's PCs and titled NPCs."""
    viewer = viewer_of(db, user, character_id)
    return [other_out(o) for o in play_others.others(db, viewer)]


@router.get("/characters/{character_id}/play/others/{other_id}")
def read_other(
    character_id: uuid.UUID, other_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> OtherStatusOut:
    """Another character's status, as the character knows it."""
    viewer = viewer_of(db, user, character_id)
    return status_out(db, user, viewer, play_others.other(db, viewer, other_id))


@router.post("/characters/{character_id}/play/others/{other_id}/learn")
def learn_status(
    character_id: uuid.UUID, other_id: uuid.UUID, body: LearnIn, db: DbSession, user: CurrentUser
) -> OtherStatusOut:
    """Spend a Leadership use for the game to learn a fleeting status's patron, where
    it was earned and the story (MET: VTM p. 310)."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    viewer = play_others.viewing(db, character)
    other = play_others.other(db, viewer, other_id)
    play_others.learn(db, user, viewer, other, body.key, body.id)
    db.commit()
    return status_out(db, user, viewer, other)


@router.post("/characters/{character_id}/play/others/{other_id}/status/{held_id}/remove")
def remove_given_status(
    character_id: uuid.UUID,
    other_id: uuid.UUID,
    held_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> OtherStatusOut:
    """Remove early a negative status the person's own character gave (p. 313)."""
    viewer = viewer_of(db, user, character_id)
    other = play_others.other(db, viewer, other_id)
    target = sheets.lock_character(db, other.character.id)
    play_others.remove(db, user, viewer, other, held_id)
    db.commit()
    db.refresh(target)
    return status_out(db, user, viewer, other)
