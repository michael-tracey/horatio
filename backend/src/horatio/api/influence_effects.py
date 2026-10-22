"""Targets and effects of targeted influence actions (horatio.influence_targets,
horatio.influence_effects). Storytellers and assistant storytellers resolve them;
a character's player sees the effects on it, never who made them."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select

from horatio import influence, influence_effects, influence_log, influence_targets
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.influence import InfluenceType
from horatio.influence_effects import Lasting
from horatio.models import Character, InfluenceEffect, InfluenceEntry, Submission, Troupe, User
from horatio.permissions import TroupeAction, visible_character
from horatio.responses import WorkItem

router = APIRouter(tags=["influence effects"])

EffectKind = Literal["attack", "boost", "block"]


# --- targets, on log entries ------------------------------------------------------------


class InfluenceTargetIn(BaseModel):
    """What a targeted action is aimed at: a character; for an Attack, a log entry's
    short id instead (UW268), whoever took it; for a Block, an activity."""

    character_id: uuid.UUID | None = None
    entry: str | None = Field(default=None, max_length=20)
    # The influence aimed at; an Attack may aim at the other type, a Block at either.
    type: InfluenceType | None = None
    activity: str = Field(default="", max_length=300)


class InfluenceTargetOut(BaseModel):
    character_id: uuid.UUID | None
    # The target's name as it was logged.
    name: str
    entry_id: uuid.UUID | None
    entry_short_id: str | None
    type: InfluenceType | None
    activity: str
    # "Vasquez's Elite", "the Underworld behind UW268", "acquiring firearms (Underworld)".
    text: str


class EffectRef(BaseModel):
    id: uuid.UUID
    # "Elite 2 lower".
    text: str
    active: bool


def target_in(
    db: DbSession, troupe_id: uuid.UUID, body: InfluenceTargetIn | None
) -> influence_targets.Target:
    """A target as a request gives it, with an entry's short id looked up."""
    if body is None:
        return influence_targets.NONE
    entry_id = None
    if body.entry and body.entry.strip():
        found = influence_log.by_short_id(db, troupe_id, body.entry)
        if found is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"No entry {body.entry.strip().upper()} in this troupe's log.",
            )
        entry_id = found.id
    return influence_targets.Target(
        character_id=body.character_id,
        entry_id=entry_id,
        influence_type=body.type,
        activity=body.activity,
    )


def type_name(influence_type: str | None) -> str:
    return influence.TYPE_NAMES.get(cast(InfluenceType, influence_type), influence_type or "")


def target_text(entry: InfluenceEntry, target_short_id: str | None) -> str:
    aimed = type_name(entry.target_type or entry.type)
    if entry.action_key == influence.BLOCK:
        return f"{entry.target_activity} ({aimed})"
    if entry.target_character_id is not None or (entry.target_name and not target_short_id):
        return f"{entry.target_name}'s {aimed}"
    if target_short_id:
        return f"the {aimed} behind {target_short_id}"
    return ""


def targets_out(
    db: DbSession, entries: Sequence[InfluenceEntry]
) -> dict[uuid.UUID, tuple[InfluenceTargetOut | None, EffectRef | None, EffectKind | None]]:
    """Each entry's target, the effect resolving it recorded, and the kind of effect
    resolving it would record (None for an entry that makes none)."""
    ids = [e.id for e in entries]
    target_ids = {e.target_entry_id for e in entries} - {None}
    targets = {
        t.id: influence_log.short_id(t)
        for t in db.scalars(select(InfluenceEntry).where(InfluenceEntry.id.in_(target_ids)))
    }
    effects = {
        e.entry_id: e
        for e in db.scalars(select(InfluenceEffect).where(InfluenceEffect.entry_id.in_(ids)))
    }
    found: dict[
        uuid.UUID, tuple[InfluenceTargetOut | None, EffectRef | None, EffectKind | None]
    ] = {}
    for entry in entries:
        short = targets.get(entry.target_entry_id) if entry.target_entry_id else None
        aimed = entry.action_key in influence_targets.TARGETED
        target = (
            InfluenceTargetOut(
                character_id=entry.target_character_id,
                name=entry.target_name,
                entry_id=entry.target_entry_id,
                entry_short_id=short,
                type=cast(InfluenceType | None, entry.target_type),
                activity=entry.target_activity,
                text=target_text(entry, short),
            )
            if aimed
            else None
        )
        effect = effects.get(entry.id)
        ref = (
            EffectRef(
                id=effect.id,
                text=influence_effects.describe(effect),
                active=influence_effects.lasting(db, effect).active,
            )
            if effect
            else None
        )
        found[entry.id] = (target, ref, cast(EffectKind | None, influence_effects.kind_of(entry)))
    return found


# --- effects ----------------------------------------------------------------------------


