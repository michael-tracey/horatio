"""Filling Gossip and Insider Trading and Word on the Street from the influence log,
discovery blocks, and how far back lookups look (horatio.influence_lookups)."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import influence_log, influence_lookups
from horatio.api.downtimes import my_participation, staff_troupe
from horatio.api.influence_log import InfluenceEntryOut, entries_out, troupe_entry
from horatio.api.responses import WorkItemOut, item_out, response_item
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.influence import InfluenceType
from horatio.models import InfluenceBlock, InfluenceEntry, Troupe, User
from horatio.permissions import TroupeAction, require_troupe_action
from horatio.responses import WorkItem

router = APIRouter(tags=["influence lookups"])


class WindowOut(BaseModel):
    """The stretch of the log searched, both ends included: from `days` before the
    cycle closes until it closes."""

    since: datetime
    until: datetime
    days: int


class FoundOut(BaseModel):
    """One entry a lookup finds. Never who took it."""

    short_id: str
    happened_at: datetime
    specialization: str
    # "5: Lockdown".
    action: str
    purpose: str
    times: int


class LookupAnswerOut(BaseModel):
    """One of the character's answers taking the lookup this cycle."""

    response_id: uuid.UUID
    question: str
    answer: str
    body: str
    status: str


class LookupOut(BaseModel):
    type: InfluenceType
    # "Word on the Street".
    action_name: str
    # How many of the character's answers this cycle take it.
    strength: int
    window: WindowOut
    # The character's specialisations of the type, which it covers.
    specializations: list[str]
    # Oldest first.
    found: list[FoundOut]
    # In the form's order: the result goes on the last, and the others say they
    # are combined with it.
    answers: list[LookupAnswerOut]


class BlockOut(BaseModel):
    id: uuid.UUID
    entry: InfluenceEntryOut


class DiscoveryBlockOut(BaseModel):
    # Whose action the player says it is.
    whose: Literal["own", "other"] | None
    # The player's own entry they picked, if they did.
    picked: InfluenceEntryOut | None
    # The block this answer added, once accepted.
    block: BlockOut | None
    window: WindowOut
    # Every entry in the window a block can hide, of both types, newest first.
    choices: list[InfluenceEntryOut]


class BlockIn(BaseModel):
    entry_id: uuid.UUID


class OwnEntryOut(BaseModel):
    """One of the player's own character's entries, to pick for a discovery block."""

    id: uuid.UUID
    short_id: str
    type: InfluenceType
    happened_at: datetime
    specialization: str
    action: str
    purpose: str


class BlockChoicesOut(BaseModel):
    window: WindowOut
    # Newest first.
    entries: list[OwnEntryOut]


class Lookback(BaseModel):
    days: int = Field(ge=1, le=3650)


def window_out(span: influence_lookups.Window) -> WindowOut:
    return WindowOut(since=span.since, until=span.until, days=span.days)


def log_item(db: DbSession, user: User, response_id: uuid.UUID) -> tuple[WorkItem, Troupe]:
    """A response, for someone who keeps the troupe's influence log."""
    item, troupe = response_item(db, user, response_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_INFLUENCE_LOG)
    return item, troupe


# --- lookups ----------------------------------------------------------------------------


