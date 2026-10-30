"""A character's Retainers: the list under the background, with who may edit and link."""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from horatio import identities, reference, retainers, sheets
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, User
from horatio.permissions import visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["retainers"])


class RetainerPower(BaseModel):
    level: int
    name: str
    note: str


class RetainerOut(BaseModel):
    # None for a Retainer bought on the sheet with nothing kept for it yet.
    id: uuid.UUID | None
    # The name, and the dots: for one bought on the sheet, its detail ("" for one
    # held without a name) and rating there.
    name: str
    dots: int
    bought: bool
    description: str
    # The merit that gave it; empty for the background's own.
    from_merit: str
    lost: str | None  # released | killed
    lost_on: date | None
    # The NPC it is linked to, for those who can see that NPC.
    npc_id: uuid.UUID | None
    npc_name: str | None
    # What it is as an NPC (core p. 105): a ghoul or not, its specialties (skills,
    # each +5 to its pool) and a ghoul's discipline specialty, with the powers
    # that reaches, one for each dot.
    ghoul: bool = False
    specialties: list[str] = []
    discipline: str = ""
    powers: list[RetainerPower] = []
    # Its test pool for most actions (dots x 2), its health levels (one a dot)
    # and potent Blood (a ghoul's 5), and what its taps on the Play View are kept under.
    pool: int = 0
    health: int = 0
    blood: int = 0
    tracker: str = ""
    # For one lost (p. 104): its dots are back not before `back_from` (two weeks a
    # dot), and not until `back_games` games (one a dot) have gone by; `back_on`
    # is the day they are, once the home troupe's schedule has those games.
    # `away` while they are out of reach.
    back_from: date | None = None
    back_games: int = 0
    back_on: date | None = None
    away: bool = False
    # Given by its merit's rules (horatio.rules.grants): its dots, `kind` ("Ghouled
    # animal") and being a ghoul are the merit's, with a note of how it is built,
    # the page, and what its discipline specialty can be beside a ghoul's.
    given: bool = False
    kind: str = ""
    note: str = ""
    page: str | None = None
    given_disciplines: list[str] = []


class RetainersOut(BaseModel):
    # The Retainers background's dots, across every Retainer bought.
    rating: int
    retainers: list[RetainerOut]
    can_edit: bool
    can_link: bool
    # What specialties can be: any skill, and for a ghoul one discipline in-clan
    # for the character it serves.
    skills: list[str] = []
    disciplines: list[str] = []


class RetainerIn(BaseModel):
    # Present for a Retainer already listed.
    id: uuid.UUID | None = None
    # One bought on the sheet is named as it was bought there, and its dots are the sheet's.
    name: str = Field(min_length=1, max_length=200)
    dots: int
    description: str = Field(default="", max_length=500)
    from_merit: str = Field(default="", max_length=100)
    lost: str | None = Field(default=None, pattern="^(released|killed)$")
    lost_on: date | None = None
    npc_id: uuid.UUID | None = None
    ghoul: bool = False
    specialties: list[str] = Field(default=[], max_length=10)
    discipline: str = Field(default="", max_length=100)


class RetainersIn(BaseModel):
    retainers: list[RetainerIn] = Field(max_length=retainers.MAX_LISTED)


