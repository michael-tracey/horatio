"""Specialisations a character can choose, a troupe's own lists, and filling in a
trait's missing detail."""

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import languages, sheets, specializations
from horatio.api.downtimes import staff_troupe
from horatio.api.sheets import SheetOut, players_character, sheet_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe
from horatio.permissions import TroupeAction, visible_character
from horatio.rules import languages as language_rules
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
    # How many the character may hold under its rules (one a dot by the book, or the
    # troupe's chart of languages), and how many it holds that count against that:
    # not those another trait gives. None where nothing limits them.
    allowed: int | None
    counted: int


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
            allowed=k.allowed,
            counted=k.counted,
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
    """The troupe's lists for each kind of specialisation. They are the troupe's, for
    every splat: a ghoul's kinds and catalogue are the vampire's."""
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


# --- Languages ------------------------------------------------------------------


class LanguagesIn(BaseModel):
    # "book", one language per dot of Linguistics (p. 95); "accelerated", the
    # accelerated chart; or "custom", the troupe's own chart.
    mode: Literal["book", "accelerated", "custom"]
    # The troupe's own chart: languages at each rating from 1. Kept while another
    # chart is chosen; left out, the one it has stays.
    custom: list[int] | None = Field(default=None, max_length=20)
    # Natural Linguist doubles the chart in use, as the book has it (p. 252).
    natural_doubles: bool = True


class OverOut(BaseModel):
    """A character holding more languages than the troupe's chart now allows: they
    keep them, and the sheet shows the broken check."""

    character_id: uuid.UUID
    name: str
    held: int
    allowed: int


class LanguagesOut(BaseModel):
    mode: Literal["book", "accelerated", "custom"]
    # The troupe's own chart, kept while another is chosen; empty until set.
    custom: list[int]
    natural_doubles: bool
    # The languages each rating gives under the chart in use, from 1 to max_rating,
    # without Natural Linguist; and the accelerated chart, for offering.
    table: list[int]
    accelerated: list[int]
    max_rating: int
    # The setting in words, and the book's.
    text: str
    book_text: str
    over: list[OverOut]


def languages_out(db: DbSession, troupe_id: uuid.UUID) -> LanguagesOut:
    troupe = db.get_one(Troupe, troupe_id)
    rule = language_rules.rule_of(troupe)
    most = languages.max_rating(db, troupe_id)
    return LanguagesOut(
        mode=rule.mode,
        custom=list(rule.custom),
        natural_doubles=rule.natural_doubles,
        table=rule.ratings(most),
        accelerated=list(language_rules.ACCELERATED),
        max_rating=most,
        text=language_rules.setting_text(rule),
        book_text=language_rules.BOOK_TEXT,
        over=[
            OverOut(character_id=o.character_id, name=o.name, held=o.held, allowed=o.allowed)
            for o in languages.over_limit(db, troupe_id)
        ],
    )


@router.get("/troupes/{troupe_id}/languages")
def read_languages(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> LanguagesOut:
    """How many languages Linguistics gives in the troupe, and who holds more."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return languages_out(db, troupe_id)


@router.put("/troupes/{troupe_id}/languages")
def set_languages(
    troupe_id: uuid.UUID, body: LanguagesIn, db: DbSession, user: CurrentUser
) -> LanguagesOut:
    """Choose how many languages Linguistics gives: creation, purchases, review and
    the sheet follow at once. A character holding more than the new chart allows
    keeps them, flagged on the sheet and listed here."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    languages.set_rule(db, user, troupe, body.mode, body.custom, body.natural_doubles)
    db.commit()
    return languages_out(db, troupe_id)