@router.get("/responses/{response_id}/lookup")
def lookup(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> LookupOut:
    """What a Gossip and Insider Trading or Word on the Street answer finds in the
    log, with the character's other answers it combines with."""
    item, troupe = log_item(db, user, response_id)
    found = influence_lookups.look_up(db, item, troupe)
    rules = influence_log.troupe_rules(db, troupe.id)
    return LookupOut(
        type=found.influence_type,
        action_name=found.action.name,
        strength=found.strength,
        window=window_out(found.window),
        specializations=found.specializations,
        found=[
            FoundOut(
                short_id=influence_log.short_id(e),
                happened_at=e.happened_at,
                specialization=e.specialization,
                action=influence_log.action_label(rules, e),
                purpose=e.purpose,
                times=e.times,
            )
            for e in found.entries
        ],
        answers=[
            LookupAnswerOut(
                response_id=i.response.id,
                question=i.question.prompt,
                answer=i.answer.body,
                body=i.response.body,
                status=i.response.status,
            )
            for i in found.items
        ],
    )


# --- discovery blocks -------------------------------------------------------------------


@router.get("/responses/{response_id}/discovery-block")
def discovery_block(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DiscoveryBlockOut:
    """A discovery block answer: the entry the player picked, the block once
    accepted, and the entries it could hide."""
    item, troupe = log_item(db, user, response_id)
    rules = influence_log.troupe_rules(db, troupe.id)
    if not influence_lookups.is_discovery_block(rules, item):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That answer is not a discovery block.")
    span = influence_lookups.window(troupe, item.cycle)
    picked = influence_lookups.picked_entry(db, item)
    block = influence_lookups.block_by(db, item.response)
    blocked = db.get_one(InfluenceEntry, block.entry_id) if block else None
    choices = influence_lookups.blockable_entries(db, rules, troupe.id, span)
    whose = item.answer.structured.get("block")
    out = entries_out(db, rules, [e for e in (picked, blocked) if e] + choices)
    by_id = {e.id: e for e in out}
    return DiscoveryBlockOut(
        whose=whose if whose in ("own", "other") else None,
        picked=by_id[picked.id] if picked else None,
        block=BlockOut(id=block.id, entry=by_id[block.entry_id]) if block else None,
        window=window_out(span),
        choices=[by_id[e.id] for e in choices],
    )


@router.post("/responses/{response_id}/discovery-block")
def accept_block(
    response_id: uuid.UUID, body: BlockIn, db: DbSession, user: CurrentUser
) -> WorkItemOut:
    """Accept the block on an entry of either type: one more block on it, and the
    response says so."""
    item, troupe = log_item(db, user, response_id)
    entry = troupe_entry(db, user, body.entry_id)
    influence_lookups.accept_block(db, user, item, troupe, entry)
    db.commit()
    return item_out(db, item)


@router.delete("/responses/{response_id}/discovery-block", status_code=status.HTTP_204_NO_CONTENT)
def remove_answer_block(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Take the block this answer added back off its entry."""
    item, _ = log_item(db, user, response_id)
    block = influence_lookups.block_by(db, item.response)
    if block is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This answer has blocked nothing.")
    influence_lookups.remove_block(db, user, block)
    db.commit()


@router.delete("/influence-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_block(block_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """Take a block back off its entry, from the log page."""
    block = db.get(InfluenceBlock, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such block.")
    troupe_entry(db, user, block.entry_id)
    influence_lookups.remove_block(db, user, block)
    db.commit()


@router.get("/characters/{character_id}/downtime/block-choices")
def block_choices(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BlockChoicesOut:
    """The player's own character's entries that a discovery block in this cycle
    can hide. Players never see anyone else's."""
    character, cycle, _ = my_participation(db, user, character_id)
    troupe = db.get_one(Troupe, cycle.troupe_id)
    rules = influence_log.troupe_rules(db, troupe.id)
    span = influence_lookups.window(troupe, cycle)
    entries = influence_lookups.blockable_entries(db, rules, troupe.id, span, character.id)
    return BlockChoicesOut(
        window=window_out(span),
        entries=[
            OwnEntryOut(
                id=e.id,
                short_id=influence_log.short_id(e),
                type=e.type,  # type: ignore[arg-type]  # checked by the database
                happened_at=e.happened_at,
                specialization=e.specialization,
                action=influence_log.action_label(rules, e),
                purpose=e.purpose,
            )
            for e in entries
        ],
    )


# --- the lookback -----------------------------------------------------------------------


@router.put("/troupes/{troupe_id}/influence-lookback")
def set_lookback(
    troupe_id: uuid.UUID, body: Lookback, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """House rule: how many days back lookups look, from the close of their cycle."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    influence_lookups.set_lookback(db, user, troupe, body.days)
    db.commit()
    return troupe_out(db, user, troupe)
