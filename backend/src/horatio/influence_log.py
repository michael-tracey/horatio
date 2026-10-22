"""The troupe's influence log (CONTEXT.md: Influence Log): every influence action
taken in a troupe, whoever took it and however it reached Horatio.

Each entry is one action, or the same action taken several times for one purpose
(`times`), by a character of the troupe or someone named only in words. It says
when it happened, to the minute, since lookups count back from it (#130), and
where it came from:

- **downtime:** staff log a player's influence answer from the response editor.
  The purpose starts as the answer for staff to trim. A second answer in the same
  cycle with the same action, specialisation and purpose adds to the first
  entry's times instead of making another;
- **game:** spending influence on the Play View (#133), linked to the tap;
- **hand:** storytellers and assistant storytellers add it themselves;
- **import:** brought in from the old spreadsheet (#132), keeping the sheet's id
  as its `reference`, unique in the troupe, so an import can run again.

Each entry has a short id, E12 or UW7: its type's letters and a number counted
up in the troupe for that type. Storytellers and assistant storytellers keep the
log; players never see it, only their own characters' entries (#135). Every
change goes in the troupe's audit log, without the character, since a
character's own log is its player's to read.

Entries belong to the troupe: they happened in its game world. A character
leaving the troupe, changing home troupe or retiring takes nothing out of the
log, and nothing here filters by who is in the troupe now. Each entry keeps the
character's name as it was logged; a deleted character's entries keep that name
with no character.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from horatio import audit, influence
from horatio.influence import InfluenceType
from horatio.models import (
    Character,
    InfluenceBlock,
    InfluenceEntry,
    Response,
    Submission,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.responses import WorkItem
from horatio.rules.model import TroupeRules
from horatio.rules.store import read_troupe_rules
from horatio.sheets import conflict, unprocessable

Source = str  # "downtime" | "game" | "hand" | "import"
SOURCES: tuple[Source, ...] = ("downtime", "game", "hand", "import")
PREFIXES: dict[InfluenceType, str] = {"elite": "E", "underworld": "UW"}
SHORT_ID = re.compile(r"^\s*(E|UW)\s*(\d+)\s*$", re.IGNORECASE)


def short_id(entry: InfluenceEntry) -> str:
    """How staff and players refer to it: E12, UW7."""
    return f"{PREFIXES[entry.type]}{entry.number}"  # type: ignore[index]  # checked by the database


def parse_short_id(text: str) -> tuple[InfluenceType, int] | None:
    """The type and number in "E334" or "uw 259", or None."""
    found = SHORT_ID.match(text)
    if found is None:
        return None
    return ("elite" if found[1].upper() == "E" else "underworld"), int(found[2])


def by_short_id(db: Session, troupe_id: uuid.UUID, text: str) -> InfluenceEntry | None:
    parsed = parse_short_id(text)
    if parsed is None:
        return None
    return db.scalar(
        select(InfluenceEntry).where(
            InfluenceEntry.troupe_id == troupe_id,
            InfluenceEntry.type == parsed[0],
            InfluenceEntry.number == parsed[1],
        )
    )


def troupe_rules(db: Session, troupe_id: uuid.UUID) -> TroupeRules:
    """The rules the troupe's influence actions come from. Influence is a Vampire
    rule, as the rest of Horatio's troupe rules are today."""
    return read_troupe_rules(db, "vampire", troupe_id)


def action_label(rules: TroupeRules, entry: InfluenceEntry) -> str:
    if entry.action_key is None:
        return "No action yet"
    return influence.label(rules, entry.type, entry.action_key)  # type: ignore[arg-type]


def next_number(db: Session, troupe_id: uuid.UUID, influence_type: InfluenceType) -> int:
    """The next free number for the type's short ids. Holds the troupe's row until the
    transaction ends, so two entries made at once do not take the same one."""
    db.execute(select(Troupe.id).where(Troupe.id == troupe_id).with_for_update())
    highest = db.scalar(
        select(func.max(InfluenceEntry.number)).where(
            InfluenceEntry.troupe_id == troupe_id, InfluenceEntry.type == influence_type
        )
    )
    return (highest or 0) + 1


