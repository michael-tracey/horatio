"""A character's influence (horatio.influence_history): its history, for its player
and its home troupe's staff, and what the Log influence tool needs to know about
it, for staff."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from horatio import influence, influence_history, influence_log
from horatio.api.influence import InfluenceStandingOut, standing_out
from horatio.api.influence_log import Source, log_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.downtimes import effective_allowance
from horatio.influence import InfluenceType
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    InfluenceEntry,
    Troupe,
    User,
)
from horatio.permissions import visible_character
from horatio.rules.model import TroupeRules

router = APIRouter(tags=["influence history"])


class HistoryEntryOut(BaseModel):
    id: uuid.UUID
    # How staff and players refer to it: E12, UW7.
    short_id: str
    troupe_id: uuid.UUID
    troupe_name: str
    # In a troupe other than the character's home troupe: one it has left, or visits.
    other_troupe: bool
    type: InfluenceType
    happened_at: datetime
    specialization: str
    action_key: str | None
    # "5: Lockdown"; "No action yet" while it needs details.
    action: str
    conflict: bool
    purpose: str
    times: int
    # Discovery blocks this character put on it. Others' blocks are never shown.
    own_blocks: int
    source: Source
    cycle_id: uuid.UUID | None
    cycle_name: str | None
    # The Play View game it was spent in, for a game entry.
    game_number: int | None
    game_started_at: datetime | None
    needs_details: bool
    # The reader can fill in its details here: a game entry, while the game goes on.
    can_finish: bool
    # A Gossip or Word on the Street now could still turn it up: within its
    # troupe's lookback, and not a conflict action.
    findable: bool


class OwedOut(BaseModel):
    type: InfluenceType
    # Actions spent between downtimes, owed to the next cycle.
    amount: int


class InfluenceHistoryOut(BaseModel):
    entries: list[HistoryEntryOut]
    # The character's rating, specialisations and actions in each type, as its
    # sheet stands.
    standings: list[InfluenceStandingOut]
    owed: list[OwedOut]
    # How many days back lookups in the home troupe search, for "Findable now".
    lookback_days: int
    # The troupe the reader can log influence in for this character, if any.
    log_troupe_id: uuid.UUID | None


class FinishIn(BaseModel):
    specialization: str = Field(default="", max_length=200)
    action_key: str
    purpose: str = Field(default="", max_length=1000)


class CycleUseOut(BaseModel):
    type: InfluenceType
    # The character's allowance of this type in the cycle, or None for an NPC or a
    # character not taking part.
    allowance: int | None
    # Actions of this type logged for the character in the cycle, times included.
    logged: int


class LogStandingOut(BaseModel):
    """What the Log influence tool needs about a character."""

    # Its own specialisations of each type come first in the tool's list.
    standings: list[InfluenceStandingOut]
    # For the cycle asked about; empty without one.
    cycle: list[CycleUseOut]


# --- a character's history --------------------------------------------------------------


def history_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    character = visible_character(db, user, character_id)
    if not influence_history.can_see(db, user, character):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the character's player and its home troupe's storytellers see its influence.",
        )
    return character


def history_out(
    db: DbSession, user: User, character: Character, entries: Sequence[InfluenceEntry]
) -> list[HistoryEntryOut]:
    troupe_ids = {e.troupe_id for e in entries}
    troupes = {t.id: t for t in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids)))}
    rules: dict[uuid.UUID, TroupeRules] = {t: influence_log.troupe_rules(db, t) for t in troupe_ids}
    lookbacks = {t: influence_history.lookback_days(db, t) for t in troupe_ids}
    cycle_ids = {e.cycle_id for e in entries} - {None}
    cycles = dict(
        db.execute(
            select(DowntimeCycle.id, DowntimeCycle.name).where(DowntimeCycle.id.in_(cycle_ids))
        ).all()
    )
    games = influence_history.games(db, entries)
    blocks = influence_history.blocks_placed(db, character, entries)
    home = character.home_troupe_id or character.owner_troupe_id
    now = datetime.now(UTC)

    found: list[HistoryEntryOut] = []
    for e in entries:
        influence_type: InfluenceType = e.type  # type: ignore[assignment]  # checked by the database
        here = rules[e.troupe_id]
        action = influence.find(here, influence_type, e.action_key) if e.action_key else None
        game = games.get(e.id)
        found.append(
            HistoryEntryOut(
                id=e.id,
                short_id=influence_log.short_id(e),
                troupe_id=e.troupe_id,
                troupe_name=troupes[e.troupe_id].name,
                other_troupe=e.troupe_id != home,
                type=influence_type,
                happened_at=e.happened_at,
                specialization=e.specialization,
                action_key=e.action_key,
                action=influence_log.action_label(here, e),
                conflict=action.conflict if action else False,
                purpose=e.purpose,
                times=e.times,
                own_blocks=blocks.get(e.id, 0),
                source=e.source,  # type: ignore[arg-type]  # checked by the database
                cycle_id=e.cycle_id,
                cycle_name=cycles.get(e.cycle_id) if e.cycle_id else None,
                game_number=game.number if game else None,
                game_started_at=game.started_at if game else None,
                needs_details=e.needs_details,
                can_finish=influence_history.can_finish(db, user, character, e, game),
                findable=influence_history.findable(e, action, now, lookbacks[e.troupe_id]),
            )
        )
    return found


@router.get("/characters/{character_id}/influence")
def read_history(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> InfluenceHistoryOut:
    """The character's own influence actions, newest first, from every troupe it
    has acted in. Never another character's, nor blocks others placed."""
    character = history_character(db, user, character_id)
    entries = influence_log.character_entries(db, character.id)
    home = influence_history.home_troupe(db, character)
    owed = influence_history.owed(db, character)
    return InfluenceHistoryOut(
        entries=history_out(db, user, character, entries),
        standings=[standing_out(s) for s in influence.standings(db, character).values()],
        owed=[OwedOut(type=t, amount=owed[t]) for t in influence.TYPES],
        lookback_days=(
            influence_history.lookback_days(db, home.id)
            if home
            else influence_history.DEFAULT_LOOKBACK_DAYS
        ),
        log_troupe_id=home.id if home and influence_history.keeps_log(db, user, home) else None,
    )


