"""Titles: positions characters hold in one troupe (CONTEXT.md: Title).

A troupe's titles are its rule sets' list plus any it added. Its storytellers
and assistant storytellers give them to characters in the troupe; a title
means nothing elsewhere, and goes when the character leaves.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, CharacterTitle, RuleSet, Troupe, TroupeTitle, User
from horatio.sheets import conflict, membership, unprocessable


def catalogue_titles(db: Session) -> list[str]:
    titles: set[str] = set()
    for listed in db.scalars(select(RuleSet.titles)):
        titles.update(listed)
    return sorted(titles)


def troupe_titles(db: Session, troupe_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(TroupeTitle.name)
            .where(TroupeTitle.troupe_id == troupe_id)
            .order_by(TroupeTitle.name)
        )
    )


def available(db: Session, troupe_id: uuid.UUID) -> set[str]:
    return set(catalogue_titles(db)) | set(troupe_titles(db, troupe_id))


def add_title(db: Session, staff: User, troupe: Troupe, name: str) -> None:
    name = name.strip()
    if not name:
        raise unprocessable("A title needs a name.")
    if name in available(db, troupe.id):
        raise conflict(f"{name} is already a title here.")
    db.add(TroupeTitle(troupe_id=troupe.id, name=name))
    db.flush()
    audit.record(db, staff, "title.added", troupe_id=troupe.id, title=name)


def remove_title(db: Session, staff: User, troupe: Troupe, name: str) -> None:
    """Remove a title the troupe added, taking it from anyone who holds it."""
    found = db.scalar(
        select(TroupeTitle).where(TroupeTitle.troupe_id == troupe.id, TroupeTitle.name == name)
    )
    if found is None:
        raise conflict("Only titles this troupe added can be removed.")
    db.execute(
        delete(CharacterTitle).where(
            CharacterTitle.troupe_id == troupe.id, CharacterTitle.name == name
        )
    )
    db.delete(found)
    db.flush()
    audit.record(db, staff, "title.removed_from_troupe", troupe_id=troupe.id, title=name)


def held(db: Session, troupe_id: uuid.UUID, character_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(CharacterTitle.name)
            .where(
                CharacterTitle.troupe_id == troupe_id, CharacterTitle.character_id == character_id
            )
            .order_by(CharacterTitle.name)
        )
    )


def set_titles(
    db: Session, staff: User, troupe: Troupe, character: Character, names: Sequence[str]
) -> list[str]:
    """Give `character` exactly these titles in `troupe`."""
    if membership(db, character, troupe.id) is None:
        raise conflict("Titles are only for characters in this troupe.")
    unknown = set(names) - available(db, troupe.id)
    if unknown:
        raise unprocessable(
            f"Not a title here: {', '.join(sorted(unknown))}. Add it to the troupe first."
        )
    before = set(held(db, troupe.id, character.id))
    after = set(names)
    for name in before - after:
        db.execute(
            delete(CharacterTitle).where(
                CharacterTitle.troupe_id == troupe.id,
                CharacterTitle.character_id == character.id,
                CharacterTitle.name == name,
            )
        )
        audit.record(
            db, staff, "title.taken", troupe_id=troupe.id, character_id=character.id, title=name
        )
    for name in after - before:
        db.add(CharacterTitle(troupe_id=troupe.id, character_id=character.id, name=name))
        audit.record(
            db, staff, "title.given", troupe_id=troupe.id, character_id=character.id, title=name
        )
    db.flush()
    return sorted(after)


def drop_all(db: Session, troupe_id: uuid.UUID, character_id: uuid.UUID) -> None:
    """A character leaving a troupe leaves its titles there."""
    db.execute(
        delete(CharacterTitle).where(
            CharacterTitle.troupe_id == troupe_id, CharacterTitle.character_id == character_id
        )
    )
