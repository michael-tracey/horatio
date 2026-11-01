"""A troupe's titles, and who holds them; and the status rules by sect, with where
each status comes from in the troupe."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import sect_status, titles
from horatio.api.downtimes import staff_troupe
from horatio.api.sect_status import StatusAbout, about
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
    # The one of its titles here that gives it status.
    active: bool = False


class TitleWhatOut(BaseModel):
    """What a title is, beyond the status it gives (horatio.rules.status.TitleData)."""

    # The title it is another name for, giving the same: a Master Harpy is a Harpy.
    alias_of: str | None = None
    # A clan's title (a Tremere Lord): it has no sect, and gives no sect status.
    clan: str | None = None
    # Why it gives no status, where the book says so; its page is the title's page.
    gives_none: str = ""
    # What the rules data cannot say about what it gives, in words.
    note: str = ""
    # No book describes it yet (the Independent Alliance's): it gives nothing.
    no_rules_yet: bool = False


def title_what(title: TitleData | None) -> TitleWhatOut:
    if title is None:
        return TitleWhatOut()
    return TitleWhatOut(
        alias_of=title.alias_of,
        clan=title.clan,
        gives_none=title.gives_none,
        note=title.note,
        no_rules_yet=title.no_rules_yet,
    )


class TitleOut(TitleWhatOut):
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
    # Only one character holds it at a time: players cannot choose it while
    # someone does.
    unique: bool = False
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
    # The troupe's own titles in their order on the Who's Who, after the rule sets'.
    court_order: list[str]


class StatusSourceOut(BaseModel):
    """Where a status comes from in the troupe."""

    kind: Literal["title", "social_age", "faction", "merit"]
    # The title, social age ("Elder"), faction ("Loyalist") or merit.
    name: str
    page: str | None
    # A title's other names: a Harpy is also a Master Harpy.
    aliases: list[str]
    # "while the Prince is absent", "one of Blessed or Enforcer, chosen each game".
    condition: str
    # The troupe's own title.
    house: bool


class StatusRuleOut(StatusAbout):
    # Where it usually comes from, in words, as the rules data says.
    source: str
    # What gives it in the troupe: its titles, social ages, factions and merits.
    given_by: list[StatusSourceOut]


class SectStatusOut(BaseModel):
    # "General" for the status every sect has.
    sect: str
    # The sect's name for Accepted: Acknowledged, Initiated, Committed.
    accepted: str | None
    page: str | None
    statuses: list[StatusRuleOut]


class StatusCapsOut(BaseModel):
    """What a character carries into a game (MET: VTM p. 313)."""

    abiding_sources: int
    fleeting: int
    lesser_ban: int
    greater_ban: int
    page: str | None


class StatusRulesOut(BaseModel):
    caps: StatusCapsOut
    # The general status, then the status of each sect the troupe takes.
    sects: list[SectStatusOut]


class TitleChange(BaseModel):
    # None: it can go to a character of any sect.
    sect: str | None = None
    # Abiding status of its sect, or general status.
    status: list[str] = []
    # Only one character holds it at a time.
    unique: bool = False


class NewTitle(TitleChange):
    name: str = Field(min_length=1, max_length=100)


class HeldTitles(BaseModel):
    titles: list[str]


def title_out(
    title: TitleData, troupe: Troupe, house: set[str], holders: list[TitleHolderOut]
) -> TitleOut:
    return TitleOut(
        **title_what(title).model_dump(),
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
        unique=title.unique,
        offered=titles.offers(troupe, title),
        holders=holders,
    )


def titles_out(db: DbSession, troupe: Troupe) -> TitlesOut:
    known = titles.title_data(db, troupe.id)
    own = [t.name for t in titles.house_titles(db, troupe.id)]
    house = set(own)
    holders: dict[str, list[TitleHolderOut]] = {}
    for h in titles.holdings(db, troupe.id):
        holders.setdefault(h.title, []).append(
            TitleHolderOut(
                character_id=h.character.id,
                character_name=h.character.name,
                sect=h.sect,
                out_of_sect=h.out_of_sect,
                active=h.active,
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
        court_order=own,
    )


@router.get("/titles")
def list_titles(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TitlesOut:
    """The titles the troupe gives, with their sect and status, and who holds them."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    return titles_out(db, troupe)


@router.get("/status-rules")
def status_rules(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> StatusRulesOut:
    """Every status of the troupe's sects, and the general status, by sect: its type,
    what it does, and where it comes from here. Anyone signed in may read it, as
    they may the troupe's house rules: it is the book's rules and the troupe's titles,
    never who holds them."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or (troupe.archived_at is not None and not user.is_custodian):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    caps, sects = sect_status.status_rules(db, troupe)
    return StatusRulesOut(
        caps=StatusCapsOut(
            abiding_sources=caps.abiding_sources,
            fleeting=caps.fleeting,
            lesser_ban=caps.lesser_ban,
            greater_ban=caps.greater_ban,
            page=caps.page,
        ),
        sects=[
            SectStatusOut(
                sect=s.sect,
                accepted=s.accepted,
                page=s.page,
                statuses=[
                    StatusRuleOut(
                        **about(r.status).model_dump(),
                        source=r.status.source,
                        given_by=[
                            StatusSourceOut(
                                kind=g.kind,
                                name=g.name,
                                page=g.page,
                                aliases=list(g.aliases),
                                condition=g.condition,
                                house=g.house,
                            )
                            for g in r.sources
                        ],
                    )
                    for r in s.statuses
                ],
            )
            for s in sects
        ],
    )


@router.post("/titles", status_code=status.HTTP_201_CREATED)
def add_title(troupe_id: uuid.UUID, body: NewTitle, db: DbSession, user: CurrentUser) -> TitlesOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    titles.add_title(db, user, troupe, body.name, body.sect, body.status, body.unique)
    db.commit()
    return titles_out(db, troupe)


@router.put("/titles/{name}")
def change_title(
    troupe_id: uuid.UUID, name: str, body: TitleChange, db: DbSession, user: CurrentUser
) -> TitlesOut:
    """Change the sect and status of a title the troupe added, for all who hold it."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_TITLES)
    titles.change_title(db, user, troupe, name, body.sect, body.status, body.unique)
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
