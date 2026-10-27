"""Shared backgrounds (CONTEXT.md: Shared Background): a Haven, Herd, Allies or
Contacts that characters in a coterie, pack or gang pool together, and its log.

The rules (Vol. 2 Issue 1, p. 88): each sharer puts in dots of their own, the
group's total never goes above 5 however many are put in, any sharer may draw on
it, and a sharer who dies or leaves takes their dots out after a while.

Horatio keeps a record only. The log says who put in or took out how many dots,
and who drew on it, when and for what; the total is worked out from it. Nothing
here changes a rating on anyone's sheet, nor stops a use when the background is
spent.

The troupe's storytellers and assistant storytellers set one up and keep its
log. The players of the characters that have put dots in see it, and log uses
for their own characters while those still have dots in it. Every change goes in
the troupe's audit log, and in the character's own log for an entry naming one.

Entries belong to the shared background, and keep the character's name as it was
when logged; a deleted character's entries keep that name with no character.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.influence_log import in_troupe
from horatio.models import (
    Character,
    SharedBackground,
    SharedBackgroundEntry,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.rules.store import read_troupe_rules
from horatio.sheets import conflict, unprocessable

Kind = str  # "contribution" | "withdrawal" | "use"
KINDS: tuple[Kind, ...] = ("contribution", "withdrawal", "use")
# The backgrounds the book lets a group share (Vol. 2 Issue 1, p. 88).
SHAREABLE = ("Haven", "Herd", "Allies", "Contacts")
# However many dots are put in, the group's background is at most this.
MOST = 5
RULE_PAGE = "Vol. 2 Issue 1, p. 88"


def dots_text(dots: int) -> str:
    return "1 dot" if dots == 1 else f"{dots} dots"


def backgrounds(db: Session, troupe_id: uuid.UUID) -> list[str]:
    """The backgrounds a group in the troupe can share: the book's, as the troupe's
    rules have them. Every splat's backgrounds are the Vampire catalogue's (a
    ghoul's less Generation, which no group shares)."""
    rules = read_troupe_rules(db, "vampire", troupe_id)
    have = {n for (c, n) in rules.rule_set.traits if c == "backgrounds"}
    return [b for b in SHAREABLE if b in have]


# --- who may do what --------------------------------------------------------------------


def can_manage(db: Session, user: User, troupe: Troupe) -> bool:
    if troupe.archived_at is not None and not user.is_custodian:
        return False
    return allows(
        troupe_role(db, user, troupe),
        TroupeAction.MANAGE_SHARED_BACKGROUNDS,
        is_custodian=user.is_custodian,
    )


def entries(db: Session, shared: SharedBackground) -> list[SharedBackgroundEntry]:
    """Its log, newest first."""
    return list(
        db.scalars(
            select(SharedBackgroundEntry)
            .where(SharedBackgroundEntry.background_id == shared.id)
            .order_by(SharedBackgroundEntry.happened_at.desc(), SharedBackgroundEntry.id.desc())
        )
    )


def contributors(db: Session, shared: SharedBackground) -> list[Character]:
    """The characters that have ever put dots in, whether or not they still have."""
    ids = select(SharedBackgroundEntry.character_id).where(
        SharedBackgroundEntry.background_id == shared.id,
        SharedBackgroundEntry.kind == "contribution",
    )
    return list(db.scalars(select(Character).where(Character.id.in_(ids))))


def can_see(db: Session, user: User, shared: SharedBackground) -> bool:
    """Its troupe's staff, and the players of the characters that have put dots in."""
    troupe = db.get_one(Troupe, shared.troupe_id)
    if can_manage(db, user, troupe):
        return True
    return any(c.kind == "pc" and c.player_id == user.id for c in contributors(db, shared))


def plays(user: User, character: Character | None) -> bool:
    return character is not None and character.kind == "pc" and character.player_id == user.id


# --- the total --------------------------------------------------------------------------


@dataclass
class Sharer:
    character_id: uuid.UUID | None
    name: str
    # Put in, less taken out.
    dots: int


@dataclass
class Standing:
    # Every character that has put dots in, in the order they first did.
    sharers: list[Sharer] = field(default_factory=list)

    @property
    def put_in(self) -> int:
        return sum(s.dots for s in self.sharers)

    @property
    def total(self) -> int:
        """The group's rating: what is put in, but never more than 5."""
        return min(self.put_in, MOST)

    def dots_of(self, character_id: uuid.UUID) -> int:
        return next((s.dots for s in self.sharers if s.character_id == character_id), 0)


def standing(found: Sequence[SharedBackgroundEntry]) -> Standing:
    """Who has how many dots in it, from its log. A character since deleted counts
    under the name it was logged with."""
    by_who: dict[uuid.UUID | str, Sharer] = {}
    for entry in sorted(found, key=lambda e: (e.happened_at, e.id)):
        if entry.kind == "use" or entry.dots is None:
            continue
        key: uuid.UUID | str = entry.character_id or entry.name
        sharer = by_who.setdefault(key, Sharer(entry.character_id, entry.name, 0))
        sharer.dots += entry.dots if entry.kind == "contribution" else -entry.dots
    return Standing(list(by_who.values()))


# --- setting one up ---------------------------------------------------------------------


@dataclass
class Contribution:
    character_id: uuid.UUID
    dots: int


def checked_name(
    db: Session, troupe_id: uuid.UUID, name: str, keep: SharedBackground | None
) -> str:
    name = " ".join(name.split())
    if not name:
        raise unprocessable("Give the shared background a name.")
    clash = db.scalar(
        select(SharedBackground.id).where(
            SharedBackground.troupe_id == troupe_id, SharedBackground.name == name
        )
    )
    if clash is not None and (keep is None or clash != keep.id):
        raise conflict(f"The troupe already has a shared background called {name}.")
    return name


def checked_background(db: Session, troupe_id: uuid.UUID, background: str) -> str:
    if background not in backgrounds(db, troupe_id):
        raise unprocessable(
            f"A group can share only {', '.join(SHAREABLE[:-1])} or {SHAREABLE[-1]} ({RULE_PAGE})."
        )
    return background


def describe(shared: SharedBackground) -> dict[str, Any]:
    """What the audit log says about it."""
    return {"shared": shared.name, "shared_id": str(shared.id), "background": shared.background}


def create(
    db: Session,
    actor: User,
    troupe: Troupe,
    *,
    name: str,
    background: str,
    notes: str,
    contributions: Sequence[Contribution],
    happened_at: datetime,
) -> SharedBackground:
    """Set up a shared background, with the dots each sharer puts in."""
    if not contributions:
        raise unprocessable("Choose at least one character sharing it.")
    if len({c.character_id for c in contributions}) != len(contributions):
        raise unprocessable("Each character is listed once.")
    shared = SharedBackground(
        troupe_id=troupe.id,
        name=checked_name(db, troupe.id, name, None),
        background=checked_background(db, troupe.id, background),
        notes=notes.strip(),
        created_by=actor.id,
    )
    db.add(shared)
    db.flush()
    audit.record(db, actor, "shared_background.created", troupe_id=troupe.id, **describe(shared))
    for contribution in contributions:
        log(
            db,
            actor,
            shared,
            Details(
                kind="contribution",
                character_id=contribution.character_id,
                happened_at=happened_at,
                dots=contribution.dots,
            ),
        )
    return shared


def change(
    db: Session,
    actor: User,
    shared: SharedBackground,
    *,
    name: str | None = None,
    background: str | None = None,
    notes: str | None = None,
) -> list[str]:
    """Rename it, or change which background it is or what it gives. Returns the
    names of what changed."""
    changed: list[str] = []
    was = shared.name
    if name is not None and (name := checked_name(db, shared.troupe_id, name, shared)) != was:
        shared.name = name
        changed.append("name")
    if background is not None and background != shared.background:
        shared.background = checked_background(db, shared.troupe_id, background)
        changed.append("background")
    if notes is not None and notes.strip() != shared.notes:
        shared.notes = notes.strip()
        changed.append("what it gives")
    db.flush()
    if changed:
        audit.record(
            db,
            actor,
            "shared_background.changed",
            troupe_id=shared.troupe_id,
            was=was,
            fields=", ".join(changed),
            **describe(shared),
        )
    return changed


def remove(db: Session, actor: User, shared: SharedBackground) -> None:
    """Delete it and its log."""
    data = describe(shared)
    db.execute(
        delete(SharedBackgroundEntry).where(SharedBackgroundEntry.background_id == shared.id)
    )
    db.delete(shared)
    db.flush()
    audit.record(db, actor, "shared_background.deleted", troupe_id=shared.troupe_id, **data)


# --- its log ----------------------------------------------------------------------------


@dataclass
class Details:
    kind: Kind
    character_id: uuid.UUID
    happened_at: datetime
    dots: int | None = None
    purpose: str = ""
    note: str = ""


def may_log(db: Session, user: User, shared: SharedBackground, details: Details) -> bool:
    """Staff log anything; a player logs a use for their own character."""
    troupe = db.get_one(Troupe, shared.troupe_id)
    if can_manage(db, user, troupe):
        return True
    return (
        troupe.archived_at is None
        and details.kind == "use"
        and plays(user, db.get(Character, details.character_id))
    )


def log(
    db: Session, actor: User, shared: SharedBackground, details: Details
) -> SharedBackgroundEntry:
    """Add a line to its log, checked against what is in it so far: dots are taken
    out only from what the character put in, and only a character with dots in it
    draws on it."""
    if details.kind not in KINDS:
        raise unprocessable("An entry puts dots in, takes them out, or uses it.")
    if details.happened_at.tzinfo is None:
        raise unprocessable("Say when it happened with its time zone.")
    if details.kind == "use":
        dots = None
    elif details.dots is None or details.dots < 1:
        raise unprocessable("Say how many dots, at least 1.")
    else:
        dots = details.dots
    character = db.get(Character, details.character_id)
    if character is None:
        raise unprocessable("No such character.")
    held = standing(entries(db, shared)).dots_of(character.id)
    if details.kind == "contribution" and not in_troupe(db, shared.troupe_id, character):
        raise unprocessable("That character is not in this troupe.")
    if details.kind == "withdrawal" and (dots or 0) > held:
        raise unprocessable(f"{character.name} has only {dots_text(held)} in it to take out.")
    if details.kind == "use" and held < 1:
        raise unprocessable(f"{character.name} has no dots in {shared.name}, so cannot draw on it.")
    entry = SharedBackgroundEntry(
        background_id=shared.id,
        kind=details.kind,
        happened_at=details.happened_at,
        character_id=character.id,
        name=character.name,
        dots=dots,
        purpose=details.purpose.strip(),
        note=details.note.strip(),
        logged_by=actor.id,
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        actor,
        "shared_background.logged",
        troupe_id=shared.troupe_id,
        character_id=character.id,
        **entry_data(shared, entry),
    )
    return entry


def entry_data(shared: SharedBackground, entry: SharedBackgroundEntry) -> dict[str, Any]:
    """What the audit log says about an entry; `kind` picks its sentence."""
    return {
        **describe(shared),
        "kind": entry.kind,
        "entry_id": str(entry.id),
        "dots": dots_text(entry.dots) if entry.dots else "",
        "purpose": entry.purpose,
    }


def may_unlog(db: Session, user: User, entry: SharedBackgroundEntry) -> bool:
    """Staff take any entry off; whoever logged a use can take it back."""
    shared = db.get_one(SharedBackground, entry.background_id)
    troupe = db.get_one(Troupe, shared.troupe_id)
    if can_manage(db, user, troupe):
        return True
    return troupe.archived_at is None and entry.kind == "use" and entry.logged_by == user.id


def unlog(db: Session, actor: User, entry: SharedBackgroundEntry) -> None:
    """Take an entry off its log. Taking off dots put in is refused while that would
    leave the character with fewer than none."""
    shared = db.get_one(SharedBackground, entry.background_id)
    if entry.kind == "contribution" and entry.character_id is not None:
        rest = [e for e in entries(db, shared) if e.id != entry.id]
        if standing(rest).dots_of(entry.character_id) < 0:
            raise conflict(f"{entry.name} has taken those dots out since; delete that entry first.")
    data = entry_data(shared, entry)
    db.delete(entry)
    db.flush()
    audit.record(
        db,
        actor,
        "shared_background.unlogged",
        troupe_id=shared.troupe_id,
        character_id=entry.character_id,
        character_name=entry.name,
        **data,
    )


# --- reading ----------------------------------------------------------------------------


def of_troupe(db: Session, troupe_id: uuid.UUID) -> list[SharedBackground]:
    return list(
        db.scalars(
            select(SharedBackground)
            .where(SharedBackground.troupe_id == troupe_id)
            .order_by(SharedBackground.name)
        )
    )


def of_character(db: Session, character_id: uuid.UUID) -> list[SharedBackground]:
    """Those the character has ever put dots in, in any troupe."""
    ids = select(SharedBackgroundEntry.background_id).where(
        SharedBackgroundEntry.character_id == character_id,
        SharedBackgroundEntry.kind == "contribution",
    )
    return list(
        db.scalars(
            select(SharedBackground)
            .where(SharedBackground.id.in_(ids))
            .order_by(SharedBackground.name)
        )
    )
