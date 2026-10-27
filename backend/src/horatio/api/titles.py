"""A troupe's titles, and who holds them."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import titles
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Troupe
from horatio.permissions import TroupeAction
from horatio.rules.status import GENERAL, TitleData

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["titles"])


class WhileAbsentOut(BaseModel):
    title: str
    status: list[str]
    note: str


class TitleHolderOut(BaseModel):
    character_id: uuid.UUID
    character_name: str
    # The character's sect, from its sheet.
    sect: str | None
    # It holds a title of another sect, given before titles had sects or since it
    # changed sect: kept, for staff to look at.
    out_of_sect: bool


class TitleOut(BaseModel):
    name: str
    # None: it can go to a character of any sect.
    sect: str | None
    # The abiding status it gives while held (horatio.rules.status).
    status: list[str]
    # One of these as well, chosen each game.
    choose_one: list[str]
    while_absent: list[WhileAbsentOut]
    page: str | None
    # Added by this troupe, which can change and remove it.
    house: bool
    # The troupe gives it now: it has no sect, or one of the troupe's. One it
    # doesn't is listed only while someone holds it.
    offered: bool
    holders: list[TitleHolderOut]


class StatusChoice(BaseModel):
    """Abiding status a troupe's own title can give."""

    name: str
    sect: str


class TitlesOut(BaseModel):
    # The sects whose titles the troupe gives: its allowed sects, or every sect.
    sects: list[str]
    titles: list[TitleOut]
    # Abiding status of those sects, and general status.
    status_choices: list[StatusChoice]


class TitleChange(BaseModel):
    # None: it can go to a character of any sect.
    sect: str | None = None
    # Abiding status of its sect, or general status.
    status: list[str] = []


class NewTitle(TitleChange):
    name: str = Field(min_length=1, max_length=100)


class HeldTitles(BaseModel):
    titles: list[str]


def title_out(
    title: TitleData, troupe: Troupe, house: set[str], holders: list[TitleHolderOut]
) -> TitleOut:
    return TitleOut(
        name=title.name,
        sect=title.sect,
        status=list(title.status),
        choose_one=list(title.choose_one),
        while_absent=[
            WhileAbsentOut(title=a.title, status=list(a.status), note=a.note)
            for a in title.while_absent
        ],
        page=title.page,
        house=title.name in house,
        offered=titles.offers(troupe, title),
        holders=holders,
    )


def titles_out(db: DbSession, troupe: Troupe) -> TitlesOut:
    known = titles.title_data(db, troupe.id)
    house = {t.name for t in titles.house_titles(db, troupe.id)}
    holders: dict[str, list[TitleHolderOut]] = {}
    for h in titles.holdings(db, troupe.id):
        holders.setdefault(h.title, []).append(
            TitleHolderOut(
                character_id=h.character.id,
                character_name=h.character.name,
                sect=h.sect,
                out_of_sect=h.out_of_sect,
            )
        )
    # A title held but no longer in the rules is still listed, so it can be taken.
    for name in holders.keys() - known.keys():
        known[name] = TitleData(name=name)
    sects = titles.troupe_sects(db, troupe)
    return TitlesOut(
        sects=sects,
        titles=[
            title_out(t, troupe, house, holders.get(name, []))
            for name, t in sorted(known.items())
            if name in house or name in holders or titles.offers(troupe, t)
        ],
        status_choices=[
            StatusChoice(name=name, sect=sect)
            for name, sect in titles.abiding_status(db).items()
            if sect in sects or sect == GENERAL
        ],
    )


@router.get("/titles")
def list_titles(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TitlesOut:
    """The titles the troupe gives, with their sect and status, and who holds them."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    return titles_out(db, troupe)


@router.post("/titles", status_code=status.HTTP_201_CREATED)
def add_title(troupe_id: uuid.UUID, body: NewTitle, db: DbSession, user: CurrentUser) -> TitlesOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    titles.add_title(db, user, troupe, body.name, body.sect, body.status)
    db.commit()
    return titles_out(db, troupe)


@router.put("/titles/{name}")
def change_title(
    troupe_id: uuid.UUID, name: str, body: TitleChange, db: DbSession, user: CurrentUser
) -> TitlesOut:
    """Change the sect and status of a title the troupe added, for all who hold it."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    titles.change_title(db, user, troupe, name, body.sect, body.status)
    db.commit()
    return titles_out(db, troupe)


@router.delete("/titles/{name}")
def remove_title(troupe_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser) -> TitlesOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    titles.remove_title(db, user, troupe, name)
    db.commit()
    return titles_out(db, troupe)


@router.put("/characters/{character_id}/titles")
def set_titles(
    troupe_id: uuid.UUID,
    character_id: uuid.UUID,
    body: HeldTitles,
    db: DbSession,
    user: CurrentUser,
) -> HeldTitles:
    """Give a character in this troupe exactly these titles."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    character = db.get(Character, character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    held = titles.set_titles(db, user, troupe, character, body.titles)
    db.commit()
    return HeldTitles(titles=held)