@router.put("/characters/{character_id}/influence/{entry_id}")
def finish_entry(
    character_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: FinishIn,
    db: DbSession,
    user: CurrentUser,
) -> HistoryEntryOut:
    """Fill in the details of an entry spent at a game still going."""
    character = history_character(db, user, character_id)
    entry = db.get(InfluenceEntry, entry_id)
    if entry is None or entry.character_id != character.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry.")
    influence_history.finish(
        db,
        user,
        character,
        entry,
        specialization=body.specialization,
        action_key=body.action_key,
        purpose=body.purpose,
    )
    db.commit()
    return history_out(db, user, character, [entry])[0]


# --- for the Log influence tool ---------------------------------------------------------


@router.get("/troupes/{troupe_id}/influence-log/characters/{character_id}")
def log_standing(
    troupe_id: uuid.UUID,
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    cycle_id: uuid.UUID | None = None,
) -> LogStandingOut:
    """A character's own specialisations, for the Log influence tool to offer first,
    and for a cycle, its allowance of each type and what is logged against it."""
    troupe = log_troupe(db, user, troupe_id)
    character = db.get(Character, character_id)
    if character is None or not (
        influence_log.in_troupe(db, troupe.id, character)
        or character.id in {c.id for c in influence_log.logged_characters(db, troupe.id)}
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character here.")
    standings = [standing_out(s) for s in influence.standings(db, character).values()]
    if cycle_id is None:
        return LogStandingOut(standings=standings, cycle=[])
    cycle = db.get(DowntimeCycle, cycle_id)
    if cycle is None or cycle.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such cycle here.")
    participant = db.scalar(
        select(CycleParticipant).where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.character_id == character.id,
            CycleParticipant.removed_at.is_(None),
        )
    )
    allowance = (
        effective_allowance(db, participant)
        if participant is not None and character.kind == "pc"
        else None
    )
    logged = dict(
        db.execute(
            select(InfluenceEntry.type, func.sum(InfluenceEntry.times))
            .where(
                InfluenceEntry.troupe_id == troupe.id,
                InfluenceEntry.character_id == character.id,
                InfluenceEntry.cycle_id == cycle.id,
            )
            .group_by(InfluenceEntry.type)
        ).all()
    )
    return LogStandingOut(
        standings=standings,
        cycle=[
            CycleUseOut(
                type=t,
                allowance=(
                    allowance.get(influence.ACTION_KINDS[t], 0) if allowance is not None else None
                ),
                logged=int(logged.get(t) or 0),
            )
            for t in influence.TYPES
        ],
    )
