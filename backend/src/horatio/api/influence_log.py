"""The troupe's influence log, for its storytellers and assistant storytellers
(horatio.influence_log). Players never see it."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import or_, select

from horatio import influence, influence_log, influence_lookups, specializations
from horatio.api.downtimes import staff_troupe
from horatio.api.influence import InfluenceActionOut, action_out
from horatio.api.influence_effects import (
    EffectKind,
    EffectRef,
    InfluenceTargetIn,
    InfluenceTargetOut,
    target_in,
    targets_out,
)
from horatio.api.responses import response_item
from horatio.auth.deps import CurrentUser, DbSession
from horatio.influence import InfluenceType
from horatio.models import (
    Character,
    DowntimeCycle,
    InfluenceEntry,
    Response,
    ScheduledGame,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.permissions import TroupeAction, require_troupe_action
from horatio.rules.model import TroupeRules

router = APIRouter(tags=["influence log"])

Source = Literal["downtime", "game", "hand", "import"]
# How many past games the Log influence tool offers to date an entry by.
GAMES = 30


class BlockSourceOut(BaseModel):
    """A discovery block an answer added to an entry (horatio.influence_lookups)."""

    id: uuid.UUID
    response_id: uuid.UUID | None
    # Whose answer, in which cycle; None if the response has gone since.
    character_id: uuid.UUID | None
    character_name: str | None
    cycle_id: uuid.UUID | None
    cycle_name: str | None
    added_at: datetime
    added_by_name: str


class InfluenceEntryOut(BaseModel):
    id: uuid.UUID
    # How staff and players refer to it: E12, UW7.
    short_id: str
    type: InfluenceType
    happened_at: datetime
    # The character; None for someone not in Horatio, or a character since deleted.
    character_id: uuid.UUID | None
    # The name as it was logged.
    name: str
    # The character's name now, where it has changed since.
    current_name: str | None
    # The character is no longer in the troupe: it left, moved its home elsewhere,
    # or retired. Its entries stay in the log all the same.
    left_troupe: bool
    specialization: str
    action_key: str | None
    # "5: Lockdown"; "No action yet" while it needs details.
    action: str
    conflict: bool
    purpose: str
    times: int
    blocks: int
    source: Source
    cycle_id: uuid.UUID | None
    cycle_name: str | None
    play_event_id: uuid.UUID | None
    # An imported row's id in the sheet it came from, such as E334.
    reference: str | None
    needs_details: bool
    logged_by_id: uuid.UUID | None
    logged_by_name: str | None
    logged_at: datetime
    # Downtime answers logged in it.
    response_ids: list[uuid.UUID]
    # A targeted action's target; the effect resolving it recorded, and the kind it
    # would record (horatio.influence_effects).
    target: InfluenceTargetOut | None = None
    effect: EffectRef | None = None
    resolves: EffectKind | None = None
    # The blocks discovery block answers added, of `blocks`; staff may set the
    # rest by hand.
    blocked_by: list[BlockSourceOut] = []


class InfluenceLogOut(BaseModel):
    entries: list[InfluenceEntryOut]
    # How many entries pass the filters, on every page.
    total: int


class InfluenceEntryIn(BaseModel):
    type: InfluenceType
    happened_at: AwareDatetime
    # A character of the troupe, or leave it out and give `name` for someone not in
    # Horatio.
    character_id: uuid.UUID | None = None
    name: str = Field(default="", max_length=200)
    specialization: str = Field(default="", max_length=200)
    action_key: str | None = None
    purpose: str = Field(default="", max_length=1000)
    times: int = Field(default=1, ge=1, le=100)
    blocks: int = Field(default=0, ge=0, le=100)
    needs_details: bool = False
    # A downtime cycle of the troupe's it applies to.
    cycle_id: uuid.UUID | None = None
    # What an Attack, Defend, Boost or Block is aimed at.
    target: InfluenceTargetIn | None = None


class MergeIn(BaseModel):
    # Entries to merge into this one.
    entry_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class LogAnswerIn(BaseModel):
    # The player's answer, trimmed to a short purpose.
    purpose: str = Field(max_length=1000)


class LoggedOut(BaseModel):
    entry: InfluenceEntryOut
    # True when it added to an entry already logged for the same action and purpose.
    repeat: bool


class InfluenceTypeChoices(BaseModel):
    type: InfluenceType
    name: str
    actions: list[InfluenceActionOut]
    # The troupe's specialisations of this type, and any others already in the log.
    specializations: list[str]


class CharacterChoice(BaseModel):
    id: uuid.UUID
    name: str
    kind: str  # pc | npc
    # In the troupe now; otherwise only named in its log.
    in_troupe: bool


class CycleChoice(BaseModel):
    id: uuid.UUID
    name: str
    # Picking a cycle in the Log influence tool dates the entry when it opened, or
    # when it closes if it has not opened yet.
    opened_at: datetime | None
    closes_at: datetime


class GameChoice(BaseModel):
    """A game on the troupe's schedule, which dates an entry when it started."""

    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime


