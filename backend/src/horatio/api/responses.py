"""Answering downtimes: the work list, assignment, writing, fill tables, delivery,
and players reading their results."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from horatio import downtimes, influence_log, quest_actions, quest_requirements, quests, responses
from horatio.api.downtimes import staff_cycle, staff_troupe
from horatio.api.influence import InfluenceAnswerOut, answer_out
from horatio.api.influence_effects import BlockWarningOut, block_warnings
from horatio.api.sheets import players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    InfluenceEntry,
    Quest,
    QuestScenario,
    RandomTable,
    Response,
    Submission,
    Troupe,
    User,
)
from horatio.permissions import (
    TroupeAction,
    can_edit_character,
    require_troupe_action,
    visible_character,
)
from horatio.rules.store import read_troupe_rules

router = APIRouter(tags=["responses"])


class InfluenceEntryRef(BaseModel):
    """The influence log entry an answer was logged in."""

    id: uuid.UUID
    short_id: str
    times: int


class QuestActionRequirementOut(BaseModel):
    label: str
    met: bool
    met_by_name: str


class QuestActionOut(BaseModel):
    """The quest a Quest action names (horatio.quest_actions), as staff answer it."""

    id: uuid.UUID
    name: str
    category: str
    difficulty: int
    downtime_only: bool
    # draft | active | completed | failed | closed
    status: str
    # The scenario the action was for, of how many, and its texts written ahead.
    scenario: int | None
    scenario_count: int
    success_text: str
    fail_text: str
    # Its result, once recorded; whether through this cycle, and still to go out.
    result: str | None
    result_text: str
    recorded_here: bool
    awaiting_delivery: bool
    requirements: list[QuestActionRequirementOut]
    # Other characters who put in a Quest action for it this cycle.
    acted: list[str]
    # For a Complex or Epic quest, party members who put in none this cycle, so have
    # not spent the action its scenario needs (Nothing's Simple, Vol. II Issue 1,
    # p. 102).
    not_spent: list[str]


class WorkItemOut(BaseModel):
    """What a staff member needs to write a response. No character sheet: narrators
    never see sheets, and this is what narrators are shown."""

    id: uuid.UUID
    cycle_id: uuid.UUID
    character_id: uuid.UUID
    character_name: str
    question: str
    action_kind: str | None
    answer: str
    structured: dict[str, Any]
    # An influence answer's action and specialisation (horatio.influence).
    influence: InfluenceAnswerOut | None
    # The influence log entry staff logged it in.
    influence_entry: InfluenceEntryRef | None = None
    # Recorded Blocks an influence answer looks to be up against.
    influence_blocks: list[BlockWarningOut] = []
    # A Quest action's quest.
    quest: QuestActionOut | None = None
    status: str
    assigned_to_user_id: uuid.UUID | None
    assigned_to_any_narrator: bool
    body: str


class QuestResultIn(BaseModel):
    result: Literal["passed", "failed"]
    # The success or fail text, if changed as it is recorded.
    text: str | None = Field(default=None, max_length=8000)
    # A failed result ends the quest as failed, rather than to be tried again.
    ends: bool = False


class WorkCycle(BaseModel):
    id: uuid.UUID
    name: str
    status: str


class Assignment(BaseModel):
    user_id: uuid.UUID | None = None
    any_narrator: bool = False


class Writing(BaseModel):
    body: str


class Progress(BaseModel):
    participants: int
    submitted: int
    responses: int
    unassigned: int
    assigned: int
    written: int
    # Written out of total, per assignee ("any narrator" and "unassigned" included).
    by_assignee: dict[str, dict[str, int]]
    by_action_kind: dict[str, dict[str, int]]


class TableIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    entries: list[str]


class TableOut(TableIn):
    id: uuid.UUID


class Roll(BaseModel):
    text: str


class Delivered(BaseModel):
    # Delivered in Horatio, how many of those again as updates, and how many
    # copies were queued on the troupe's connectors.
    delivered: int
    updated: int = 0
    queued: int = 0


class DeliverIn(BaseModel):
    # Also deliver downtimes with responses still to write.
    partial: bool = False


class ResultOut(BaseModel):
    cycle_id: uuid.UUID
    cycle_name: str
    delivered_at: datetime | None
    # Delivered again since, with responses written or changed after the first time.
    updated: bool = False
    message: str


class DowntimeWaiting(BaseModel):
    """What waits for a player between games, for the counts on their character's tabs."""

    # An open cycle the character is in, with its downtime not yet submitted.
    due: bool
    # When each cycle's results last reached the player, newest first.
    delivered: list[datetime]


