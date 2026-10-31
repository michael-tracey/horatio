"""A character's titles on its Status & Titles tab (horatio.titles): those it holds in
its home troupe, which one is active, and those it can choose, of its sect; and
choosing, switching and giving them up, as the troupe's Titles on sheets setting
allows."""

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from horatio import sheets, titles
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, User
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}/titles", tags=["titles"])


class HeldTitleOut(BaseModel):
    name: str
    sect: str | None
    # The status it gives while active: "Noble", "Blessed or Enforcer".
    status: list[str]
    page: str | None
    # The one title that gives status. The others give none while it is.
    active: bool
    # Of another sect than the character's now: it gives nothing even if active.
    out_of_sect: bool


class TitleChoiceOut(BaseModel):
    name: str
    sect: str | None
    status: list[str]
    page: str | None
    # Only one character in the troupe holds it at a time.
    unique: bool
    # The other characters in the troupe who hold it, by any of its names.
    holders: list[str]
    # Whether the viewer can choose it now: not a unique title someone else holds,
    # unless the viewer is staff.
    open: bool


class CharacterTitlesOut(BaseModel):
    # The home troupe, whose titles the character chooses from.
    troupe_id: uuid.UUID | None
    troupe_name: str | None
    sect: str | None
    # Titles on sheets: "players" choose their characters' titles, or "staff" only.
    setting: str
    # Whether the viewer chooses the character's titles, and as whom.
    acting: Literal["player", "staff"] | None
    # Whether the viewer chooses which title is active: its player always can.
    can_switch: bool
    # Why there are no titles to choose, or only some: no home troupe, no sect, or
    # the troupe keeps titles to staff.
    why: str | None
    held: list[HeldTitleOut]
    # The troupe's titles of the character's sect and of none, that it does not hold,
    # in court order.
    choices: list[TitleChoiceOut]


class ChooseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Make it the active title. The first title held is active anyway.
    active: bool = False


class ActiveIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def titles_out(db: DbSession, user: User, character: Character) -> CharacterTitlesOut:
    troupe = titles.home_of(db, character)
    sect = titles.character_sects(db, [character.id]).get(character.id)
    acting = titles.may_choose(db, user, character, troupe)
    if troupe is None:
        return CharacterTitlesOut(
            troupe_id=None,
            troupe_name=None,
            sect=sect,
            setting="players",
            acting=None,
            can_switch=False,
            why=f"{character.name} has no home troupe: titles are held in a troupe.",
            held=[],
            choices=[],
        )
    setting = titles.setting_of(troupe)
    data = titles.title_data(db, troupe.id)
    order = titles.court_order(db, troupe.id)
    active = titles.active_title(db, troupe.id, character.id)
    holding = titles.held(db, troupe.id, character.id)
    held = [
        HeldTitleOut(
            name=name,
            sect=data[name].sect if name in data else None,
            status=titles.gives_words(data.get(name)),
            page=data[name].page if name in data else None,
            active=name == active,
            out_of_sect=titles.out_of_sect(data.get(name), sect),
        )
        for name in sorted(holding, key=lambda n: titles.court_key(order, n))
    ]
    # Who holds each office, by any of its names (a Baron's, an Advocate's).
    holders: dict[str, list[str]] = {}
    for h in titles.holdings(db, troupe.id):
        if h.character.id != character.id:
            office = data[h.title].office if h.title in data else h.title
            holders.setdefault(office, []).append(h.character.name)
    choices = [
        TitleChoiceOut(
            name=name,
            sect=t.sect,
            status=titles.gives_words(t),
            page=t.page,
            unique=t.unique,
            holders=holders.get(t.office, []),
            open=acting is not None
            and not (t.unique and holders.get(t.office) and acting == "player"),
        )
        for name, t in sorted(
            titles.offered(db, troupe).items(), key=lambda i: titles.court_key(order, i[0])
        )
        if name not in holding and not titles.out_of_sect(t, sect)
    ]
    why = None
    if sect is None:
        why = f"{character.name} has no sect: only titles of any sect."
    if acting is None and titles.is_player(user, character) and setting == "staff":
        why = f"In {troupe.name}, only staff give titles: ask them for one."
    return CharacterTitlesOut(
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        sect=sect,
        setting=setting,
        acting=acting,
        can_switch=titles.may_switch(db, user, character, troupe) is not None,
        why=why,
        held=held,
        choices=choices,
    )


@router.get("")
def read_titles(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CharacterTitlesOut:
    """The titles the character holds in its home troupe, the active one, and those
    it can choose."""
    character = visible_character(db, user, character_id)
    return titles_out(db, user, character)


@router.post("")
def choose_title(
    character_id: uuid.UUID, body: ChooseIn, db: DbSession, user: CurrentUser
) -> CharacterTitlesOut:
    """The character takes one of its home troupe's titles of its sect. Staff are told."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    titles.choose(db, user, character, body.name, active=body.active)
    db.commit()
    return titles_out(db, user, character)


@router.put("/active")
def make_active(
    character_id: uuid.UUID, body: ActiveIn, db: DbSession, user: CurrentUser
) -> CharacterTitlesOut:
    """Make a title the character holds its active one: its status in place of the
    old one's. Staff are told."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    titles.switch(db, user, character, body.name)
    db.commit()
    return titles_out(db, user, character)


@router.delete("/{name}")
def give_up_title(
    character_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser
) -> CharacterTitlesOut:
    """The character gives up a title, and the status it gave. Staff are told."""
    visible_character(db, user, character_id)
    character = sheets.lock_character(db, character_id)
    titles.give_up(db, user, character, name)
    db.commit()
    return titles_out(db, user, character)
