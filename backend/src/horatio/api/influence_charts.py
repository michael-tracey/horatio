"""The influence log as charts (#710), for the troupe's storytellers and assistant
storytellers, who keep the log. Players and narrators never see it.

The charts are shaped in the browser from a slim copy of the log's entries, and
of who holds what influence now; nothing here is new information to staff, who
can already read every entry, its target and its blocks in the log itself."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import or_, select

from horatio import influence, influence_log
from horatio.api.influence_log import log_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.influence import InfluenceType
from horatio.models import Character, DowntimeCycle, InfluenceEntry, TroupeMembership

router = APIRouter(tags=["influence charts"])

ActorKind = Literal["character", "name"]


class ChartEntryOut(BaseModel):
    id: uuid.UUID
    # E12, UW7.
    short_id: str
    type: InfluenceType
    happened_at: datetime
    # Who took it: a character, or someone not in Horatio (character_id None).
    character_id: uuid.UUID | None
    # The character's name now, or the name as it was logged.
    name: str
    specialization: str
    action_key: str | None
    # "5: Lockdown", "Attack"; "No action yet" while it needs details.
    action: str
    # A general action's level; None for a conflict action or none yet.
    level: int | None
    conflict: bool
    purpose: str
    times: int
    blocks: int
    cycle_id: uuid.UUID | None
    # Whom an Attack, Boost or Defend is aimed at: a character, or a name. An
    # Attack on another entry is aimed at whoever took that entry.
    target_character_id: uuid.UUID | None
    target_name: str
    # What a Block is on, such as "acquiring firearms".
    target_activity: str


class ChartCycleOut(BaseModel):
    id: uuid.UUID
    name: str
    opened_at: datetime | None
    closes_at: datetime


class InfluenceChartsOut(BaseModel):
    entries: list[ChartEntryOut]
    # The troupe's downtime cycles, oldest first.
    cycles: list[ChartCycleOut]


class HoldingOut(BaseModel):
    character_id: uuid.UUID
    name: str
    # pc | npc
    kind: str
    # Each type's rating as it stands now (with any Attack or Boost on it), and
    # the character's own specialisations of that type.
    elite: int
    elite_specializations: list[str]
    underworld: int
    underworld_specializations: list[str]


class InfluenceHoldingsOut(BaseModel):
    # The troupe's characters now with any influence, most first.
    holdings: list[HoldingOut]


@router.get("/troupes/{troupe_id}/influence-charts")
def read_charts(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    since: datetime | None = None,
    until: datetime | None = None,
) -> InfluenceChartsOut:
    """Every entry in the troupe's log (from `since`, up to `until`), oldest first,
    with what the charts need, and the troupe's cycles."""
    log_troupe(db, user, troupe_id)
    query = select(InfluenceEntry).where(InfluenceEntry.troupe_id == troupe_id)
    if since is not None:
        query = query.where(InfluenceEntry.happened_at >= since)
    if until is not None:
        query = query.where(InfluenceEntry.happened_at <= until)
    entries = list(db.scalars(query.order_by(InfluenceEntry.happened_at, InfluenceEntry.number)))
    rules = influence_log.troupe_rules(db, troupe_id)

    # An Attack can be aimed at another entry, possibly outside the range asked for.
    aimed_ids = {e.target_entry_id for e in entries} - {None}
    aimed = {
        e.id: e for e in db.scalars(select(InfluenceEntry).where(InfluenceEntry.id.in_(aimed_ids)))
    }
    character_ids = (
        {e.character_id for e in entries}
        | {e.target_character_id for e in entries}
        | {a.character_id for a in aimed.values()}
    ) - {None}
    names = {
        i: n
        for i, n in db.execute(
            select(Character.id, Character.name).where(Character.id.in_(character_ids))
        )
    }

    def who(character_id: uuid.UUID | None, logged: str) -> tuple[uuid.UUID | None, str]:
        if character_id is not None and character_id in names:
            return character_id, names[character_id]
        return None, logged

    found: list[ChartEntryOut] = []
    for e in entries:
        influence_type: InfluenceType = e.type  # type: ignore[assignment]  # checked by the database
        action = influence.find(rules, influence_type, e.action_key) if e.action_key else None
        actor_id, actor_name = who(e.character_id, e.name)
        target_id, target_name = who(e.target_character_id, e.target_name)
        if e.target_entry_id is not None and (other := aimed.get(e.target_entry_id)) is not None:
            target_id, target_name = who(other.character_id, other.name)
        found.append(
            ChartEntryOut(
                id=e.id,
                short_id=influence_log.short_id(e),
                type=influence_type,
                happened_at=e.happened_at,
                character_id=actor_id,
                name=actor_name,
                specialization=e.specialization,
                action_key=e.action_key,
                action=influence_log.action_label(rules, e),
                level=action.level if action else None,
                conflict=action.conflict if action else False,
                purpose=e.purpose,
                times=e.times,
                blocks=e.blocks,
                cycle_id=e.cycle_id,
                target_character_id=target_id,
                target_name=target_name,
                target_activity=e.target_activity,
            )
        )
    cycles = db.scalars(
        select(DowntimeCycle)
        .where(DowntimeCycle.troupe_id == troupe_id)
        .order_by(DowntimeCycle.closes_at, DowntimeCycle.id)
    )
    return InfluenceChartsOut(
        entries=found,
        cycles=[
            ChartCycleOut(id=c.id, name=c.name, opened_at=c.opened_at, closes_at=c.closes_at)
            for c in cycles
        ],
    )


@router.get("/troupes/{troupe_id}/influence-charts/holdings")
def read_holdings(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> InfluenceHoldingsOut:
    """Who in the troupe holds what influence now: each character's Elite and
    Underworld ratings and specialisations, under its own troupe rules."""
    log_troupe(db, user, troupe_id)
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None)
    )
    characters = db.scalars(
        select(Character).where(
            or_(Character.id.in_(members), Character.owner_troupe_id == troupe_id),
            Character.status != "retired",
        )
    )
    holdings: list[HoldingOut] = []
    for c in characters:
        held = influence.standings(db, c)
        elite, underworld = held["elite"], held["underworld"]
        if elite.rating <= 0 and underworld.rating <= 0:
            continue
        holdings.append(
            HoldingOut(
                character_id=c.id,
                name=c.name,
                kind=c.kind,
                elite=max(elite.rating, 0),
                elite_specializations=elite.held,
                underworld=max(underworld.rating, 0),
                underworld_specializations=underworld.held,
            )
        )
    holdings.sort(key=lambda h: (-(h.elite + h.underworld), h.name.casefold()))
    return InfluenceHoldingsOut(holdings=holdings)
