"""Shared backgrounds and their logs (horatio.shared_backgrounds): set up and kept
by a troupe's storytellers and assistant storytellers, seen by the players of the
characters sharing them, who log uses for their own characters."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import or_, select

from horatio import shared_backgrounds
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Character,
    SharedBackground,
    SharedBackgroundEntry,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.permissions import TroupeAction, visible_character

router = APIRouter(tags=["shared backgrounds"])

Kind = Literal["contribution", "withdrawal", "use"]


class SharerOut(BaseModel):
    # None for a character since deleted.
    character_id: uuid.UUID | None
    name: str
    # Put in, less taken out; 0 once they have taken it all out.
    dots: int
    # The reader can log a use for this character: staff for any sharer, a player
    # for their own.
    can_log_use: bool


class SharedEntryOut(BaseModel):
    id: uuid.UUID
    kind: Kind
    happened_at: datetime
    character_id: uuid.UUID | None
    # The character's name as it was logged.
    name: str
    # Put in or taken out; None for a use.
    dots: int | None
    # What a use was for.
    purpose: str
    note: str
    logged_by_name: str | None
    logged_at: datetime
    # The reader can take it off the log.
    can_delete: bool


class SharedBackgroundOut(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    troupe_name: str
    name: str
    # The background's name, such as "Haven".
    background: str
    # What the sharers chose it gives them.
    notes: str
    # The group's rating: what is put in, but never more than `most`.
    total: int
    put_in: int
    most: int
    # Every character that has put dots in, in the order they first did.
    sharers: list[SharerOut]
    # Newest first.
    entries: list[SharedEntryOut]
    # The reader is the troupe's staff: they change it and log anything.
    can_manage: bool
    created_at: datetime


class ContributionIn(BaseModel):
    character_id: uuid.UUID
    dots: int = Field(ge=1, le=10)


class SharedBackgroundIn(BaseModel):
    name: str = Field(max_length=200)
    background: str
    notes: str = Field(default="", max_length=2000)
    # The characters sharing it and the dots each puts in, logged as at now.
    contributions: list[ContributionIn] = Field(min_length=1, max_length=50)


class SharedBackgroundChange(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    background: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SharedEntryIn(BaseModel):
    kind: Kind
    character_id: uuid.UUID
    # Now, if left out.
    happened_at: AwareDatetime | None = None
    # For dots put in or taken out.
    dots: int | None = Field(default=None, ge=1, le=10)
    purpose: str = Field(default="", max_length=1000)
    note: str = Field(default="", max_length=2000)


class SharedCharacterChoice(BaseModel):
    id: uuid.UUID
    name: str
    kind: str  # pc | npc


class SharedChoicesOut(BaseModel):
    # The backgrounds a group can share (Vol. 2 Issue 1, p. 88).
    backgrounds: list[str]
    page: str
    most: int
    # The troupe's characters now, PCs and NPCs.
    characters: list[SharedCharacterChoice]


# --- helpers ----------------------------------------------------------------------------


def shared_out(db: DbSession, user: User, shared: SharedBackground) -> SharedBackgroundOut:
    troupe = db.get_one(Troupe, shared.troupe_id)
    manage = shared_backgrounds.can_manage(db, user, troupe)
    found = shared_backgrounds.entries(db, shared)
    standing = shared_backgrounds.standing(found)
    character_ids = {s.character_id for s in standing.sharers} - {None}
    characters = {
        c.id: c for c in db.scalars(select(Character).where(Character.id.in_(character_ids)))
    }
    user_ids = {e.logged_by for e in found} - {None}
    users = {
        i: n for i, n in db.execute(select(User.id, User.display_name).where(User.id.in_(user_ids)))
    }
    open_troupe = troupe.archived_at is None

    def name_of(character_id: uuid.UUID | None, logged: str) -> str:
        character = characters.get(character_id) if character_id else None
        return character.name if character else logged

    def can_log_use(character_id: uuid.UUID | None, dots: int) -> bool:
        if character_id is None or dots < 1:
            return False
        return manage or (
            open_troupe and shared_backgrounds.plays(user, characters.get(character_id))
        )

    def can_delete(entry: SharedBackgroundEntry) -> bool:
        return manage or (open_troupe and entry.kind == "use" and entry.logged_by == user.id)

    return SharedBackgroundOut(
        id=shared.id,
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        name=shared.name,
        background=shared.background,
        notes=shared.notes,
        total=standing.total,
        put_in=standing.put_in,
        most=shared_backgrounds.MOST,
        sharers=[
            SharerOut(
                character_id=s.character_id,
                name=name_of(s.character_id, s.name),
                dots=s.dots,
                can_log_use=can_log_use(s.character_id, s.dots),
            )
            for s in standing.sharers
        ],
        entries=[
            SharedEntryOut(
                id=e.id,
                kind=e.kind,  # type: ignore[arg-type]  # checked by the database
                happened_at=e.happened_at,
                character_id=e.character_id,
                name=e.name,
                dots=e.dots,
                purpose=e.purpose,
                note=e.note,
                logged_by_name=users.get(e.logged_by) if e.logged_by else None,
                logged_at=e.created_at,
                can_delete=can_delete(e),
            )
            for e in found
        ],
        can_manage=manage,
        created_at=shared.created_at,
    )


def visible_shared(db: DbSession, user: User, shared_id: uuid.UUID) -> SharedBackground:
    """The shared background, or 404 if there is none or `user` may not see it."""
    shared = db.get(SharedBackground, shared_id)
    if shared is None or not shared_backgrounds.can_see(db, user, shared):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shared background.")
    return shared


def managed_shared(db: DbSession, user: User, shared_id: uuid.UUID) -> SharedBackground:
    shared = visible_shared(db, user, shared_id)
    staff_troupe(db, user, shared.troupe_id, TroupeAction.MANAGE_SHARED_BACKGROUNDS)
    return shared


def outs(db: DbSession, user: User, found: Sequence[SharedBackground]) -> list[SharedBackgroundOut]:
    return [shared_out(db, user, s) for s in found]


# --- the troupe's -----------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/shared-backgrounds")
def troupe_shared(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[SharedBackgroundOut]:
    """Every shared background in the troupe, by name, for its staff."""
    staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_SHARED_BACKGROUNDS)
    return outs(db, user, shared_backgrounds.of_troupe(db, troupe_id))


@router.get("/troupes/{troupe_id}/shared-backgrounds/choices")
def choices(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> SharedChoicesOut:
    """What a shared background can be, and the characters who can share it."""
    staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_SHARED_BACKGROUNDS)
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None)
    )
    characters = db.scalars(
        select(Character)
        .where(
            or_(Character.id.in_(members), Character.owner_troupe_id == troupe_id),
            Character.status != "retired",
        )
        .order_by(Character.name)
    )
    return SharedChoicesOut(
        backgrounds=shared_backgrounds.backgrounds(db, troupe_id),
        page=shared_backgrounds.RULE_PAGE,
        most=shared_backgrounds.MOST,
        characters=[SharedCharacterChoice(id=c.id, name=c.name, kind=c.kind) for c in characters],
    )


@router.post("/troupes/{troupe_id}/shared-backgrounds", status_code=status.HTTP_201_CREATED)
def create(
    troupe_id: uuid.UUID, body: SharedBackgroundIn, db: DbSession, user: CurrentUser
) -> SharedBackgroundOut:
    """Set up a shared background, with the characters sharing it and their dots."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_SHARED_BACKGROUNDS)
    shared = shared_backgrounds.create(
        db,
        user,
        troupe,
        name=body.name,
        background=body.background,
        notes=body.notes,
        contributions=[
            shared_backgrounds.Contribution(c.character_id, c.dots) for c in body.contributions
        ],
        happened_at=datetime.now(UTC),
    )
    db.commit()
    return shared_out(db, user, shared)