def number_free(
    db: Session, troupe_id: uuid.UUID, influence_type: InfluenceType, number: int
) -> bool:
    return (
        db.scalar(
            select(InfluenceEntry.id).where(
                InfluenceEntry.troupe_id == troupe_id,
                InfluenceEntry.type == influence_type,
                InfluenceEntry.number == number,
            )
        )
        is None
    )


def in_troupe(db: Session, troupe_id: uuid.UUID, character: Character) -> bool:
    """A character in the troupe now: a member, or an NPC it keeps."""
    if character.owner_troupe_id == troupe_id:
        return True
    return (
        db.scalar(
            select(TroupeMembership.id).where(
                TroupeMembership.troupe_id == troupe_id,
                TroupeMembership.character_id == character.id,
                TroupeMembership.left_at.is_(None),
            )
        )
        is not None
    )


@dataclass
class Details:
    """What an entry says, as staff give it."""

    influence_type: InfluenceType
    happened_at: datetime
    # A character of the troupe, or None and a name for someone not in Horatio.
    character_id: uuid.UUID | None
    name: str = ""
    specialization: str = ""
    action_key: str | None = None
    purpose: str = ""
    times: int = 1
    blocks: int = 0
    needs_details: bool = False
    cycle_id: uuid.UUID | None = None


def checked(
    db: Session, troupe_id: uuid.UUID, details: Details, *, keep: InfluenceEntry | None = None
) -> Details:
    """The details cleaned up and checked: the action is one of the type's in the
    troupe's rules, and the character is in the troupe (unless it is the one the
    entry already names, which may have left since). The entry keeps a character's
    name as it was when logged."""
    if details.influence_type not in influence.TYPES:
        raise unprocessable("Influence is Elite or Underworld.")
    if details.happened_at.tzinfo is None:
        raise unprocessable("Say when it happened with its time zone.")
    if details.times < 1 or details.blocks < 0:
        raise unprocessable("Times taken is at least 1, and blocks at least 0.")
    action_key = details.action_key or None
    if action_key is None and not details.needs_details:
        raise unprocessable("Choose the action, or mark the entry as needing details.")
    if action_key is not None:
        rules = troupe_rules(db, troupe_id)
        found = influence.find(rules, details.influence_type, action_key)
        unchanged = keep is not None and (keep.type, keep.action_key) == (
            details.influence_type,
            action_key,
        )
        if found is None and not unchanged:
            type_name = influence.TYPE_NAMES[details.influence_type]
            raise unprocessable(f"Choose one of the {type_name} actions.")
    name = details.name.strip()
    if details.character_id is not None:
        character = db.get(Character, details.character_id)
        if keep is not None and keep.character_id == details.character_id:
            # Its name as it was logged stays, whatever it is called now.
            name = keep.name
        elif character is None or not in_troupe(db, troupe_id, character):
            raise unprocessable("That character is not in this troupe.")
        else:
            name = character.name
    elif not name:
        raise unprocessable("Choose a character, or name someone not in Horatio.")
    return replace(
        details,
        name=name,
        specialization=details.specialization.strip(),
        action_key=action_key,
        purpose=details.purpose.strip(),
    )


def describe(rules: TroupeRules, entry: InfluenceEntry) -> dict[str, Any]:
    """What the audit log says about an entry."""
    return {
        "entry": short_id(entry),
        "entry_id": str(entry.id),
        "who": entry.name,
        "what": action_label(rules, entry),
    }


