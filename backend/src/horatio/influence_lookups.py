"""Looking things up in the influence log, and hiding things from it.

**Lookups (#130).** Gossip and Insider Trading (Elite) and Word on the Street
(Underworld) are the level-2 general actions. Each tells a character what has
been done lately with influence of its type in any of their specialisations of
it, never who did it (MET: VtM core, p. 512). Staff fill the answer from the log:

- **strength** is how many of the character's answers in the cycle take that
  lookup, since actions for one result are spent in the same month (p. 510);
- **the window** ends when the cycle closes and starts the troupe's lookback in
  days before that, to the minute: 90 by default, the rules' "within the last 3
  months";
- **what is found:** entries of the type, in the character's specialisations of
  it, in the window, blocked fewer times than the strength (p. 511), and
  neither the character's own actions nor conflict actions (Attack, Block,
  Boost, Defend, a discovery block; the troupe's call, not the rules'). Entries
  of characters who have since left the troupe are found like any other.

**Discovery blocks (#131).** A discovery block answer hides one log entry from
lookups: the player picks one of their own entries, or describes someone
else's in words. Staff choose the entry and accept the block, which adds one to
its blocks and records the answer that added it, so a mistaken block can be
taken off again. A block can be paid with actions of either type (p. 511), so
an Elite answer may block an Underworld entry. Only general actions can be
blocked.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from horatio import audit, influence, influence_log, responses
from horatio.influence import InfluenceAction, InfluenceType
from horatio.models import (
    Answer,
    Character,
    CycleParticipant,
    DowntimeCycle,
    InfluenceBlock,
    InfluenceEntry,
    Question,
    Response,
    Submission,
    Troupe,
    User,
)
from horatio.responses import WorkItem
from horatio.rules.model import TroupeRules
from horatio.sheets import conflict, unprocessable

# The level of the lookup actions in each type's list.
LOOKUP_LEVEL = 2
# Targeted actions, never found by a lookup nor blocked, whatever a troupe's own
# list says.
CONFLICT_KEYS = frozenset(
    {
        influence.ATTACK,
        influence.BLOCK,
        influence.BOOST,
        influence.DEFEND,
        influence.DISCOVERY_BLOCK,
    }
)


@dataclass(frozen=True)
class Window:
    """The stretch of the log a lookup searches, both ends included."""

    since: datetime
    until: datetime
    days: int


def window(troupe: Troupe, cycle: DowntimeCycle) -> Window:
    days = troupe.influence_lookback_days
    return Window(since=cycle.closes_at - timedelta(days=days), until=cycle.closes_at, days=days)


def conflict_keys(rules: TroupeRules, influence_type: InfluenceType) -> frozenset[str]:
    return CONFLICT_KEYS | {a.key for a in influence.actions(rules, influence_type) if a.conflict}


def is_lookup(action: InfluenceAction | None) -> bool:
    return action is not None and action.general and action.level == LOOKUP_LEVEL


def answer_of(
    rules: TroupeRules, item: WorkItem
) -> tuple[InfluenceType, InfluenceAction | None] | None:
    """An influence answer's type and action, or None for any other answer."""
    influence_type = influence.type_of(item.question.action_kind)
    if influence_type is None:
        return None
    return influence_type, influence.answer_action(rules, influence_type, item.answer.structured)


# --- lookups ----------------------------------------------------------------------------


@dataclass
class Lookup:
    influence_type: InfluenceType
    action: InfluenceAction
    # The character's answers taking this lookup in the cycle, in the form's order.
    # The result goes on the last; the others are combined with it.
    items: list[WorkItem]
    window: Window
    # The character's specialisations of the type, from their sheet.
    specializations: list[str]
    # What it finds, oldest first.
    entries: list[InfluenceEntry]

    @property
    def strength(self) -> int:
        return len(self.items)