# --- one --------------------------------------------------------------------------------


@router.get("/shared-backgrounds/{shared_id}")
def read(shared_id: uuid.UUID, db: DbSession, user: CurrentUser) -> SharedBackgroundOut:
    return shared_out(db, user, visible_shared(db, user, shared_id))


@router.patch("/shared-backgrounds/{shared_id}")
def change(
    shared_id: uuid.UUID, body: SharedBackgroundChange, db: DbSession, user: CurrentUser
) -> SharedBackgroundOut:
    shared = managed_shared(db, user, shared_id)
    shared_backgrounds.change(
        db, user, shared, name=body.name, background=body.background, notes=body.notes
    )
    db.commit()
    return shared_out(db, user, shared)


@router.delete("/shared-backgrounds/{shared_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(shared_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Delete it and its whole log."""
    shared_backgrounds.remove(db, user, managed_shared(db, user, shared_id))
    db.commit()


@router.post("/shared-backgrounds/{shared_id}/entries", status_code=status.HTTP_201_CREATED)
def log_entry(
    shared_id: uuid.UUID, body: SharedEntryIn, db: DbSession, user: CurrentUser
) -> SharedBackgroundOut:
    """Log dots put in or taken out (staff), or a use (staff, or the character's
    player)."""
    shared = visible_shared(db, user, shared_id)
    details = shared_backgrounds.Details(
        kind=body.kind,
        character_id=body.character_id,
        happened_at=body.happened_at or datetime.now(UTC),
        dots=body.dots,
        purpose=body.purpose,
        note=body.note,
    )
    if not shared_backgrounds.may_log(db, user, shared, details):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the troupe's storytellers log dots; players log uses for their own characters.",
        )
    shared_backgrounds.log(db, user, shared, details)
    db.commit()
    return shared_out(db, user, shared)


@router.delete("/shared-background-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlog_entry(entry_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    entry = db.get(SharedBackgroundEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry.")
    visible_shared(db, user, entry.background_id)
    if not shared_backgrounds.may_unlog(db, user, entry):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the troupe's storytellers, or whoever logged a use, take it off.",
        )
    shared_backgrounds.unlog(db, user, entry)
    db.commit()


# --- a character's ----------------------------------------------------------------------


@router.get("/characters/{character_id}/shared-backgrounds")
def character_shared(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[SharedBackgroundOut]:
    """The shared backgrounds the character has put dots in, that the reader sees."""
    character = visible_character(db, user, character_id)
    found = shared_backgrounds.of_character(db, character.id)
    return outs(db, user, [s for s in found if shared_backgrounds.can_see(db, user, s)])
