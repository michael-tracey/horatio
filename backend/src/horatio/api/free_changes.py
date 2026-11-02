"""A troupe's free changes for new characters (horatio.free_changes, issue #439), under
Customise › Rules: none, by date or by games played, and the traits never refunded."""

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import free_changes
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe
from horatio.permissions import TroupeAction
from horatio.rules.store import read_troupe_rules
from horatio.sheets import unprocessable

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["house rules"])


class TraitRef(BaseModel):
    category: str
    name: str


class FreeChangesSetting(BaseModel):
    # "none": locked on acceptance; "date": for `days` days from acceptance; "games":
    # until the character has attended `games` of the troupe's games.
    kind: Literal["none", "date", "games"]
    days: int = Field(default=30, ge=1, le=365)
    games: int = Field(default=3, ge=1, le=50)
    # Traits never refunded in free changes, from the catalogue.
    excluded: list[TraitRef] = Field(default=[], max_length=100)


class FreeChangesSettingOut(FreeChangesSetting):
    # The setting in words, as the House rules tab says it.
    text: str


def setting_out(troupe: Troupe) -> FreeChangesSettingOut:
    return FreeChangesSettingOut(
        kind=troupe.free_changes,  # type: ignore[arg-type]  # checked by the database
        days=troupe.free_changes_days,
        games=troupe.free_changes_games,
        excluded=[TraitRef(**e) for e in troupe.free_changes_excluded],
        text=free_changes.setting_text(troupe),
    )


@router.get("/free-changes")
def read_free_changes(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> FreeChangesSettingOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return setting_out(troupe)


@router.put("/free-changes")
def set_free_changes(
    troupe_id: uuid.UUID, body: FreeChangesSetting, db: DbSession, user: CurrentUser
) -> FreeChangesSettingOut:
    """Set how long the troupe's new characters stay open to free changes. It applies
    at once to the characters whose free changes are open; turning it on gives them to
    characters accepted from now on."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    known = {
        key
        for splat in troupe.allowed_splats
        for key in read_troupe_rules(db, splat, troupe.id).rule_set.traits
    }
    for trait in body.excluded:
        if (trait.category, trait.name) not in known:
            raise unprocessable(f"There is no trait {trait.name} to exclude.")
    free_changes.change_setting(
        db,
        user,
        troupe,
        body.kind,
        body.days,
        body.games,
        [(e.category, e.name) for e in body.excluded],
    )
    db.commit()
    return setting_out(troupe)