class InfluenceEffectOut(BaseModel):
    id: uuid.UUID
    kind: EffectKind
    type: InfluenceType
    # An Attack's or Boost's target, with its name as it was.
    character_id: uuid.UUID | None
    name: str
    # The log entry it came from.
    entry_id: uuid.UUID | None
    entry_short_id: str | None
    # Levels lost (after Defends) or raised, or a Block's strength.
    levels: int
    # Levels the target's Defends took off an Attack.
    defended: int
    activity: str
    starts_at: datetime
    # It lasts at least to here, and for an Attack until `games_left` is 0 too.
    ends_at: datetime
    games: int
    games_left: int
    active: bool
    upcoming: bool
    # "Elite 2 lower", "Block 2 on acquiring firearms (Underworld)".
    text: str
    recorded_by_name: str | None


class CharacterEffectOut(BaseModel):
    """An effect on a character, for its sheet: what and until when, not who made it."""

    kind: Literal["attack", "boost"]
    type: InfluenceType
    levels: int
    defended: int
    starts_at: datetime
    ends_at: datetime
    games_left: int
    text: str


class PlanOut(BaseModel):
    """What resolving an entry would record, before staff confirm it."""

    kind: EffectKind
    type: InfluenceType
    character_id: uuid.UUID | None
    name: str
    # Actions the entry spent: its times taken.
    spent: int
    # Levels asked for, or a Block's strength.
    levels: int
    # Actions those levels cost; for an Attack, `per_level` each.
    cost: int
    per_level: int
    # The target's rating now.
    rating: int
    # The target's Defends that count, and the levels they take off.
    defends: list[str]
    defended: int
    # Levels changed in the end, or a Block's strength.
    result: int
    activity: str
    starts_at: datetime
    ends_at: datetime
    games: int
    notes: list[str]


class ResolveIn(BaseModel):
    # Levels to lower or raise by, or a Block's strength; left out, the entry's actions decide.
    levels: int | None = Field(default=None, ge=0, le=10)
    # A Block: the influence blocked, what it is on, and when it ends.
    type: InfluenceType | None = None
    activity: str | None = Field(default=None, max_length=300)
    ends_at: AwareDatetime | None = None


class BlockIn(BaseModel):
    type: InfluenceType
    activity: str = Field(min_length=1, max_length=300)
    strength: int = Field(ge=1, le=20)
    starts_at: AwareDatetime
    # Left out, it lasts to the end of the month it starts in.
    ends_at: AwareDatetime | None = None


class RemovedOut(BaseModel):
    # Something staff should do by hand, such as an allowance already changed.
    note: str | None


def effects_out(
    db: DbSession, held: Sequence[tuple[InfluenceEffect, Lasting]]
) -> list[InfluenceEffectOut]:
    entry_ids = {e.entry_id for e, _ in held} - {None}
    shorts = {
        e.id: influence_log.short_id(e)
        for e in db.scalars(select(InfluenceEntry).where(InfluenceEntry.id.in_(entry_ids)))
    }
    user_ids = {e.recorded_by for e, _ in held} - {None}
    users = {
        i: n for i, n in db.execute(select(User.id, User.display_name).where(User.id.in_(user_ids)))
    }
    return [
        InfluenceEffectOut(
            id=e.id,
            kind=cast(EffectKind, e.kind),
            type=cast(InfluenceType, e.type),
            character_id=e.character_id,
            name=e.name,
            entry_id=e.entry_id,
            entry_short_id=shorts.get(e.entry_id) if e.entry_id else None,
            levels=e.levels,
            defended=e.defended,
            activity=e.activity,
            starts_at=e.starts_at,
            ends_at=e.ends_at,
            games=e.games,
            games_left=h.games_left,
            active=h.active,
            upcoming=h.upcoming,
            text=influence_effects.describe(e),
            recorded_by_name=users.get(e.recorded_by) if e.recorded_by else None,
        )
        for e, h in held
    ]


def effect_out(db: DbSession, effect: InfluenceEffect) -> InfluenceEffectOut:
    return effects_out(db, [(effect, influence_effects.lasting(db, effect))])[0]


def plan_out(found: influence_effects.Plan) -> PlanOut:
    return PlanOut(
        kind=cast(EffectKind, found.kind),
        type=found.influence_type,
        character_id=found.character.id if found.character else None,
        name=found.name,
        spent=found.spent,
        levels=found.levels,
        cost=found.cost,
        per_level=found.per_level,
        rating=found.rating,
        defends=[influence_log.short_id(d) for d in found.defends],
        defended=found.defended,
        result=found.result,
        activity=found.activity,
        starts_at=found.starts_at,
        ends_at=found.ends_at,
        games=found.games,
        notes=found.notes,
    )


def log_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    return staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_INFLUENCE_LOG)


