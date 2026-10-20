"""What a printed character sheet shows: the sheet as it stands, with any discipline
dots still waiting on the home troupe marked."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import pictures, sheets, titles
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, SheetVersion, TraitCategory, TraitDefinition, Troupe, User
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
    # Dots waiting on the home troupe: the rating they were bought from.
    pending_from: int | None
    # For a specialisation: the skill or background it belongs to, as its
    # category and name (from the rule set's `specializes`).
    specializes: dict[str, str] | None


class PrintedSheet(BaseModel):
    character_name: str
    player_name: str
    splat: str
    troupe_name: str | None
    # Titles held in that troupe.
    titles: list[str]
    # The character's picture (horatio.pictures), small in the header, or None.
    picture: str | None
    kind: str  # pc | npc
    # Whether `troupe_name` is the home troupe, and when and by whom it accepted the character.
    home: bool
    accepted_at: datetime | None
    accepted_by: str | None
    traits: list[PrintedTrait]


@router.get("/print")
def printed_sheet(
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    troupe_id: uuid.UUID | None = None,
) -> PrintedSheet:
    """The sheet as it stands, headed for `troupe_id` (by default the home troupe, else
    the first troupe joined), whose titles it shows."""
    return print_sheet(db, visible_character(db, user, character_id), troupe_id)


def print_sheet(db: Session, character: Character, troupe_id: uuid.UUID | None) -> PrintedSheet:
    """`character`'s printed sheet, headed for `troupe_id` if it belongs there."""
    joined = [m.troupe_id for m in sheets.memberships(db, character)]
    troupe = next((t for t in (troupe_id, character.home_troupe_id, *joined) if t in joined), None)
    found = (
        sheets.membership(db, character, character.home_troupe_id)
        if character.home_troupe_id
        else None
    )
    version = (
        db.get(SheetVersion, found.approved_version_id)
        if found is not None and found.approved_version_id is not None
        else None
    )
    snapshot = [r.snapshot() for r in sheets.sheet_rows(db, character)]
    held = {
        (name, d.detail): d.from_rating
        for (_, d), name in (
            (pair, db.get_one(TraitDefinition, pair[1].trait_definition_id).name)
            for pair in sheets.pending_disciplines(db, character)
        )
    }

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
            pending_from=held.get((t["name"], t["detail"]))
            if t["category"] == "disciplines"
            else None,
            specializes=dict(rule_set.categories[t["category"]].specializes or {}) or None,
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
        home=troupe is not None and troupe == character.home_troupe_id,
        accepted_at=version.approved_at if version else None,
        accepted_by=db.get_one(User, version.approved_by).display_name if version else None,
        traits=traits,
        picture=pictures.picture_url(character.id, character.picture_id),
    )
