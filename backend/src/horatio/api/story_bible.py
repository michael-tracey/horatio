"""A troupe's story bible (horatio.story_bible, #879): the staff-only companion to the
Setting Style Document. Its running staff, who write the setting, read it and keep
its notes; nobody else may, so it never reaches a player, the profile or print for
players."""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import chronicle, story_bible
from horatio.api.characters import CharacterOut, characters_out
from horatio.api.chronicle import ChronicleEventOut, event_out
from horatio.api.downtimes import staff_troupe
from horatio.api.locations import Kind as LocationKind
from horatio.api.troupe_profiles import Profile
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, Location, StoryBibleNote, Troupe, User
from horatio.permissions import TroupeAction
from horatio.story_bible import BibleError

router = APIRouter(prefix="/troupes/{troupe_id}/story-bible", tags=["story bible"])

Trimmed = Annotated[str, StringConstraints(strip_whitespace=True)]


class StoryBibleNoteIn(BaseModel):
    title: Annotated[Trimmed, Field(max_length=200)] = ""
    # Markdown.
    body: Annotated[Trimmed, Field(max_length=20000)] = ""


class StoryBibleOrderIn(BaseModel):
    # Every note, once each, in the new order.
    ids: list[uuid.UUID]


class StoryBibleNoteOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str


class StoryBibleLocaleOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: LocationKind
    rating: int
    # Who controls it: a character's name, or a name only; None for nobody.
    controller: str | None
    # The location it is a subsidiary of, if any.
    parent: str | None
    address: str
    description: str
    # Staff's notes on its record.
    notes: str


class StoryBibleOut(BaseModel):
    troupe: str
    # The chronicle's name, as the profile has it: the Setting Style Document's title.
    chronicle: str
    notes: list[StoryBibleNoteOut]
    # The chronicle's events (horatio.chronicle), every one, oldest first as recorded.
    chronology: list[ChronicleEventOut]
    # The troupe's NPCs, in play first, then retired.
    npcs: list[CharacterOut]
    # Its Stock Locations, without Havens.
    locales: list[StoryBibleLocaleOut]


def bible_troupe(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, for running staff only: those who write the Setting Style Document,
    and see its NPCs and locations."""
    return staff_troupe(db, user, troupe_id, TroupeAction.WRITE_SETTING)


def troupe_note(db: Session, troupe: Troupe, note_id: uuid.UUID) -> StoryBibleNote:
    note = db.get(StoryBibleNote, note_id)
    if note is None or note.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such note.")
    return note


def refused(error: BibleError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


def words_of(body: StoryBibleNoteIn) -> story_bible.Words:
    return story_bible.Words(title=body.title, body=body.body)


def locales_out(db: Session, troupe: Troupe) -> list[StoryBibleLocaleOut]:
    found = story_bible.locales(db, troupe)
    names = {
        id_: name
        for id_, name in db.execute(
            select(Location.id, Location.name).where(Location.troupe_id == troupe.id)
        )
    }
    controllers = {loc.controller_id for loc in found if loc.controller_id}
    who = (
        {c.id: c.name for c in db.scalars(select(Character).where(Character.id.in_(controllers)))}
        if controllers
        else {}
    )

    def controller(loc: Location) -> str | None:
        if loc.control == "character" and loc.controller_id:
            return who.get(loc.controller_id)
        if loc.control == "named":
            return loc.controller_name
        return None

    return [
        StoryBibleLocaleOut(
            id=loc.id,
            name=loc.name,
            kind=cast(LocationKind, loc.kind),
            rating=loc.rating,
            controller=controller(loc),
            parent=names.get(loc.parent_id) if loc.parent_id else None,
            address=loc.address,
            description=loc.description,
            notes=loc.notes,
        )
        for loc in found
    ]


def bible_out(db: Session, troupe: Troupe) -> StoryBibleOut:
    profile = Profile.model_validate(troupe.profile)
    return StoryBibleOut(
        troupe=troupe.name,
        chronicle=profile.setting.chronicle,
        notes=[
            StoryBibleNoteOut(id=n.id, title=n.title, body=n.body)
            for n in story_bible.notes(db, troupe.id)
        ],
        chronology=[event_out(e) for e in chronicle.events(db, troupe, full=True)],
        npcs=characters_out(db, story_bible.npcs(db, troupe)),
        locales=locales_out(db, troupe),
    )


@router.get("")
def read_story_bible(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> StoryBibleOut:
    """The troupe's story bible: its chronicle, NPCs and locations as Horatio holds
    them, and staff's own notes. For its running staff only."""
    return bible_out(db, bible_troupe(db, user, troupe_id))


@router.post("/notes", status_code=status.HTTP_201_CREATED)
def add_story_bible_note(
    troupe_id: uuid.UUID, body: StoryBibleNoteIn, db: DbSession, user: CurrentUser
) -> StoryBibleOut:
    """Add a note, last in the bible."""
    troupe = bible_troupe(db, user, troupe_id)
    try:
        story_bible.add(db, user, troupe, words_of(body))
    except BibleError as error:
        raise refused(error) from None
    db.commit()
    return bible_out(db, troupe)


@router.put("/notes/{note_id}")
def change_story_bible_note(
    troupe_id: uuid.UUID,
    note_id: uuid.UUID,
    body: StoryBibleNoteIn,
    db: DbSession,
    user: CurrentUser,
) -> StoryBibleOut:
    troupe = bible_troupe(db, user, troupe_id)
    note = troupe_note(db, troupe, note_id)
    try:
        story_bible.change(db, user, troupe, note, words_of(body))
    except BibleError as error:
        raise refused(error) from None
    db.commit()
    return bible_out(db, troupe)


@router.delete("/notes/{note_id}")
def remove_story_bible_note(
    troupe_id: uuid.UUID, note_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> StoryBibleOut:
    troupe = bible_troupe(db, user, troupe_id)
    story_bible.remove(db, user, troupe, troupe_note(db, troupe, note_id))
    db.commit()
    return bible_out(db, troupe)


@router.put("/order")
def order_story_bible_notes(
    troupe_id: uuid.UUID, body: StoryBibleOrderIn, db: DbSession, user: CurrentUser
) -> StoryBibleOut:
    """Put the notes in a new order."""
    troupe = bible_troupe(db, user, troupe_id)
    try:
        story_bible.reorder(db, user, troupe, body.ids)
    except BibleError as error:
        raise refused(error) from None
    db.commit()
    return bible_out(db, troupe)