def troupe_entry(db: DbSession, user: User, entry_id: uuid.UUID) -> tuple[InfluenceEntry, Troupe]:
    entry = db.get(InfluenceEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry.")
    return entry, log_troupe(db, user, entry.troupe_id)


def entry_plan(db: DbSession, entry: InfluenceEntry, body: ResolveIn) -> influence_effects.Plan:
    return influence_effects.plan(
        db,
        entry,
        levels=body.levels,
        influence_type=body.type,
        activity=body.activity,
        ends_at=body.ends_at,
    )


@router.get("/influence-entries/{entry_id}/resolution")
def preview(
    entry_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    levels: int | None = None,
    type: InfluenceType | None = None,
    activity: str | None = None,
    ends_at: datetime | None = None,
) -> PlanOut:
    """What resolving an Attack, Boost, Block or location action would record: the
    cost, the Defends taken off, and how long it lasts."""
    entry, _ = troupe_entry(db, user, entry_id)
    body = ResolveIn(levels=levels, type=type, activity=activity, ends_at=ends_at)
    return plan_out(entry_plan(db, entry, body))


@router.post("/influence-entries/{entry_id}/resolution", status_code=status.HTTP_201_CREATED)
def resolve(
    entry_id: uuid.UUID, body: ResolveIn, db: DbSession, user: CurrentUser
) -> InfluenceEffectOut:
    """Resolve the entry: record its effect on the target's influence, or its Block."""
    entry, troupe = troupe_entry(db, user, entry_id)
    effect = influence_effects.record(db, user, troupe, entry_plan(db, entry, body))
    db.commit()
    return effect_out(db, effect)


@router.get("/troupes/{troupe_id}/influence-effects")
def troupe_effects(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, ended: bool = False
) -> list[InfluenceEffectOut]:
    """The troupe's effects and blocks holding now or still to begin, newest first;
    with `ended`, those over too."""
    log_troupe(db, user, troupe_id)
    return effects_out(db, influence_effects.troupe_effects(db, troupe_id, ended=ended))


@router.post("/troupes/{troupe_id}/influence-blocks", status_code=status.HTTP_201_CREATED)
def record_block(
    troupe_id: uuid.UUID, body: BlockIn, db: DbSession, user: CurrentUser
) -> InfluenceEffectOut:
    """Record a Block on an activity with no log entry behind it, such as an NPC's."""
    troupe = log_troupe(db, user, troupe_id)
    effect = influence_effects.record_block(
        db,
        user,
        troupe,
        influence_type=body.type,
        activity=body.activity,
        strength=body.strength,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    db.commit()
    return effect_out(db, effect)


@router.delete("/influence-effects/{effect_id}")
def remove_effect(effect_id: uuid.UUID, db: DbSession, user: CurrentUser) -> RemovedOut:
    """Take an effect back, as if never resolved; its entry can be resolved again."""
    effect = db.get(InfluenceEffect, effect_id)
    if effect is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such effect.")
    log_troupe(db, user, effect.troupe_id)
    note = influence_effects.remove(db, user, effect)
    db.commit()
    return RemovedOut(note=note)


@router.get("/characters/{character_id}/influence-effects")
def character_effects(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[CharacterEffectOut]:
    """The Attacks and Boosts holding on a character now, for its sheet."""
    character: Character = visible_character(db, user, character_id)
    return [
        CharacterEffectOut(
            kind=cast(Literal["attack", "boost"], e.kind),
            type=cast(InfluenceType, e.type),
            levels=e.levels,
            defended=e.defended,
            starts_at=e.starts_at,
            ends_at=e.ends_at,
            games_left=h.games_left,
            text=influence_effects.describe(e),
        )
        for e, h in influence_effects.on_character(db, character.id)
    ]


# --- blocks an answer may be up against -------------------------------------------------


class BlockWarningOut(BaseModel):
    id: uuid.UUID
    # "Block 2 on acquiring firearms (Underworld)".
    text: str
    strength: int
    ends_at: datetime


def block_warnings(db: DbSession, item: WorkItem) -> list[BlockWarningOut]:
    """Recorded Blocks a general influence answer looks to be up against, by the words
    it shares with them. The cost is for staff to judge."""
    influence_type = influence.type_of(item.question.action_kind)
    if influence_type is None:
        return []
    rules = influence_log.troupe_rules(db, item.cycle.troupe_id)
    action = influence.answer_action(rules, influence_type, item.answer.structured)
    if action is not None and action.conflict:
        return []  # Blocks hold back general actions only (p. 511)
    submission = db.get(Submission, item.answer.submission_id)
    since = (submission.submitted_at if submission else None) or item.answer.created_at
    return [
        BlockWarningOut(
            id=b.id, text=influence_effects.describe(b), strength=b.levels, ends_at=b.ends_at
        )
        for b in influence_effects.blocks_against(
            db, item.cycle.troupe_id, influence_type, item.answer.body, since
        )
    ]
