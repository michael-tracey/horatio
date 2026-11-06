"""Remembrances (horatio.remembrances): the troupe's setting; opening them for a
retired character; writing a memory in a downtime; and reading them on the
character. Their review and publishing are the cycle's, with its Player Nominations
(horatio.api.nominations)."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import audit, downtimes, pictures, remembrances, social_age
from horatio.api.downtimes import my_participation, staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, CycleParticipant, DowntimeCycle, Troupe, User
from horatio.permissions import TroupeAction, visible_character

router = APIRouter(tags=["remembrances"])


class RemembrancesIn(BaseModel):
    on: bool


class RemembrancesSettingOut(BaseModel):
    on: bool


class MemoryIn(BaseModel):
    text: str = Field(max_length=remembrances.TEXT_MOST)


class MyMemoryOut(BaseModel):
    """A character the downtime asks a memory of, and the writer's memory, if any."""

    remembrance_id: uuid.UUID
    character_id: uuid.UUID
    name: str
    picture: str | None
    clan: str | None
    # Why it left: Final Death, Off-field or Inactive.
    reason: str | None
    # The writer's own memory of them, if written.
    text: str | None
    # Published: it can no longer be changed by its writer.
    published: bool


class MyRemembrancesOut(BaseModel):
    remembered: list[MyMemoryOut]
    # Whether the downtime is submitted: staff read them only once it is.
    submitted: bool
    most: int


class MemoryOut(BaseModel):
    id: uuid.UUID
    text: str
    edited: bool


class RememberedMonthOut(BaseModel):
    cycle_id: uuid.UUID
    month: str
    published_at: datetime
    memories: list[MemoryOut]


class CharacterRemembrancesOut(BaseModel):
    # Its home troupe uses Remembrances now. Off, only what was published shows.
    on: bool
    # None asked or opened; its player asked, for staff to confirm; or open.
    state: Literal["none", "asked", "open"]
    # The cycle that asks for memories, or would if they were opened now; None for
    # the next one to open.
    cycle_name: str | None
    # The caller may open them: the home troupe's running staff, while it is on.
    can_open: bool
    # The memories published, newest month first, without names.
    months: list[RememberedMonthOut]


# --- helpers ----------------------------------------------------------------------------------


def my_remembrances_out(
    db: DbSession, cycle: DowntimeCycle, participant: CycleParticipant
) -> MyRemembrancesOut:
    troupe = db.get_one(Troupe, cycle.troupe_id)
    remembrances.require_on(troupe)
    asked = remembrances.in_cycle(db, cycle)
    clans = social_age.standings(db, [r.character.id for r in asked])
    mine = remembrances.mine(db, participant)
    submission = downtimes.submission_for(db, participant)
    out: list[MyMemoryOut] = []
    for r in asked:
        memory = mine.get(r.remembrance.id)
        out.append(
            MyMemoryOut(
                remembrance_id=r.remembrance.id,
                character_id=r.character.id,
                name=r.character.name,
                picture=pictures.picture_url(r.character.id, r.character.picture_id),
                clan=clans[r.character.id].clan,
                reason=r.reason,
                text=memory.text if memory else None,
                published=memory is not None and memory.published_at is not None,
            )
        )
    return MyRemembrancesOut(
        remembered=out,
        submitted=submission is not None and submission.status == "submitted",
        most=remembrances.TEXT_MOST,
    )