def lookup_items(
    db: Session, rules: TroupeRules, item: WorkItem, influence_type: InfluenceType, key: str
) -> list[WorkItem]:
    """The character's answers in this submission that take the same lookup."""
    rows = db.execute(
        select(Response, Answer, Question)
        .join(Answer, Response.answer_id == Answer.id)
        .join(Question, Answer.question_id == Question.id)
        .where(
            Answer.submission_id == item.answer.submission_id,
            Question.action_kind == item.question.action_kind,
        )
        .order_by(Question.position, Answer.slot)
    )
    found: list[WorkItem] = []
    for response, answer, question in rows:
        action = influence.answer_action(rules, influence_type, answer.structured)
        if action is not None and action.key == key:
            found.append(WorkItem(response, answer, question, item.character, item.cycle))
    return found


def look_up(db: Session, item: WorkItem, troupe: Troupe) -> Lookup:
    """What a Gossip and Insider Trading or Word on the Street answer finds."""
    rules = influence_log.troupe_rules(db, troupe.id)
    answer = answer_of(rules, item)
    if answer is None or not is_lookup(answer[1]):
        raise unprocessable(
            "Only Gossip and Insider Trading and Word on the Street look in the influence log."
        )
    influence_type, action = answer
    assert action is not None
    items = lookup_items(db, rules, item, influence_type, action.key)
    strength = len(items)
    held = influence.standings(db, item.character)[influence_type].held
    span = window(troupe, item.cycle)
    entries: list[InfluenceEntry] = []
    if held:
        entries = list(
            db.scalars(
                select(InfluenceEntry)
                .where(
                    InfluenceEntry.troupe_id == troupe.id,
                    InfluenceEntry.type == influence_type,
                    func.lower(InfluenceEntry.specialization).in_([s.lower() for s in held]),
                    InfluenceEntry.happened_at >= span.since,
                    InfluenceEntry.happened_at <= span.until,
                    InfluenceEntry.action_key.is_not(None),
                    InfluenceEntry.action_key.not_in(conflict_keys(rules, influence_type)),
                    InfluenceEntry.blocks < strength,
                    or_(
                        InfluenceEntry.character_id.is_(None),
                        InfluenceEntry.character_id != item.character.id,
                    ),
                )
                .order_by(InfluenceEntry.happened_at, InfluenceEntry.number)
            )
        )
    return Lookup(
        influence_type=influence_type,
        action=action,
        items=items,
        window=span,
        specializations=held,
        entries=entries,
    )


# --- discovery blocks -------------------------------------------------------------------


def is_discovery_block(rules: TroupeRules, item: WorkItem) -> bool:
    answer = answer_of(rules, item)
    action = answer[1] if answer else None
    return action is not None and action.key == influence.DISCOVERY_BLOCK


def blockable(rules: TroupeRules, entry: InfluenceEntry) -> bool:
    """Only general actions can be blocked (p. 511)."""
    if entry.action_key is None:
        return False
    return entry.action_key not in conflict_keys(rules, entry.type)  # type: ignore[arg-type]  # checked by the database


def blockable_entries(
    db: Session,
    rules: TroupeRules,
    troupe_id: uuid.UUID,
    span: Window,
    character_id: uuid.UUID | None = None,
) -> list[InfluenceEntry]:
    """The troupe's entries in the window that a block can hide, of both types,
    newest first: everyone's, or one character's own."""
    query = select(InfluenceEntry).where(
        InfluenceEntry.troupe_id == troupe_id,
        InfluenceEntry.happened_at >= span.since,
        InfluenceEntry.happened_at <= span.until,
    )
    if character_id is not None:
        query = query.where(InfluenceEntry.character_id == character_id)
    query = query.order_by(InfluenceEntry.happened_at.desc(), InfluenceEntry.number.desc())
    return [e for e in db.scalars(query) if blockable(rules, e)]


def picked_entry(db: Session, item: WorkItem) -> InfluenceEntry | None:
    """The entry a player picked to block: one of their own character's, in the
    troupe running the cycle. Anything else they could send is ignored."""
    structured = item.answer.structured
    if structured.get("block") != "own" or not isinstance(structured.get("block_entry"), str):
        return None
    try:
        entry_id = uuid.UUID(structured["block_entry"])
    except ValueError:
        return None
    entry = db.get(InfluenceEntry, entry_id)
    if (
        entry is None
        or entry.troupe_id != item.cycle.troupe_id
        or entry.character_id != item.character.id
    ):
        return None
    return entry


