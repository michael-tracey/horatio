"""Specialisations a character can choose, a troupe's own lists, and filling in a
trait's missing detail."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import sheets, specializations
from horatio.api.downtimes import staff_troupe
from horatio.api.sheets import SheetOut, players_character, sheet_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import TroupeAction, visible_character
from horatio.rules.store import read_troupe_rules

router = APIRouter(tags=["specialisations"])


class KindOut(BaseModel):
    category: str
    name: str
    # The skill or background it specialises, and its rating on the sheet.
    parent_category: str
    parent_name: str
    parent_rating: int
    options: list[str]
    # The options are the troupe's own list, not the catalogue's.
    from_troupe: bool
    # Free text is allowed (as "Custom" with the text as detail).
    custom: bool
    held: list[dict[str, str]]


class TroupeKindOut(BaseModel):
    category: str
    name: str
    # Where it is listed on a sheet: "Skills" or "Backgrounds".
    group: str
    parent_name: str
    catalogue: list[str]
    # The troupe's list; None uses the catalogue (and free text).
    troupe: list[str] | None


class OptionList(BaseModel):
    names: list[str] = Field(max_length=500)


class DetailChange(BaseModel):
    category: str
    name: str
    detail: str = Field(min_length=1, max_length=200)


@router.get("/characters/{character_id}/specializations")
def character_kinds(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[KindOut]:
    character = visible_character(db, user, character_id)
    return [
        KindOut(
            category=k.category,
            name=k.name,
            parent_category=k.parent_category,
            parent_name=k.parent_name,
            parent_rating=k.parent_rating,
            options=k.options,
            from_troupe=k.from_troupe,
            custom=k.custom,
            held=[{"name": n, "detail": d} for n, d in k.held],
        )
        for k in specializations.kinds(db, character)
    ]


@router.put("/characters/{character_id}/traits/detail")
def set_detail(
    character_id: uuid.UUID, body: DetailChange, db: DbSession, user: CurrentUser
) -> SheetOut:
    """Fill in a trait's missing detail, such as a Crafts bought without a field."""
    character = players_character(db, user, character_id)
    with sheets.checked(db, character, user):
        sheets.set_detail(db, user, character, body.category, body.name, body.detail.strip())
    db.commit()
    return sheet_out(db, character)


@router.get("/troupes/{troupe_id}/specializations")
def troupe_kinds(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[TroupeKindOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    rules = read_troupe_rules(db, "vampire", troupe_id)
    lists = specializations.troupe_options(db, troupe_id)
    return [
        TroupeKindOut(
            category=c.key,
            name=c.name,
            group=c.group,
            parent_name=c.specializes["name"],
            catalogue=sorted(
                n
                for (cat, n) in rules.rule_set.traits
                if cat == c.key and n != specializations.CUSTOM
            ),
            troupe=lists.get(c.key),
        )
        for c in rules.rule_set.categories.values()
        if c.specializes
    ]


@router.put("/troupes/{troupe_id}/specializations/{category}")
def set_troupe_kind(
    troupe_id: uuid.UUID, category: str, body: OptionList, db: DbSession, user: CurrentUser
) -> list[TroupeKindOut]:
    """Replace a troupe's list for one kind of specialisation; empty goes back to the
    catalogue's."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    specializations.set_troupe_options(db, user, troupe, category, body.names)
    db.commit()
    return troupe_kinds(troupe_id, db, user)
