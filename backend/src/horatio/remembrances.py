"""Remembrances (issue #471): when a character leaves play, the troupe's next downtime
asks everyone for a memory of them. Running staff open them for a retired character,
as it retires or later; its player can ask for them as they retire it, for staff to
confirm. The memories are reviewed and published with the cycle's Player Nominations
(horatio.nominations), shuffled within each character and without names, and kept
with the character for good.

An optional troupe setting, off by default (`Troupe.remembrances`), independent of
Player Nominations. While it is off, none can be opened or written and nothing of
them shows, except those already published: they belong to the people remembered,
and stay on the characters' pages and the Who's Who.

Which cycle asks: the one open when they are opened, if it isn't yet past Due;
otherwise the next one to open. Each writer (a character taking part) writes one
memory of each, changeable while their downtime is, until it is published.

Who reads them: the troupe's players (an active character at home there) and staff,
and the remembered character's own player, always.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, downtimes, leaving, nominations, notifications
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    Nomination,
    Remembrance,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.sheets import conflict, unprocessable

# The most a memory may say: as a nomination.
TEXT_MOST = nominations.TEXT_MOST


def on(troupe: Troupe) -> bool:
    return troupe.remembrances


def require_on(troupe: Troupe) -> None:
    if not on(troupe):
        raise conflict("This troupe doesn't use Remembrances.")


def can_open(db: Session, user: User, troupe: Troupe) -> bool:
    """Running staff open remembrances, as they run the troupe's cycles."""
    return troupe.archived_at is None and allows(
        troupe_role(db, user, troupe), TroupeAction.MANAGE_CYCLES, is_custodian=user.is_custodian
    )


def of(db: Session, character: Character) -> Remembrance | None:
    """The character's remembrances in its home troupe, if any were opened or asked."""
    if character.home_troupe_id is None:
        return None
    return db.scalar(
        select(Remembrance).where(
            Remembrance.troupe_id == character.home_troupe_id,
            Remembrance.character_id == character.id,
        )
    )


def asking_cycle(db: Session, troupe: Troupe) -> DowntimeCycle | None:
    """The cycle that would ask for memories now: the open one, if it isn't yet past
    Due. None waits for the next one to open."""
    cycle = db.scalar(
        select(DowntimeCycle).where(
            DowntimeCycle.troupe_id == troupe.id, DowntimeCycle.status == "open"
        )
    )
    return cycle if cycle is not None and not downtimes.past_due(cycle) else None


def home_of(db: Session, character: Character) -> Troupe:
    if character.kind != "pc" or character.home_troupe_id is None:
        raise conflict("Only a player character with a home troupe has remembrances.")
    return db.get_one(Troupe, character.home_troupe_id)


def open_for(db: Session, staff: User, character: Character) -> Remembrance:
    """Open remembrances for a retired character, in its home troupe's cycle that asks
    now or the next to open."""
    troupe = home_of(db, character)
    require_on(troupe)
    if character.status != "retired":
        raise conflict("Remembrances are for a character who has left play.")
    found = of(db, character)
    if found is not None and found.opened_at is not None:
        raise conflict(f"Remembrances for {character.name} are open already.")
    if found is None:
        found = Remembrance(troupe_id=troupe.id, character_id=character.id)
        db.add(found)
    cycle = asking_cycle(db, troupe)
    found.opened_by = staff.id
    found.opened_at = downtimes.now()
    found.cycle_id = cycle.id if cycle else None
    db.flush()
    audit.record(
        db,
        staff,
        "remembrance.opened",
        troupe_id=troupe.id,
        character_id=character.id,
        cycle=cycle.name if cycle else "the next cycle that opens",
    )
    return found


def ask_for(db: Session, player: User, character: Character) -> Remembrance:
    """Its player asks staff to open remembrances, as they retire it. Running staff
    are told, to confirm by opening them."""
    troupe = home_of(db, character)
    require_on(troupe)
    found = of(db, character)
    if found is not None:
        return found
    found = Remembrance(
        troupe_id=troupe.id,
        character_id=character.id,
        asked_by=player.id,
        asked_at=downtimes.now(),
    )
    db.add(found)
    db.flush()
    audit.record(db, player, "remembrance.asked", troupe_id=troupe.id, character_id=character.id)
    notifications.notify(
        db,
        notifications.staff_for(db, troupe, TroupeAction.MANAGE_CYCLES),
        "remembrance.asked",
        f"{character.name}'s player asks for remembrances of {character.name}",
        f"/characters/{character.id}",
        troupe_id=troupe.id,
        character_id=character.id,
    )
    return found


def asked_in(db: Session, cycle: DowntimeCycle, troupe: Troupe) -> None:
    """As a cycle opens, it asks for the remembrances waiting for the next one."""
    if not on(troupe):
        return
    for found in db.scalars(
        select(Remembrance).where(
            Remembrance.troupe_id == troupe.id,
            Remembrance.opened_at.is_not(None),
            Remembrance.cycle_id.is_(None),
        )
    ):
        found.cycle_id = cycle.id
    db.flush()


@dataclass(frozen=True)
class Remembered:
    """Remembrances, with the character remembered."""

    remembrance: Remembrance
    character: Character

    @property
    def reason(self) -> str | None:
        return leaving.reason_name(self.character.left_reason)