def block_by(db: Session, response: Response) -> InfluenceBlock | None:
    """The block this answer added, if staff accepted it."""
    return db.scalar(select(InfluenceBlock).where(InfluenceBlock.response_id == response.id))


def accept_block(
    db: Session, actor: User, item: WorkItem, troupe: Troupe, entry: InfluenceEntry
) -> InfluenceBlock:
    """Block an entry with a discovery block answer: one more block on it, and the
    response says so. The entry may be of either type."""
    rules = influence_log.troupe_rules(db, troupe.id)
    if not is_discovery_block(rules, item):
        raise unprocessable("Only a discovery block answer blocks an entry.")
    if block_by(db, item.response) is not None:
        raise conflict("This answer has blocked an entry already. Take that block off first.")
    if entry.troupe_id != troupe.id:
        raise unprocessable("That entry is not in this troupe's influence log.")
    if not blockable(rules, entry):
        raise unprocessable(
            "Only general actions can be blocked, not Attack, Block, Boost, Defend or a "
            "discovery block, nor an entry still needing its details."
        )
    entry.blocks += 1
    block = InfluenceBlock(entry_id=entry.id, response_id=item.response.id, added_by=actor.id)
    db.add(block)
    db.flush()
    audit.record(
        db,
        actor,
        "influence.blocked",
        troupe_id=troupe.id,
        blocks=entry.blocks,
        **influence_log.describe(rules, entry),
    )
    responses.write(db, actor, item, troupe, f"Blocked (now {entry.blocks}).")
    return block


def remove_block(db: Session, actor: User, block: InfluenceBlock) -> InfluenceEntry:
    """Take a block back off its entry, as if it had never been accepted. The
    answer's response stays as written, for staff to change."""
    entry = db.get_one(InfluenceEntry, block.entry_id)
    entry.blocks = max(0, entry.blocks - 1)
    db.delete(block)
    db.flush()
    audit.record(
        db,
        actor,
        "influence.unblocked",
        troupe_id=entry.troupe_id,
        blocks=entry.blocks,
        **influence_log.describe(influence_log.troupe_rules(db, entry.troupe_id), entry),
    )
    return entry


@dataclass
class BlockSource:
    """Where one of an entry's blocks came from."""

    id: uuid.UUID
    response_id: uuid.UUID | None
    # The character whose answer added it, and the cycle; None if the response
    # has gone since.
    character_id: uuid.UUID | None
    character_name: str | None
    cycle_id: uuid.UUID | None
    cycle_name: str | None
    added_at: datetime
    added_by_name: str


def block_sources(
    db: Session, entry_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[BlockSource]]:
    """The blocks answers added to these entries, oldest first."""
    rows = db.execute(
        select(InfluenceBlock, Character, DowntimeCycle, User.display_name)
        .join(User, InfluenceBlock.added_by == User.id)
        .outerjoin(Response, InfluenceBlock.response_id == Response.id)
        .outerjoin(Answer, Response.answer_id == Answer.id)
        .outerjoin(Submission, Answer.submission_id == Submission.id)
        .outerjoin(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .outerjoin(Character, CycleParticipant.character_id == Character.id)
        .outerjoin(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
        .where(InfluenceBlock.entry_id.in_(entry_ids))
        .order_by(InfluenceBlock.created_at, InfluenceBlock.id)
    )
    found: dict[uuid.UUID, list[BlockSource]] = {}
    for block, character, cycle, added_by in rows:
        found.setdefault(block.entry_id, []).append(
            BlockSource(
                id=block.id,
                response_id=block.response_id,
                character_id=character.id if character else None,
                character_name=character.name if character else None,
                cycle_id=cycle.id if cycle else None,
                cycle_name=cycle.name if cycle else None,
                added_at=block.created_at,
                added_by_name=added_by,
            )
        )
    return found


# --- the lookback -----------------------------------------------------------------------


def set_lookback(db: Session, actor: User, troupe: Troupe, days: int) -> None:
    if days < 1:
        raise unprocessable("Look back at least one day.")
    troupe.influence_lookback_days = days
    db.flush()
    audit.record(db, actor, "house.influence_lookback", troupe_id=troupe.id, days=days)