def add_entry(
    db: Session,
    actor: User | None,
    troupe: Troupe,
    details: Details,
    *,
    source: Source,
    play_event_id: uuid.UUID | None = None,
    reference: str | None = None,
    number: int | None = None,
) -> InfluenceEntry:
    """Log an action. `number` asks for a short id's number, such as an imported
    row's own; it is used when free, else the next one is."""
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    details = checked(db, troupe.id, details)
    if reference is not None and (
        db.scalar(
            select(InfluenceEntry.id).where(
                InfluenceEntry.troupe_id == troupe.id, InfluenceEntry.reference == reference
            )
        )
        is not None
    ):
        raise conflict(f"The log already has an entry for {reference}.")
    if (
        number is None
        or number < 1
        or not number_free(db, troupe.id, details.influence_type, number)
    ):
        number = next_number(db, troupe.id, details.influence_type)
    entry = InfluenceEntry(
        troupe_id=troupe.id,
        type=details.influence_type,
        number=number,
        happened_at=details.happened_at,
        character_id=details.character_id,
        name=details.name,
        specialization=details.specialization,
        action_key=details.action_key,
        purpose=details.purpose,
        times=details.times,
        blocks=details.blocks,
        source=source,
        cycle_id=details.cycle_id,
        play_event_id=play_event_id,
        reference=reference,
        needs_details=details.needs_details,
        logged_by=actor.id if actor else None,
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        actor,
        "influence.logged",
        troupe_id=troupe.id,
        source=source,
        **describe(troupe_rules(db, troupe.id), entry),
    )
    return entry


EDITABLE = (
    "happened_at",
    "character_id",
    "name",
    "specialization",
    "action_key",
    "purpose",
    "times",
    "blocks",
    "needs_details",
    "cycle_id",
)


def change_entry(
    db: Session, actor: User | None, entry: InfluenceEntry, details: Details
) -> list[str]:
    """Change what an entry says. A change of type gives it the other type's next
    number. Returns the names of the fields that changed."""
    details = checked(db, entry.troupe_id, details, keep=entry)
    changed = [f for f in EDITABLE if getattr(entry, f) != getattr(details, f)]
    was = short_id(entry)
    if details.influence_type != entry.type:
        changed.insert(0, "type")
        number = next_number(db, entry.troupe_id, details.influence_type)
        entry.type, entry.number = details.influence_type, number
    for name in EDITABLE:
        setattr(entry, name, getattr(details, name))
    db.flush()
    if changed:
        audit.record(
            db,
            actor,
            "influence.changed",
            troupe_id=entry.troupe_id,
            was=was,
            fields=", ".join(f.replace("_", " ") for f in changed),
            **describe(troupe_rules(db, entry.troupe_id), entry),
        )
    return changed


def unlink_responses(db: Session, entry_ids: Sequence[uuid.UUID]) -> None:
    db.execute(
        update(Response)
        .where(Response.influence_entry_id.in_(entry_ids))
        .values(influence_entry_id=None)
        .execution_options(synchronize_session="fetch")
    )


def delete_entry(db: Session, actor: User, entry: InfluenceEntry) -> None:
    """Take an entry off the log. Answers logged in it can be logged again."""
    data = describe(troupe_rules(db, entry.troupe_id), entry)
    unlink_responses(db, [entry.id])
    db.delete(entry)
    db.flush()
    audit.record(db, actor, "influence.deleted", troupe_id=entry.troupe_id, **data)