def entry_ref(db: DbSession, response: Response) -> InfluenceEntryRef | None:
    entry = (
        db.get(InfluenceEntry, response.influence_entry_id) if response.influence_entry_id else None
    )
    if entry is None:
        return None
    return InfluenceEntryRef(id=entry.id, short_id=influence_log.short_id(entry), times=entry.times)


def quest_action_out(db: DbSession, item: responses.WorkItem) -> QuestActionOut | None:
    if item.question.kind != "quest":
        return None
    quest_id = quest_actions.quest_id_of(item.answer.structured)
    quest = db.get(Quest, quest_id) if quest_id else None
    if quest is None:
        return None
    all_scenarios = quests.scenarios(db, quest)
    number = item.answer.structured.get("scenario")
    scenario: QuestScenario | None = next((s for s in all_scenarios if s.number == number), None)
    found = quest_actions.actions(db, quest, item.cycle)
    return QuestActionOut(
        id=quest.id,
        name=quest.name,
        category=quest.category,
        difficulty=quest.difficulty,
        downtime_only=quest.downtime_only,
        status=quest.status,
        scenario=scenario.number if scenario else None,
        scenario_count=len(all_scenarios),
        success_text=scenario.success_text if scenario else "",
        fail_text=scenario.fail_text if scenario else "",
        result=scenario.result if scenario else None,
        result_text=scenario.result_text if scenario else "",
        recorded_here=scenario is not None and scenario.cycle_id == item.cycle.id,
        awaiting_delivery=scenario is not None and quests.awaiting_delivery(scenario),
        requirements=[
            QuestActionRequirementOut(
                label=quest_requirements.requirement_label(quest_requirements.parse(r.options)),
                met=r.met_at is not None,
                met_by_name=r.met_by_name,
            )
            for r in quests.requirements(db, quest)
        ],
        acted=[a.character.name for a in found if a.answer.id != item.answer.id],
        not_spent=[c.name for c in quest_actions.not_spent(db, quest, item.cycle)],
    )


def item_out(db: DbSession, item: responses.WorkItem) -> WorkItemOut:
    # The rules of the troupe running the cycle, where the action was taken.
    rules = read_troupe_rules(db, item.character.splat, item.cycle.troupe_id)
    return WorkItemOut(
        id=item.response.id,
        cycle_id=item.cycle.id,
        character_id=item.character.id,
        character_name=item.character.name,
        question=item.question.prompt,
        action_kind=item.question.action_kind,
        answer=item.answer.body,
        structured=item.answer.structured,
        influence=answer_out(rules, item.question.action_kind, item.answer.structured),
        influence_entry=entry_ref(db, item.response),
        influence_blocks=block_warnings(db, item),
        quest=quest_action_out(db, item),
        status=item.response.status,
        assigned_to_user_id=item.response.assigned_to_user_id,
        assigned_to_any_narrator=item.response.assigned_to_any_narrator,
        body=item.response.body,
    )