def character_remembrances_out(
    db: DbSession, user: User, character: Character
) -> CharacterRemembrancesOut:
    troupe = db.get(Troupe, character.home_troupe_id) if character.home_troupe_id else None
    on = troupe is not None and remembrances.on(troupe) and character.kind == "pc"
    found = remembrances.of(db, character)
    state: Literal["none", "asked", "open"] = (
        "none" if found is None else "open" if found.opened_at is not None else "asked"
    )
    if found is not None and found.cycle_id is not None:
        cycle_name: str | None = db.get_one(DowntimeCycle, found.cycle_id).name
    elif state != "open" and troupe is not None:
        asking = remembrances.asking_cycle(db, troupe)
        cycle_name = asking.name if asking else None
    else:
        cycle_name = None
    return CharacterRemembrancesOut(
        on=on,
        state=state,
        cycle_name=cycle_name,
        can_open=on
        and state != "open"
        and character.status == "retired"
        and troupe is not None
        and remembrances.can_open(db, user, troupe),
        months=[
            RememberedMonthOut(
                cycle_id=cycle.id,
                month=cycle.name,
                published_at=cycle.nominations_published_at,  # type: ignore[arg-type]  # published
                memories=[
                    MemoryOut(id=m.id, text=m.text, edited=m.edited_at is not None)
                    for m in memories
                ],
            )
            for cycle, memories in remembrances.published(db, character)
        ],
    )


def reading_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    """A character whose memories the user reads: its player, and its home troupe's
    staff and players."""
    character = db.get(Character, character_id)
    if character is None or not remembrances.can_read(db, user, character):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No remembrances to read here.")
    return character


# --- the setting --------------------------------------------------------------------------------


@router.put("/troupes/{troupe_id}/remembrances")
def set_remembrances(
    troupe_id: uuid.UUID, body: RemembrancesIn, db: DbSession, user: CurrentUser
) -> RemembrancesSettingOut:
    """Switch Remembrances on or off. Off, none can be opened or written and nothing
    of them shows, but those published stay on the characters and the Who's Who."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    if troupe.remembrances != body.on:
        troupe.remembrances = body.on
        audit.record(
            db, user, "house.remembrances", troupe_id=troupe.id, setting="on" if body.on else "off"
        )
    db.commit()
    return RemembrancesSettingOut(on=troupe.remembrances)


# --- opening them -------------------------------------------------------------------------------


@router.get("/characters/{character_id}/remembrances")
def character_remembrances(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CharacterRemembrancesOut:
    """The character's remembrances: whether they are open, and in which cycle, and
    the memories published, without names. For its player, and its home troupe's
    staff and players."""
    return character_remembrances_out(db, user, reading_character(db, user, character_id))


@router.post("/characters/{character_id}/remembrances/open")
def open_remembrances(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CharacterRemembrancesOut:
    """Open remembrances for a retired character: its home troupe's running staff."""
    character = visible_character(db, user, character_id)
    troupe = db.get(Troupe, character.home_troupe_id) if character.home_troupe_id else None
    if troupe is None or not remembrances.can_open(db, user, troupe):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the home troupe's running staff open remembrances."
        )
    remembrances.open_for(db, user, character)
    db.commit()
    return character_remembrances_out(db, user, character)


# --- writing them -------------------------------------------------------------------------------


@router.get("/characters/{character_id}/downtime/remembrances")
def my_remembrances(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> MyRemembrancesOut:
    """Those the character's open downtime asks memories of, and its own."""
    _, cycle, participant = my_participation(db, user, character_id)
    return my_remembrances_out(db, cycle, participant)


@router.put("/characters/{character_id}/downtime/remembrances/{remembrance_id}")
def write_memory(
    character_id: uuid.UUID,
    remembrance_id: uuid.UUID,
    body: MemoryIn,
    db: DbSession,
    user: CurrentUser,
) -> MyRemembrancesOut:
    """Write the character's memory of someone remembered, or change it."""
    character, cycle, participant = my_participation(db, user, character_id)
    remembrances.write(db, character, cycle, participant, remembrance_id, body.text)
    db.commit()
    return my_remembrances_out(db, cycle, participant)


@router.delete("/characters/{character_id}/downtime/remembrances/{remembrance_id}")
def delete_memory(
    character_id: uuid.UUID, remembrance_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> MyRemembrancesOut:
    character, cycle, participant = my_participation(db, user, character_id)
    remembrances.delete(db, character, cycle, participant, remembrance_id)
    db.commit()
    return my_remembrances_out(db, cycle, participant)
