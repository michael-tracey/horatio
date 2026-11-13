"""A troupe's chronicle (issue #711): its history in one timeline, gathered from what
Horatio records with dates. Nothing is stored here: every event is read from its own
record each time.

**The events:**

- an **Embrace** run in play (horatio.embrace), or a ghoul who **died** in one;
- a **diablerie** staff recorded (horatio.diablerie);
- a character **retired**: at Final Death, or leaving for another reason
  (horatio.leaving), when the troupe's log has it;
- a character **joining** the troupe, home or visiting, and **leaving** it;
- **status** given in the troupe (horatio.sect_status);
- each **holding of a title**, from when it began to when it ended
  (horatio.title_history), a span rather than a moment.

**Dates.** Each event has the real moment Horatio recorded it, and, where its record
keeps one, the in-game date: the night of an Embrace or a diablerie, the day status
was given, a title's in-game dates where staff gave them. Joining, leaving and
retiring have no in-game date.

**Who sees what.** The troupe's running staff see every event. Where the troupe lets
them (Troupe.chronicle_players), its members see only what the troupe already shows
them: titles, as the court over time does; characters on the Who's Who joining it;
and the departures the Who's Who lists under "No longer with us", with why
(horatio.whos_who). Embraces, diablerie and status stay staff's.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import leaving, social_age, title_history, whos_who
from horatio.models import (
    AuditEvent,
    Boonbreaker,
    Character,
    CharacterTitle,
    Diablerie,
    Embrace,
    HeldStatus,
    Troupe,
    TroupeMembership,
)

Kind = Literal["title", "status", "embrace", "diablerie", "death", "arrival", "departure"]


@dataclass
class Event:
    # Stable across reads: the kind and the record it came from.
    key: str
    kind: Kind
    character_id: uuid.UUID | None
    character_name: str
    # What happened, short: "Prince", "Embraced", "Final Death".
    label: str
    # More about it, for staff, or for players only what is public.
    detail: str
    # When Horatio recorded it; a title's holding ends at `ends_at`, or is held still.
    at: datetime
    # The record's id: rows written in one transaction share `at`, and ids (UUID v7)
    # rise as rows are made, so it keeps them in the order they were recorded (#733).
    record_id: uuid.UUID
    # The in-game date, where its record keeps one.
    on: date | None = None
    ends_at: datetime | None = None
    ends_on: date | None = None
    # A span that hasn't ended: a title held still.
    ongoing: bool = False
    # What the troupe's players may see, where it lets them.
    public: bool = False
    clan: str | None = field(default=None)
    # An NPC's arrival, which players read only as joining.
    npc: bool = False


def name_of(character: Character | None, fallback: str = "Someone deleted") -> str:
    return character.name if character else fallback


def embraces(db: Session, troupe: Troupe, people: dict[uuid.UUID, Character]) -> list[Event]:
    found = db.scalars(select(Embrace).where(Embrace.troupe_id == troupe.id))
    events = []
    for e in found:
        character = people.get(e.character_id)
        sire = e.sire_name or (name_of(people.get(e.sire_id), "") if e.sire_id else "")
        by = f"by {sire}" + (f" ({e.sire_clan})" if e.sire_clan else "") if sire else ""
        died = e.result == "died"
        events.append(
            Event(
                key=f"embrace:{e.id}",
                record_id=e.id,
                kind="embrace",
                character_id=e.character_id,
                character_name=name_of(character),
                label="Died in the Embrace" if died else "Embraced",
                detail=(f"Attempted {by}" if died and by else by[:1].upper() + by[1:])
                + _note(e.note),
                at=e.created_at,
                on=e.embraced_on,
            )
        )
    return events


def diableries(db: Session, troupe: Troupe, people: dict[uuid.UUID, Character]) -> list[Event]:
    found = db.scalars(
        select(Diablerie).where(
            Diablerie.troupe_id == troupe.id, Diablerie.recorded_at.is_not(None)
        )
    )
    return [
        Event(
            key=f"diablerie:{d.id}",
            record_id=d.id,
            kind="diablerie",
            character_id=d.character_id,
            character_name=name_of(people.get(d.character_id)),
            label="Diablerie",
            detail=(f"Of {d.victim}" if d.victim else "") + _note(d.note),
            at=d.recorded_at or d.created_at,
            on=d.committed_on,
        )
        for d in found
    ]


def _note(note: str) -> str:
    note = note.strip()
    return f". {note}" if note else ""


def status_given(db: Session, troupe: Troupe, people: dict[uuid.UUID, Character]) -> list[Event]:
    found = db.scalars(select(HeldStatus).where(HeldStatus.troupe_id == troupe.id))
    # The Disgraced a Boonbreaker holds (horatio.boonbreakers, #717) names the
    # declaration as its patron, in words of its own.
    marked = set(
        db.scalars(
            select(Boonbreaker.held_status_id).where(
                Boonbreaker.troupe_id == troupe.id, Boonbreaker.held_status_id.is_not(None)
            )
        )
    )
    events = []
    for s in found:
        patron = s.patron_name or s.patron_text
        given = patron if s.id in marked else f"From {patron}" if patron else ""
        parts = [given, s.story.strip()]
        events.append(
            Event(
                key=f"status:{s.id}",
                record_id=s.id,
                kind="status",
                character_id=s.character_id,
                character_name=name_of(people.get(s.character_id)),
                label=s.name,
                detail=". ".join(p for p in parts if p),
                at=s.created_at,
                on=s.given_on,
            )
        )
    return events


def holdings(db: Session, troupe: Troupe) -> list[Event]:
    return [
        Event(
            key=f"title:{h.id}",
            record_id=h.id,
            kind="title",
            character_id=h.character_id,
            character_name=h.character_name,
            label=h.name,
            detail="",
            at=h.began_at,
            on=h.began_in_game,
            ends_at=h.ended_at,
            ends_on=h.ended_in_game,
            ongoing=h.ended_at is None,
            public=True,
        )
        for h in title_history.holdings(db, troupe)
    ]


def comings_and_goings(
    db: Session,
    troupe: Troupe,
    people: dict[uuid.UUID, Character],
    listed: set[uuid.UUID],
) -> list[Event]:
    """Each character joining the troupe and leaving it, and those retired while in
    it: at Final Death, or for another reason, when the log kept when."""
    stays = list(
        db.scalars(select(TroupeMembership).where(TroupeMembership.troupe_id == troupe.id))
    )
    # NPCs copied from a retired character (horatio.npc_copies, #764), and whose copy.
    copies = {
        entry.character_id: str(entry.data.get("original", ""))
        for entry in db.scalars(
            select(AuditEvent).where(
                AuditEvent.troupe_id == troupe.id,
                AuditEvent.action == "npc.copied_from_character",
            )
        )
        if entry.character_id is not None
    }
    events: list[Event] = []
    for m in stays:
        character = people.get(m.character_id)
        home = m.approved_version_id is not None
        npc = character is not None and character.kind == "npc"
        joined = "Accepted as home" if home else "Joined as a visitor"
        label = "Added as an NPC" if npc else joined
        original = copies.get(m.character_id)
        events.append(
            Event(
                key=f"joined:{m.id}",
                record_id=m.id,
                kind="arrival",
                character_id=m.character_id,
                character_name=name_of(character),
                label=label,
                detail=f"A copy of {original}, retired" if original else "",
                at=m.joined_at,
                public=m.character_id in listed,
                npc=npc,
            )
        )
        if m.left_at is not None:
            events.append(
                Event(
                    key=f"left:{m.id}",
                    record_id=m.id,
                    kind="departure",
                    character_id=m.character_id,
                    character_name=name_of(character),
                    label="Left the troupe",
                    detail="",
                    at=m.left_at,
                )
            )
    retired = {
        c.id: c for c in people.values() if c.status == "retired" and c.left_reason is not None
    }
    if retired:
        logged = db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.troupe_id == troupe.id,
                AuditEvent.action == "character.retired",
                AuditEvent.character_id.in_(list(retired)),
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        last: dict[uuid.UUID, AuditEvent] = {}
        for entry in logged:
            if entry.character_id is not None:
                last[entry.character_id] = entry
        for character_id, entry in last.items():
            character = retired[character_id]
            death = character.left_reason == "final_death"
            events.append(
                Event(
                    key=f"retired:{entry.id}",
                    record_id=entry.id,
                    kind="death" if death else "departure",
                    character_id=character_id,
                    character_name=character.name,
                    label=leaving.reason_name(character.left_reason) or "Retired",
                    detail="" if death else "Retired",
                    at=entry.created_at,
                    public=character.left_listed and character_id in listed,
                )
            )
    return events


def characters_of(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Character]:
    wanted = list({i for i in ids if i})
    if not wanted:
        return {}
    return {c.id: c for c in db.scalars(select(Character).where(Character.id.in_(wanted)))}


def events(db: Session, troupe: Troupe, *, full: bool) -> list[Event]:
    """The troupe's chronicle, oldest first by the real moment: every event for its
    running staff (`full`), or only the public ones, with what is public of them."""
    stays = db.scalars(
        select(TroupeMembership.character_id).where(TroupeMembership.troupe_id == troupe.id)
    )
    ids: set[uuid.UUID] = set(stays)
    ids |= set(db.scalars(select(Embrace.character_id).where(Embrace.troupe_id == troupe.id)))
    ids |= {
        i for i in db.scalars(select(Embrace.sire_id).where(Embrace.troupe_id == troupe.id)) if i
    }
    ids |= set(
        db.scalars(
            select(Diablerie.character_id).where(
                Diablerie.troupe_id == troupe.id, Diablerie.recorded_at.is_not(None)
            )
        )
    )
    ids |= set(db.scalars(select(HeldStatus.character_id).where(HeldStatus.troupe_id == troupe.id)))
    people = characters_of(db, ids)

    held: dict[uuid.UUID, list[str]] = {}
    for character_id, name in db.execute(
        select(CharacterTitle.character_id, CharacterTitle.name).where(
            CharacterTitle.troupe_id == troupe.id
        )
    ):
        held.setdefault(character_id, []).append(name)
    listed = {c.id for c in whos_who.members(db, troupe, held)}
    listed |= {c.id for c in whos_who.departed(db, troupe)}

    found = holdings(db, troupe) + comings_and_goings(db, troupe, people, listed)
    if full:
        found += embraces(db, troupe, people) + diableries(db, troupe, people)
        found += status_given(db, troupe, people)
    else:
        found = [e for e in found if e.public]
        for e in found:
            # Players learn why a listed character left, as the Who's Who says, and no more.
            e.detail = ""
            # The Who's Who doesn't say which characters are NPCs.
            if e.npc:
                e.label = "Joined the troupe"

    standing = social_age.standings(db, [e.character_id for e in found if e.character_id])
    for e in found:
        known = standing.get(e.character_id) if e.character_id else None
        e.clan = known.clan if known else None
    found.sort(key=lambda e: (e.at, e.record_id))
    return found