def merge_entries(
    db: Session, actor: User, keep: InfluenceEntry, others: Sequence[InfluenceEntry]
) -> InfluenceEntry:
    """Merge repeats into one entry: the same type, character and action. Their
    times add up, it keeps the most blocks any of them had, and answers logged in
    them move to it. It keeps its own date, specialisation and purpose."""
    others = [o for o in others if o.id != keep.id]
    if not others:
        raise unprocessable("Choose at least two entries to merge.")
    for other in others:
        if other.troupe_id != keep.troupe_id:
            raise unprocessable("Those entries are in different troupes.")
        same_who = (other.character_id, other.name if other.character_id is None else None) == (
            keep.character_id,
            keep.name if keep.character_id is None else None,
        )
        if other.type != keep.type or other.action_key != keep.action_key or not same_who:
            raise unprocessable("Only repeats merge: the same type, character and action.")
    merged = [short_id(o) for o in others]
    keep.times += sum(o.times for o in others)
    keep.blocks = max([keep.blocks, *(o.blocks for o in others)])
    db.execute(
        update(Response)
        .where(Response.influence_entry_id.in_([o.id for o in others]))
        .values(influence_entry_id=keep.id)
        .execution_options(synchronize_session="fetch")
    )
    # So do the discovery blocks answers added to them (horatio.influence_lookups).
    db.execute(
        update(InfluenceBlock)
        .where(InfluenceBlock.entry_id.in_([o.id for o in others]))
        .values(entry_id=keep.id)
        .execution_options(synchronize_session="fetch")
    )
    for other in others:
        db.delete(other)
    db.flush()
    audit.record(
        db,
        actor,
        "influence.merged",
        troupe_id=keep.troupe_id,
        merged=", ".join(merged),
        times=keep.times,
        **describe(troupe_rules(db, keep.troupe_id), keep),
    )
    return keep


# --- logging downtime answers -----------------------------------------------------------