def response_item(
    db: DbSession, user: User, response_id: uuid.UUID
) -> tuple[responses.WorkItem, Troupe]:
    item = responses.item_for(db, response_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such response.")
    troupe = db.get_one(Troupe, item.cycle.troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.ANSWER_ASSIGNED_RESPONSES)
    return item, troupe


# --- staff: the work list ---------------------------------------------------------------


@router.get("/troupes/{troupe_id}/work-cycles")
def work_cycles(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[WorkCycle]:
    """Cycles with downtimes to answer, for any staff member, narrators included."""
    staff_troupe(db, user, troupe_id, TroupeAction.ANSWER_ASSIGNED_RESPONSES)
    cycles = db.scalars(
        select(DowntimeCycle)
        .where(DowntimeCycle.troupe_id == troupe_id, DowntimeCycle.status != "draft")
        .order_by(DowntimeCycle.id.desc())
    )
    return [WorkCycle(id=c.id, name=c.name, status=c.status) for c in cycles]


@router.get("/cycles/{cycle_id}/responses")
def all_responses(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[WorkItemOut]:
    """Every response in the cycle, for storytellers and assistant storytellers."""
    cycle, _ = staff_cycle(db, user, cycle_id, TroupeAction.ASSIGN_RESPONSES)
    return [item_out(db, i) for i in responses.work_items(db, cycle)]


@router.get("/cycles/{cycle_id}/responses/mine")
def my_responses(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[WorkItemOut]:
    """Responses assigned to me, and for narrators the any-narrator pool."""
    cycle, _ = staff_cycle(db, user, cycle_id, TroupeAction.ANSWER_ASSIGNED_RESPONSES)
    return [item_out(db, i) for i in responses.mine(db, user, cycle)]


@router.get("/cycles/{cycle_id}/progress")
def progress(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Progress:
    cycle, _ = staff_cycle(db, user, cycle_id, TroupeAction.ASSIGN_RESPONSES)
    return cycle_progress(db, cycle)


def cycle_progress(db: DbSession, cycle: DowntimeCycle) -> Progress:
    """How far the cycle has got: submitted, assigned and written."""
    items = responses.work_items(db, cycle)
    assignee_ids = {i.response.assigned_to_user_id for i in items if i.response.assigned_to_user_id}
    names = {
        u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(assignee_ids)))
    }
    by_assignee: dict[str, dict[str, int]] = {}
    by_kind: dict[str, dict[str, int]] = {}
    for item in items:
        r = item.response
        assignee = (
            names.get(r.assigned_to_user_id, "?")
            if r.assigned_to_user_id
            else "Any narrator"
            if r.assigned_to_any_narrator
            else "Unassigned"
        )
        kind = "quest" if item.question.kind == "quest" else item.question.action_kind or "custom"
        for bucket, key in ((by_assignee, assignee), (by_kind, kind)):
            counts = bucket.setdefault(key, {"written": 0, "total": 0})
            counts["total"] += 1
            counts["written"] += r.status == "written"
    participants = list(
        db.scalars(
            select(CycleParticipant).where(
                CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None)
            )
        )
    )
    submitted = db.scalar(
        select(func.count())
        .select_from(Submission)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.removed_at.is_(None),
            Submission.status == "submitted",
        )
    )
    return Progress(
        participants=len(participants),
        submitted=submitted or 0,
        responses=len(items),
        unassigned=sum(i.response.status == "unassigned" for i in items),
        assigned=sum(i.response.status == "assigned" for i in items),
        written=sum(i.response.status == "written" for i in items),
        by_assignee=by_assignee,
        by_action_kind=by_kind,
    )


@router.put("/responses/{response_id}/assignment")
def assign(
    response_id: uuid.UUID, body: Assignment, db: DbSession, user: CurrentUser
) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    require_troupe_action(db, user, troupe, TroupeAction.ASSIGN_RESPONSES)
    responses.assign(db, user, item, troupe, body.user_id, body.any_narrator)
    db.commit()
    return item_out(db, item)


@router.post("/responses/{response_id}/accept")
def accept(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    responses.accept(db, user, item, troupe)
    db.commit()
    return item_out(db, item)


@router.post("/responses/{response_id}/decline")
def decline(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    responses.decline(db, user, item, troupe)
    db.commit()
    return item_out(db, item)


@router.get("/responses/{response_id}")
def read_response(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    visible = responses.can_write(db, user, item, troupe) or item.response.assigned_to_any_narrator
    if not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such response.")
    return item_out(db, item)


@router.put("/responses/{response_id}")
def write(response_id: uuid.UUID, body: Writing, db: DbSession, user: CurrentUser) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    if not responses.can_write(db, user, item, troupe):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This response is not assigned to you.")
    responses.write(db, user, item, troupe, body.body)
    db.commit()
    return item_out(db, item)


@router.post("/responses/{response_id}/quest-result")
def record_quest_result(
    response_id: uuid.UUID, body: QuestResultIn, db: DbSession, user: CurrentUser
) -> WorkItemOut:
    """Record the result of the scenario a Quest action was for, on its quest. It is
    the response to every member's Quest action on that scenario in the cycle, and
    goes out with the cycle's delivery."""
    item, troupe = response_item(db, user, response_id)
    if not responses.can_write(db, user, item, troupe):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This response is not assigned to you.")
    quest_actions.record(db, user, item, body.result, body.text, ends=body.ends)
    db.commit()
    return item_out(db, item)


# --- fill tables ------------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/random-tables")
def list_tables(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[TableOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.ANSWER_ASSIGNED_RESPONSES)
    tables = db.scalars(
        select(RandomTable).where(RandomTable.troupe_id == troupe_id).order_by(RandomTable.name)
    )
    return [TableOut(id=t.id, name=t.name, entries=t.entries) for t in tables]


@router.put("/troupes/{troupe_id}/random-tables")
def save_table(troupe_id: uuid.UUID, body: TableIn, db: DbSession, user: CurrentUser) -> TableOut:
    """Create a table, or replace the entries of the one with this name."""
    staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_RANDOM_TABLES)
    table = db.scalar(
        select(RandomTable).where(RandomTable.troupe_id == troupe_id, RandomTable.name == body.name)
    )
    if table is None:
        table = RandomTable(troupe_id=troupe_id, name=body.name)
        db.add(table)
    table.entries = [e.strip() for e in body.entries if e.strip()]
    db.commit()
    return TableOut(id=table.id, name=table.name, entries=table.entries)


@router.post("/troupes/{troupe_id}/random-tables/{name}/roll")
def roll_table(troupe_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser) -> Roll:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.ANSWER_ASSIGNED_RESPONSES)
    return Roll(text=responses.roll(responses.troupe_tables(db, troupe), name))


# --- delivery ---------------------------------------------------------------------------


@router.post("/cycles/{cycle_id}/deliver")
def deliver(
    cycle_id: uuid.UUID, db: DbSession, user: CurrentUser, body: DeliverIn | None = None
) -> Delivered:
    """Deliver the downtimes with every response written, or with `partial` those
    partly answered too: for the first time, or as an update if changed since."""
    cycle, troupe = staff_cycle(db, user, cycle_id, TroupeAction.DELIVER_RESPONSES)
    done = responses.deliver_cycle(
        db, user, cycle, troupe, partial=body is not None and body.partial
    )
    db.commit()
    return Delivered(delivered=done.delivered, updated=done.updated, queued=done.queued)


@router.post("/cycles/{cycle_id}/complete")
def complete(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Delivered:
    cycle, _ = staff_cycle(db, user, cycle_id)
    responses.complete_cycle(db, user, cycle)
    db.commit()
    return Delivered(delivered=0)


@router.get("/characters/{character_id}/downtime/results")
def my_results(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[ResultOut]:
    """Delivered downtime results for the player's character, newest first: for
    each cycle, the latest delivery, which has every response as it was then."""
    character = players_character(db, user, character_id)
    rows = db.execute(
        select(Delivery, DowntimeCycle)
        .join(Submission, Delivery.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
        .where(
            CycleParticipant.character_id == character.id,
            Delivery.channel == "horatio",
            Delivery.status == "sent",
            Delivery.test_mode.is_(False),
        )
        .order_by(DowntimeCycle.id.desc(), Delivery.revision.desc())
    )
    latest: dict[uuid.UUID, ResultOut] = {}
    for d, c in rows:
        latest.setdefault(
            c.id,
            ResultOut(
                cycle_id=c.id,
                cycle_name=c.name,
                delivered_at=d.sent_at,
                updated=d.revision > 1,
                message=d.message,
            ),
        )
    return list(latest.values())


@router.get("/characters/{character_id}/downtime/waiting")
def my_waiting(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DowntimeWaiting:
    """A downtime to submit and when results were delivered, in a few small queries,
    for the character page's tabs; the page itself judges which results are new."""
    character = visible_character(db, user, character_id)
    if not can_edit_character(db, user, character):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the character's player sees this.")
    found = downtimes.waiting(db, [character.id]).get(character.id, downtimes.Waiting())
    return DowntimeWaiting(due=found.due is not None, delivered=list(found.delivered))