class InfluenceChoicesOut(BaseModel):
    types: list[InfluenceTypeChoices]
    # The troupe's characters now, PCs and NPCs, then those its log names that have
    # left it.
    characters: list[CharacterChoice]
    # People not in Horatio the log names.
    names: list[str]
    cycles: list[CycleChoice]
    # The troupe's games that have started, newest first.
    games: list[GameChoice]


# --- helpers ----------------------------------------------------------------------------


def entries_out(
    db: DbSession, rules: TroupeRules, entries: Sequence[InfluenceEntry]
) -> list[InfluenceEntryOut]:
    character_ids = {e.character_id for e in entries} - {None}
    characters = {
        c.id: c for c in db.scalars(select(Character).where(Character.id.in_(character_ids)))
    }
    troupe_ids = {e.troupe_id for e in entries}
    members = set(
        db.execute(
            select(TroupeMembership.troupe_id, TroupeMembership.character_id).where(
                TroupeMembership.troupe_id.in_(troupe_ids),
                TroupeMembership.character_id.in_(character_ids),
                TroupeMembership.left_at.is_(None),
            )
        ).all()
    )

    def left(entry: InfluenceEntry) -> bool:
        character = characters.get(entry.character_id) if entry.character_id else None
        if character is None:
            return False
        if character.owner_troupe_id == entry.troupe_id:
            return False  # one of the troupe's own NPCs
        return character.status == "retired" or (entry.troupe_id, character.id) not in members

    cycle_ids = {e.cycle_id for e in entries} - {None}
    cycles = {
        i: n
        for i, n in db.execute(
            select(DowntimeCycle.id, DowntimeCycle.name).where(DowntimeCycle.id.in_(cycle_ids))
        )
    }
    user_ids = {e.logged_by for e in entries} - {None}
    users = {
        i: n for i, n in db.execute(select(User.id, User.display_name).where(User.id.in_(user_ids)))
    }
    responses: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for response_id, entry_id in db.execute(
        select(Response.id, Response.influence_entry_id)
        .where(Response.influence_entry_id.in_([e.id for e in entries]))
        .order_by(Response.id)
    ):
        responses.setdefault(entry_id, []).append(response_id)

    targets = targets_out(db, entries)
    blocked_by = influence_lookups.block_sources(db, [e.id for e in entries])

    def current_name(entry: InfluenceEntry) -> str:
        character = characters.get(entry.character_id) if entry.character_id else None
        return character.name if character else entry.name

    found: list[InfluenceEntryOut] = []
    for e in entries:
        influence_type: InfluenceType = e.type  # type: ignore[assignment]  # checked by the database
        action = influence.find(rules, influence_type, e.action_key) if e.action_key else None
        found.append(
            InfluenceEntryOut(
                id=e.id,
                short_id=influence_log.short_id(e),
                type=influence_type,
                happened_at=e.happened_at,
                character_id=e.character_id,
                name=e.name,
                current_name=now if (now := current_name(e)) != e.name else None,
                left_troupe=left(e),
                specialization=e.specialization,
                action_key=e.action_key,
                action=influence_log.action_label(rules, e),
                conflict=action.conflict if action else False,
                purpose=e.purpose,
                times=e.times,
                blocks=e.blocks,
                source=e.source,  # type: ignore[arg-type]  # checked by the database
                cycle_id=e.cycle_id,
                cycle_name=cycles.get(e.cycle_id) if e.cycle_id else None,
                play_event_id=e.play_event_id,
                reference=e.reference,
                needs_details=e.needs_details,
                logged_by_id=e.logged_by,
                logged_by_name=users.get(e.logged_by) if e.logged_by else None,
                logged_at=e.created_at,
                response_ids=responses.get(e.id, []),
                target=targets[e.id][0],
                effect=targets[e.id][1],
                resolves=targets[e.id][2],
                blocked_by=[BlockSourceOut(**vars(b)) for b in blocked_by.get(e.id, [])],
            )
        )
    return found