def same_purpose(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def logged_entry(db: Session, response: Response) -> InfluenceEntry | None:
    if response.influence_entry_id is None:
        return None
    return db.get(InfluenceEntry, response.influence_entry_id)


def log_answer(
    db: Session, actor: User, item: WorkItem, troupe: Troupe, purpose: str
) -> tuple[InfluenceEntry, bool]:
    """Log an influence answer, with the purpose staff trimmed it to. A repeat in
    the same cycle (same character, action, specialisation and purpose) adds to the
    entry already logged. Returns the entry, and whether it was a repeat."""
    if item.response.influence_entry_id is not None:
        raise conflict("That answer is logged already.")
    influence_type = influence.type_of(item.question.action_kind)
    if influence_type is None:
        raise unprocessable("Only influence answers go in the influence log.")
    rules = troupe_rules(db, troupe.id)
    action = influence.answer_action(rules, influence_type, item.answer.structured)
    if action is None:
        raise unprocessable("The answer names no action; add it to the log by hand.")
    specialization = item.answer.structured.get("specialization")
    specialization = specialization.strip() if isinstance(specialization, str) else ""
    purpose = purpose.strip()
    repeats = db.scalars(
        select(InfluenceEntry).where(
            InfluenceEntry.troupe_id == troupe.id,
            InfluenceEntry.source == "downtime",
            InfluenceEntry.cycle_id == item.cycle.id,
            InfluenceEntry.character_id == item.character.id,
            InfluenceEntry.type == influence_type,
            InfluenceEntry.action_key == action.key,
            InfluenceEntry.specialization == specialization,
        )
    )
    repeat = next((e for e in repeats if same_purpose(e.purpose, purpose)), None)
    if repeat is not None:
        repeat.times += 1
        item.response.influence_entry_id = repeat.id
        db.flush()
        audit.record(
            db,
            actor,
            "influence.repeated",
            troupe_id=troupe.id,
            times=repeat.times,
            **describe(rules, repeat),
        )
        return repeat, True
    submission = db.get_one(Submission, item.answer.submission_id)
    entry = add_entry(
        db,
        actor,
        troupe,
        Details(
            influence_type=influence_type,
            happened_at=submission.submitted_at or item.answer.created_at,
            character_id=item.character.id,
            specialization=specialization,
            action_key=action.key,
            purpose=purpose,
            cycle_id=item.cycle.id,
        ),
        source="downtime",
    )
    item.response.influence_entry_id = entry.id
    db.flush()
    return entry, False


def unlog_answer(db: Session, actor: User, item: WorkItem) -> None:
    """Take an answer back off the log: one fewer time taken, or the entry gone
    when it was the only one."""
    entry = logged_entry(db, item.response)
    if entry is None:
        raise conflict("That answer is not logged.")
    item.response.influence_entry_id = None
    if entry.times > 1:
        entry.times -= 1
        db.flush()
        audit.record(
            db,
            actor,
            "influence.unrepeated",
            troupe_id=entry.troupe_id,
            times=entry.times,
            **describe(troupe_rules(db, entry.troupe_id), entry),
        )
    else:
        delete_entry(db, actor, entry)


# --- reading the log --------------------------------------------------------------------


@dataclass
class Filters:
    influence_type: InfluenceType | None = None
    specialization: str | None = None
    character_id: uuid.UUID | None = None
    # Someone not in Horatio, by the name the entry keeps.
    name: str | None = None
    action_key: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    needs_details: bool | None = None
    source: Source | None = None


def entries_query(troupe_id: uuid.UUID, filters: Filters | None = None) -> Select[InfluenceEntry]:
    """The troupe's entries that pass the filters, newest first. `since` is
    inclusive and `until` exclusive."""
    f = filters or Filters()
    query = select(InfluenceEntry).where(InfluenceEntry.troupe_id == troupe_id)
    if f.influence_type is not None:
        query = query.where(InfluenceEntry.type == f.influence_type)
    if f.specialization:
        query = query.where(InfluenceEntry.specialization == f.specialization)
    if f.character_id is not None:
        query = query.where(InfluenceEntry.character_id == f.character_id)
    if f.name:
        query = query.where(
            InfluenceEntry.character_id.is_(None), func.lower(InfluenceEntry.name) == f.name.lower()
        )
    if f.action_key:
        query = query.where(InfluenceEntry.action_key == f.action_key)
    if f.since is not None:
        query = query.where(InfluenceEntry.happened_at >= f.since)
    if f.until is not None:
        query = query.where(InfluenceEntry.happened_at < f.until)
    if f.needs_details is not None:
        query = query.where(InfluenceEntry.needs_details.is_(f.needs_details))
    if f.source is not None:
        query = query.where(InfluenceEntry.source == f.source)
    return query.order_by(
        InfluenceEntry.happened_at.desc(), InfluenceEntry.type, InfluenceEntry.number.desc()
    )


def find_entries(
    db: Session, troupe_id: uuid.UUID, filters: Filters, *, limit: int, offset: int = 0
) -> tuple[list[InfluenceEntry], int]:
    """A page of the troupe's entries, and how many pass the filters in all."""
    query = entries_query(troupe_id, filters)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    return list(db.scalars(query.limit(limit).offset(offset))), total


def character_entries(
    db: Session, character_id: uuid.UUID, troupe_id: uuid.UUID | None = None
) -> list[InfluenceEntry]:
    """A character's own entries, newest first: in one troupe, or in all."""
    query = select(InfluenceEntry).where(InfluenceEntry.character_id == character_id)
    if troupe_id is not None:
        query = query.where(InfluenceEntry.troupe_id == troupe_id)
    return list(db.scalars(query.order_by(InfluenceEntry.happened_at.desc())))


def logged_characters(db: Session, troupe_id: uuid.UUID) -> list[Character]:
    """The characters the troupe's log names, whether or not they are in it now."""
    ids = select(InfluenceEntry.character_id).where(
        InfluenceEntry.troupe_id == troupe_id, InfluenceEntry.character_id.is_not(None)
    )
    return list(db.scalars(select(Character).where(Character.id.in_(ids))))


def names_only(db: Session, troupe_id: uuid.UUID) -> list[str]:
    """The names in the troupe's log of people not in Horatio."""
    return sorted(
        set(
            db.scalars(
                select(InfluenceEntry.name).where(
                    InfluenceEntry.troupe_id == troupe_id, InfluenceEntry.character_id.is_(None)
                )
            )
        ),
        key=str.casefold,
    )


def specializations_used(db: Session, troupe_id: uuid.UUID) -> list[str]:
    return sorted(
        set(
            db.scalars(
                select(InfluenceEntry.specialization).where(
                    InfluenceEntry.troupe_id == troupe_id,
                    InfluenceEntry.specialization != "",
                )
            )
        ),
        key=str.casefold,
    )