def in_cycle(db: Session, cycle: DowntimeCycle) -> list[Remembered]:
    """The remembrances the cycle asks for, by the character's name."""
    rows = db.execute(
        select(Remembrance, Character)
        .join(Character, Remembrance.character_id == Character.id)
        .where(Remembrance.cycle_id == cycle.id, Remembrance.opened_at.is_not(None))
        .order_by(Character.name, Character.id)
    )
    return [Remembered(r, c) for r, c in rows]


# --- writing them --------------------------------------------------------------------------


def mine(db: Session, participant: CycleParticipant) -> dict[uuid.UUID, Nomination]:
    """The memories the character has written in this cycle, by remembrance."""
    return {
        n.remembrance_id: n
        for n in db.scalars(
            select(Nomination).where(
                Nomination.participant_id == participant.id,
                Nomination.remembrance_id.is_not(None),
            )
        )
        if n.remembrance_id is not None
    }


def writable(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    remembrance_id: uuid.UUID,
) -> Remembrance:
    troupe = db.get_one(Troupe, cycle.troupe_id)
    require_on(troupe)
    downtimes.ensure_can_submit(db, cycle, participant)
    from horatio import suspensions

    suspensions.refuse_character(db, character)
    found = db.get(Remembrance, remembrance_id)
    if found is None or found.cycle_id != cycle.id or found.opened_at is None:
        raise unprocessable("This downtime doesn't ask for that memory.")
    return found


def write(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    remembrance_id: uuid.UUID,
    text: str,
) -> Nomination:
    """Write the character's memory, or change it until it is published."""
    found = writable(db, character, cycle, participant, remembrance_id)
    text = nominations.checked_text(text)
    memory = mine(db, participant).get(found.id)
    if memory is None:
        memory = Nomination(
            cycle_id=cycle.id, participant_id=participant.id, remembrance_id=found.id, text=text
        )
        db.add(memory)
    elif memory.published_at is not None:
        raise conflict("It's published now: ask a storyteller if it needs changing.")
    elif memory.text != text:
        memory.text = text
        memory.edited_at = None
        memory.edited_by = None
    db.flush()
    return memory


def delete(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    remembrance_id: uuid.UUID,
) -> None:
    found = writable(db, character, cycle, participant, remembrance_id)
    memory = mine(db, participant).get(found.id)
    if memory is None:
        return
    if memory.published_at is not None:
        raise conflict("It's published now: ask a storyteller if it needs changing.")
    db.delete(memory)
    db.flush()


# --- publishing them ------------------------------------------------------------------------


def tell(
    db: Session,
    troupe: Troupe,
    cycle: DowntimeCycle,
    found: Sequence[Nomination],
    before: set[uuid.UUID],
) -> None:
    """For each character with memories published for the first time: the troupe's
    players are told, and the character's own player has a notification of their
    own. `before` are the remembrances with memories published already."""
    fresh = {n.remembrance_id for n in found} - before - {None}
    players = nominations.home_players(db, troupe)
    for remembrance in db.scalars(select(Remembrance).where(Remembrance.id.in_(fresh))):
        character = db.get_one(Character, remembrance.character_id)
        notifications.notify(
            db,
            [character.player_id],
            "remembrance.published",
            f"The troupe's remembrances of {character.name} are up",
            f"/characters/{character.id}",
            troupe_id=troupe.id,
            character_id=character.id,
        )
        notifications.notify(
            db,
            [p for p in players if p != character.player_id],
            "remembrance.published",
            f"Remembrances for {character.name} are up",
            f"/troupes/{troupe.id}/nominations",
            troupe_id=troupe.id,
        )


# --- reading them -----------------------------------------------------------------------------


def can_read(db: Session, user: User, character: Character) -> bool:
    """Whether the user reads the character's published memories: its own player,
    always; the custodian; and its home troupe's staff and players, whatever the
    troupe's setting now."""
    if character.player_id == user.id or user.is_custodian:
        return True
    if character.home_troupe_id is None:
        return False
    troupe = db.get_one(Troupe, character.home_troupe_id)
    return nominations.is_reader(db, user, troupe)


def published(db: Session, character: Character) -> list[tuple[DowntimeCycle, list[Nomination]]]:
    """The character's published memories, newest month first, each month's in the
    order shuffled as they were published."""
    rows = db.execute(
        select(DowntimeCycle, Nomination)
        .join(Nomination, Nomination.cycle_id == DowntimeCycle.id)
        .join(Remembrance, Nomination.remembrance_id == Remembrance.id)
        .where(Remembrance.character_id == character.id, *nominations.shown())
        .order_by(DowntimeCycle.nominations_published_at.desc(), Nomination.shuffle_key)
    )
    months: dict[uuid.UUID, tuple[DowntimeCycle, list[Nomination]]] = {}
    for cycle, memory in rows:
        months.setdefault(cycle.id, (cycle, []))[1].append(memory)
    return list(months.values())


def opened_in(db: Session, troupe: Troupe) -> set[uuid.UUID]:
    """The characters the troupe has opened remembrances for."""
    return set(
        db.scalars(
            select(Remembrance.character_id).where(
                Remembrance.troupe_id == troupe.id, Remembrance.opened_at.is_not(None)
            )
        )
    )


def remembered(db: Session, troupe: Troupe) -> set[uuid.UUID]:
    """The characters with memories published in the troupe."""
    return set(
        db.scalars(
            select(Remembrance.character_id)
            .join(Nomination, Nomination.remembrance_id == Remembrance.id)
            .where(Remembrance.troupe_id == troupe.id, *nominations.shown())
        )
    )