def listed(db: Session, entries: list[retainers.Listed], viewer: User | None) -> list[RetainerOut]:
    out: list[RetainerOut] = []
    for e in entries:
        r = e.row
        npc = retainers.viewable_npc(db, viewer, r) if r else None
        out.append(
            RetainerOut(
                id=r.id if r else None,
                name=e.name,
                dots=e.dots,
                bought=e.bought,
                description=r.description if r else "",
                from_merit=e.from_merit,
                lost=r.lost if r else None,
                lost_on=r.lost_on if r else None,
                npc_id=npc.id if npc else None,
                npc_name=npc.name if npc else None,
                ghoul=e.ghoul,
                specialties=list(r.specialties) if r else [],
                discipline=r.discipline if r else "",
                powers=powers(r.discipline, e.dots) if r and r.discipline else [],
                pool=e.dots * 2,
                health=e.dots,
                blood=retainers.GHOUL_BLOOD if e.ghoul else 0,
                tracker=retainers.tracker(e),
                back_from=e.back.earliest if e.back else None,
                back_games=e.back.games if e.back else 0,
                back_on=e.back.on if e.back else None,
                away=e.back.away(date.today()) if e.back else False,
                given=e.given is not None,
                kind=e.given.kind if e.given else "",
                note=e.given.note if e.given else "",
                page=e.given.page if e.given else None,
                given_disciplines=list(e.given.disciplines) if e.given else [],
            )
        )
    return out


def powers(discipline: str, dots: int) -> list[RetainerPower]:
    """The powers a ghoul's discipline specialty reaches: one a dot (p. 105)."""
    return [
        RetainerPower(level=p["level"], name=p["name"], note=p["note"])
        for p in reference.catalogue().powers.get(discipline, [])
        if p["level"] <= dots
    ]


def retainers_out(db: Session, character: Character, user: User) -> RetainersOut:
    return RetainersOut(
        rating=retainers.rating(db, character),
        retainers=listed(db, retainers.read(db, character), user),
        can_edit=retainers.can_edit(db, user, character),
        can_link=retainers.can_link(db, user, character),
        skills=retainers.skills(db, character),
        disciplines=retainers.domitor_disciplines(db, character),
    )


@router.get("/retainers")
def read_retainers(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> RetainersOut:
    return retainers_out(db, visible_character(db, user, character_id), user)


@router.put("/retainers")
def save_retainers(
    character_id: uuid.UUID, body: RetainersIn, db: DbSession, user: CurrentUser
) -> RetainersOut:
    """Replace the list. The player edits descriptions and losses, and the names
    and dots of those not bought on the sheet; staff do the same and alone link
    an NPC."""
    character = visible_character(db, user, character_id)
    if not retainers.can_edit(db, user, character):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the character's player or its staff can change this."
        )
    character = sheets.lock_character(db, character.id)
    retainers.replace(
        db,
        user,
        character,
        [retainers.Draft(**r.model_dump()) for r in body.retainers],
        link=retainers.can_link(db, user, character),
    )
    db.commit()
    return retainers_out(db, character, user)


class IdentityOut(BaseModel):
    # Its name on the sheet ("" for one held without), its dots, and what that
    # rating means (p. 99).
    name: str
    dots: int
    line: str
    # The sect or group that has Accepted it (p. 310); empty for none.
    accepted_by: str


class IdentitiesOut(BaseModel):
    identities: list[IdentityOut]
    page: str
    can_edit: bool


class IdentityIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    accepted_by: str = Field(default="", max_length=100)


class IdentitiesIn(BaseModel):
    identities: list[IdentityIn] = Field(max_length=30)


def identities_out(db: Session, character: Character) -> list[IdentityOut]:
    return [IdentityOut(**vars(i)) for i in identities.read(db, character)]


@router.get("/identities")
def read_identities(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> IdentitiesOut:
    character = visible_character(db, user, character_id)
    return IdentitiesOut(
        identities=identities_out(db, character),
        page=identities.PAGE,
        can_edit=retainers.can_edit(db, user, character),
    )


@router.put("/identities")
def save_identities(
    character_id: uuid.UUID, body: IdentitiesIn, db: DbSession, user: CurrentUser
) -> IdentitiesOut:
    """Say which sect or group has Accepted each identity. The player and the
    staff of its home troupe can."""
    character = visible_character(db, user, character_id)
    if not retainers.can_edit(db, user, character):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the character's player or its staff can change this."
        )
    character = sheets.lock_character(db, character.id)
    identities.accept(db, user, character, {i.name: i.accepted_by for i in body.identities})
    db.commit()
    return read_identities(character_id, db, user)
