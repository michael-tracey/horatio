"""Being built: the characters built to a troupe's rules that haven't asked to join it
yet (horatio.builds, #774), for its storytellers and assistant storytellers."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from horatio import builds, creation, pictures, sheets, social_age, titles
from horatio.api.downtimes import staff_troupe
from horatio.api.printing import PrintedSheet, print_sheet
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, CharacterTrait, Troupe, User
from horatio.permissions import TroupeAction

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["builds"])


class BuildEntry(BaseModel):
    character_id: uuid.UUID
    character_name: str
    # The player, by name and handle: never their email.
    player_id: uuid.UUID
    player_name: str
    player_handle: str
    splat: str
    # Once chosen on the sheet.
    clan: str | None
    sect: str | None
    picture: str | None
    creation_complete: bool
    # In creation, the categories with picks still to place, in the rules' order.
    to_place: list[str]
    # The checks Finish creation refuses on, as the sheet stands: each message once.
    broken: list[str]
    started_at: datetime
    # The latest change to the character or any of its traits.
    changed_at: datetime


class BuildCount(BaseModel):
    count: int


def _troupe(db: DbSession, user: CurrentUser, troupe_id: uuid.UUID) -> Troupe:
    return staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)


@router.get("/builds")
def being_built(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[BuildEntry]:
    """Characters built to the troupe's rules, with no request yet to make it home:
    the most recently changed first."""
    troupe = _troupe(db, user, troupe_id)
    if troupe.archived_at is not None:
        return []
    rows = list(
        db.execute(
            select(Character, User)
            .join(User, Character.player_id == User.id)
            .where(builds.building_for(troupe_id))
        )
    )
    ids = [c.id for c, _ in rows]
    standing = social_age.standings(db, ids)
    sects = titles.character_sects(db, ids)
    traits_changed = {
        character_id: at
        for character_id, at in db.execute(
            select(CharacterTrait.character_id, func.max(CharacterTrait.updated_at))
            .where(CharacterTrait.character_id.in_(ids))
            .group_by(CharacterTrait.character_id)
        )
    }
    entries: list[BuildEntry] = []
    for character, player in rows:
        changed = max(
            character.updated_at, traits_changed.get(character.id) or character.updated_at
        )
        entries.append(
            BuildEntry(
                character_id=character.id,
                character_name=character.name,
                player_id=player.id,
                player_name=player.display_name,
                player_handle=player.handle,
                splat=character.splat,
                clan=standing[character.id].clan,
                sect=sects.get(character.id),
                picture=pictures.picture_url(character.id, character.picture_id),
                creation_complete=character.creation_completed_at is not None,
                to_place=_to_place(db, character),
                broken=_broken(db, character),
                started_at=character.created_at,
                changed_at=changed,
            )
        )
    # Newest change first; the id breaks a tie, as rows made together share a time.
    entries.sort(key=lambda e: e.character_id, reverse=True)
    entries.sort(key=lambda e: e.changed_at, reverse=True)
    return entries


@router.get("/builds/count")
def being_built_count(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BuildCount:
    """How many are being built, for the tab."""
    troupe = _troupe(db, user, troupe_id)
    return BuildCount(count=0 if troupe.archived_at else builds.count(db, troupe_id))


@router.get("/builds/{character_id}/print")
def print_build(
    troupe_id: uuid.UUID, character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> PrintedSheet:
    """The sheet of a character being built here, to read: staff see it, but neither
    change it nor open its Play View, as it isn't in the troupe."""
    troupe = _troupe(db, user, troupe_id)
    character = db.get(Character, character_id)
    if (
        character is None
        or troupe.archived_at is not None
        or not builds.is_building_for(db, character, troupe_id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character being built here.")
    return print_sheet(db, character, troupe_id)


def _to_place(db: DbSession, character: Character) -> list[str]:
    if character.creation_completed_at is not None:
        return []
    names = sheets.rules_for(db, character).rule_set.categories
    left = [
        p.category
        for p in creation.pools_with_strays(db, character)
        if p.kind == "picks" and p.remaining > 0
    ]
    return [names[c].name if c in names else c for c in dict.fromkeys(left)]


def _broken(db: DbSession, character: Character) -> list[str]:
    return list(
        dict.fromkeys(
            v.message
            for v in sheets.sheet_violations(db, character)
            if v.check.strength in ("refuse", "complete")
        )
    )