def entry_out(db: DbSession, entry: InfluenceEntry) -> InfluenceEntryOut:
    return entries_out(db, influence_log.troupe_rules(db, entry.troupe_id), [entry])[0]


def log_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    return staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_INFLUENCE_LOG)


def troupe_entry(db: DbSession, user: User, entry_id: uuid.UUID) -> InfluenceEntry:
    entry = db.get(InfluenceEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry.")
    log_troupe(db, user, entry.troupe_id)
    return entry


def details_from(
    db: DbSession, troupe_id: uuid.UUID, body: InfluenceEntryIn
) -> influence_log.Details:
    if body.cycle_id is not None:
        cycle = db.get(DowntimeCycle, body.cycle_id)
        if cycle is None or cycle.troupe_id != troupe_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No such cycle here.")
    return influence_log.Details(
        influence_type=body.type,
        happened_at=body.happened_at,
        character_id=body.character_id,
        name=body.name,
        specialization=body.specialization,
        action_key=body.action_key,
        purpose=body.purpose,
        times=body.times,
        blocks=body.blocks,
        needs_details=body.needs_details,
        cycle_id=body.cycle_id,
        target=target_in(db, troupe_id, body.target),
    )


def type_specializations(
    db: DbSession, troupe_id: uuid.UUID, rules: TroupeRules, influence_type: InfluenceType
) -> list[str]:
    category = influence.SPECIALIZATIONS[influence_type]
    listed = specializations.troupe_options(db, troupe_id).get(category)
    if listed is None:
        listed = [
            n for (c, n) in rules.rule_set.traits if c == category and n != specializations.CUSTOM
        ]
    used = db.scalars(
        select(InfluenceEntry.specialization)
        .where(
            InfluenceEntry.troupe_id == troupe_id,
            InfluenceEntry.type == influence_type,
            InfluenceEntry.specialization != "",
        )
        .distinct()
    )
    return sorted({*listed, *used}, key=str.casefold)


# --- the log ----------------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/influence-log")
def read_log(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    type: InfluenceType | None = None,
    specialization: str | None = None,
    character_id: uuid.UUID | None = None,
    name: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    needs_details: bool | None = None,
    source: Source | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> InfluenceLogOut:
    """The troupe's entries, newest first, filtered. `since` counts from that moment
    and `until` up to it."""
    log_troupe(db, user, troupe_id)
    filters = influence_log.Filters(
        influence_type=type,
        specialization=specialization,
        character_id=character_id,
        name=name,
        action_key=action,
        since=since,
        until=until,
        needs_details=needs_details,
        source=source,
    )
    entries, total = influence_log.find_entries(db, troupe_id, filters, limit=limit, offset=offset)
    rules = influence_log.troupe_rules(db, troupe_id)
    return InfluenceLogOut(entries=entries_out(db, rules, entries), total=total)


@router.get("/troupes/{troupe_id}/influence-log/choices")
def choices(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> InfluenceChoicesOut:
    """What an entry can say: each type's actions and specialisations, the troupe's
    characters and cycles, and the names of people not in Horatio."""
    log_troupe(db, user, troupe_id)
    rules = influence_log.troupe_rules(db, troupe_id)
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None)
    )
    now = list(
        db.scalars(
            select(Character).where(
                or_(Character.id.in_(members), Character.owner_troupe_id == troupe_id),
                Character.status != "retired",
            )
        )
    )
    here = {c.id for c in now}
    gone = [c for c in influence_log.logged_characters(db, troupe_id) if c.id not in here]
    cycles = db.scalars(
        select(DowntimeCycle)
        .where(DowntimeCycle.troupe_id == troupe_id)
        .order_by(DowntimeCycle.id.desc())
    )
    return InfluenceChoicesOut(
        types=[
            InfluenceTypeChoices(
                type=t,
                name=influence.TYPE_NAMES[t],
                actions=[action_out(a) for a in influence.actions(rules, t)],
                specializations=type_specializations(db, troupe_id, rules, t),
            )
            for t in influence.TYPES
        ],
        characters=[
            CharacterChoice(id=c.id, name=c.name, kind=c.kind, in_troupe=c.id in here)
            for c in sorted(now, key=lambda c: c.name.casefold())
            + sorted(gone, key=lambda c: c.name.casefold())
        ],
        names=influence_log.names_only(db, troupe_id),
        cycles=[
            CycleChoice(id=c.id, name=c.name, opened_at=c.opened_at, closes_at=c.closes_at)
            for c in cycles
        ],
        games=[
            GameChoice(id=g.id, starts_at=g.starts_at, ends_at=g.ends_at)
            for g in db.scalars(
                select(ScheduledGame)
                .where(
                    ScheduledGame.troupe_id == troupe_id,
                    ScheduledGame.starts_at <= datetime.now(UTC),
                )
                .order_by(ScheduledGame.starts_at.desc())
                .limit(GAMES)
            )
        ],
    )


@router.post("/troupes/{troupe_id}/influence-log", status_code=status.HTTP_201_CREATED)
def add_entry(
    troupe_id: uuid.UUID, body: InfluenceEntryIn, db: DbSession, user: CurrentUser
) -> InfluenceEntryOut:
    """Log an action by hand: one taken at a game, by an NPC, or outside a cycle."""
    troupe = log_troupe(db, user, troupe_id)
    entry = influence_log.add_entry(
        db, user, troupe, details_from(db, troupe.id, body), source="hand"
    )
    db.commit()
    return entry_out(db, entry)


@router.put("/influence-entries/{entry_id}")
def change_entry(
    entry_id: uuid.UUID, body: InfluenceEntryIn, db: DbSession, user: CurrentUser
) -> InfluenceEntryOut:
    entry = troupe_entry(db, user, entry_id)
    influence_log.change_entry(db, user, entry, details_from(db, entry.troupe_id, body))
    db.commit()
    return entry_out(db, entry)


@router.delete("/influence-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    entry = troupe_entry(db, user, entry_id)
    influence_log.delete_entry(db, user, entry)
    db.commit()


@router.post("/influence-entries/{entry_id}/merge")
def merge(
    entry_id: uuid.UUID, body: MergeIn, db: DbSession, user: CurrentUser
) -> InfluenceEntryOut:
    """Merge repeats into this entry: their times add to its own."""
    keep = troupe_entry(db, user, entry_id)
    others = [troupe_entry(db, user, i) for i in body.entry_ids if i != keep.id]
    influence_log.merge_entries(db, user, keep, others)
    db.commit()
    return entry_out(db, keep)


# --- logging downtime answers -----------------------------------------------------------


@router.post("/responses/{response_id}/influence-entry")
def log_answer(
    response_id: uuid.UUID, body: LogAnswerIn, db: DbSession, user: CurrentUser
) -> LoggedOut:
    """Log a player's influence answer, with its purpose trimmed by staff."""
    item, troupe = response_item(db, user, response_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_INFLUENCE_LOG)
    entry, repeat = influence_log.log_answer(db, user, item, troupe, body.purpose)
    db.commit()
    return LoggedOut(entry=entry_out(db, entry), repeat=repeat)


@router.delete("/responses/{response_id}/influence-entry", status_code=status.HTTP_204_NO_CONTENT)
def unlog_answer(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Take an answer back off the log."""
    item, troupe = response_item(db, user, response_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_INFLUENCE_LOG)
    influence_log.unlog_answer(db, user, item)
    db.commit()
