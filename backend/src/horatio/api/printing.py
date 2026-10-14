"""What a printed character sheet shows: a troupe's approved sheet, or the sheet as
it stands when there is none (marked as not approved)."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from horatio import sheets, titles
from horatio.api.sheets import viewing_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import SheetVersion, TraitCategory, TraitDefinition, Troupe, User
from horatio.permissions import visible_character
from horatio.rules.store import read_troupe_rules

router = APIRouter(prefix="/characters/{character_id}", tags=["printing"])


class PrintedTrait(BaseModel):
    category: str
    category_name: str
    group: str
    name: str
    detail: str
    rating: int | None
    # For a skill: Physical, Social or Mental.
    attribute: str | None


class PrintedSheet(BaseModel):
    character_name: str
    player_name: str
    splat: str
    troupe_name: str | None
    # Titles held in that troupe.
    titles: list[str]
    kind: str  # pc | npc
    # Whether this is a troupe's approved sheet, and which version.
    approved: bool
    version: int | None
    approved_at: datetime | None
    approved_by: str | None
    traits: list[PrintedTrait]


@router.get("/print")
def printed_sheet(
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    troupe_id: uuid.UUID | None = None,
    current: bool = False,
) -> PrintedSheet:
    """The sheet to print. By default the approved sheet of `troupe_id` (or the home
    troupe); `current=true`, or no approved sheet, prints the sheet as it stands."""
    character = visible_character(db, user, character_id)
    troupe = viewing_troupe(db, character, troupe_id)
    found = sheets.membership(db, character, troupe) if troupe else None
    version = (
        db.get(SheetVersion, found.approved_version_id)
        if found is not None and found.approved_version_id is not None and not current
        else None
    )
    if version is not None:
        snapshot = version.snapshot
    else:
        snapshot = [r.snapshot() for r in sheets.sheet_rows(db, character)]

    rule_set = read_troupe_rules(db, character.splat, troupe).rule_set
    categories = list(
        db.execute(
            select(TraitCategory.key, TraitCategory.position).order_by(TraitCategory.position)
        )
    )
    order = {key: position for key, position in categories}
    names = {
        (key, name): props
        for key, name, props in db.execute(
            select(TraitCategory.key, TraitDefinition.name, TraitDefinition.properties).join(
                TraitDefinition, TraitDefinition.category_id == TraitCategory.id
            )
        )
    }
    traits = [
        PrintedTrait(
            category=t["category"],
            category_name=rule_set.categories[t["category"]].name,
            group=rule_set.categories[t["category"]].group,
            name=t["name"],
            detail=t["detail"],
            rating=t["rating"],
            attribute=names.get((t["category"], t["name"]), {}).get("attribute"),
        )
        for t in sorted(snapshot, key=lambda t: (order.get(t["category"], 999), t["name"]))
        if t["category"] in rule_set.categories
    ]
    return PrintedSheet(
        character_name=character.name,
        player_name=(
            db.get_one(User, character.player_id).display_name if character.kind == "pc" else "NPC"
        ),
        splat=character.splat,
        troupe_name=db.get_one(Troupe, troupe).name if troupe else None,
        titles=titles.held(db, troupe, character.id) if troupe else [],
        kind=character.kind,
        approved=version is not None,
        version=version.number if version else None,
        approved_at=version.approved_at if version else None,
        approved_by=db.get_one(User, version.approved_by).display_name if version else None,
        traits=traits,
    )
