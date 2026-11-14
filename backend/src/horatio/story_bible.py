"""A troupe's story bible (issue #879): the staff-only companion to its Setting Style
Document (MET: VTM ch. 8, p. 336), where the book has a chronicle's storytellers keep
its history, its important characters and its recurring places together.

Most of it is what Horatio already holds, read afresh each time so nothing is typed
twice: the chronicle (horatio.chronicle) is its chronology, the troupe's NPCs its
important characters, and its Stock Locations its recurring locales. Staff's own
notes are the one thing stored here. Its running staff read and keep it; players
never see any of it, and changing it tells nobody.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, Location, StoryBibleNote, Troupe, User


class BibleError(ValueError):
    """Something staff asked for that the story bible can't hold."""


@dataclass(frozen=True)
class Words:
    """A note as staff write it, trimmed."""

    title: str
    body: str


def notes(db: Session, troupe_id: uuid.UUID) -> list[StoryBibleNote]:
    """The troupe's notes, in the order staff put them."""
    return list(
        db.scalars(
            select(StoryBibleNote)
            .where(StoryBibleNote.troupe_id == troupe_id)
            .order_by(StoryBibleNote.position, StoryBibleNote.id)
        )
    )


def check_words(words: Words) -> None:
    if not words.title:
        raise BibleError("Give the note a title.")


def add(db: Session, user: User, troupe: Troupe, words: Words) -> StoryBibleNote:
    """Add a note, last in the bible."""
    check_words(words)
    last = db.scalar(
        select(func.max(StoryBibleNote.position)).where(StoryBibleNote.troupe_id == troupe.id)
    )
    note = StoryBibleNote(
        troupe_id=troupe.id, title=words.title, body=words.body, position=(last or 0) + 1
    )
    db.add(note)
    db.flush()
    audit.record(db, user, "troupe.story_bible_added", troupe_id=troupe.id, title=note.title)
    return note


def change(db: Session, user: User, troupe: Troupe, note: StoryBibleNote, words: Words) -> None:
    check_words(words)
    if (note.title, note.body) == (words.title, words.body):
        return
    note.title = words.title
    note.body = words.body
    db.flush()
    audit.record(db, user, "troupe.story_bible_changed", troupe_id=troupe.id, title=note.title)


def reorder(db: Session, user: User, troupe: Troupe, ids: Sequence[uuid.UUID]) -> None:
    """Put the notes in the order given, which must name each once."""
    found = notes(db, troupe.id)
    by_id = {n.id: n for n in found}
    if len(ids) != len(found) or set(ids) != set(by_id):
        raise BibleError("Give every note once, in its new order.")
    if [n.id for n in found] == list(ids):
        return
    for place, note_id in enumerate(ids, start=1):
        by_id[note_id].position = place
    db.flush()
    audit.record(
        db,
        user,
        "troupe.story_bible_ordered",
        troupe_id=troupe.id,
        titles=", ".join(by_id[i].title for i in ids),
    )


def remove(db: Session, user: User, troupe: Troupe, note: StoryBibleNote) -> None:
    db.delete(note)
    db.flush()
    audit.record(db, user, "troupe.story_bible_removed", troupe_id=troupe.id, title=note.title)


def npcs(db: Session, troupe: Troupe) -> list[Character]:
    """The troupe's NPCs, its important characters: those in play first, then those
    retired, each by name."""
    return list(
        db.scalars(
            select(Character)
            .where(Character.kind == "npc", Character.owner_troupe_id == troupe.id)
            .order_by(Character.status, func.lower(Character.name), Character.id)
        )
    )


def locales(db: Session, troupe: Troupe) -> list[Location]:
    """The troupe's Stock Locations, its recurring locales, by name. Havens are its
    characters' homes rather than places of the chronicle, and are left out."""
    return list(
        db.scalars(
            select(Location)
            .where(Location.troupe_id == troupe.id, Location.kind != "haven")
            .order_by(func.lower(Location.name), Location.id)
        )
    )
