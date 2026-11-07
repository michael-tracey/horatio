"""Answering downtimes: the work list, assignment, writing, fill tables, delivery,
and players reading their results."""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from horatio import (
    downtimes,
    equipment,
    influence,
    influence_log,
    keywords,
    quest_actions,
    quest_requirements,
    quests,
    response_items,
    responses,
    targets,
)
from horatio.api.downtimes import staff_cycle, staff_troupe
from horatio.api.equipment import EquipmentItemQuality
from horatio.api.influence import InfluenceAnswerOut, answer_out
from horatio.api.influence_effects import BlockWarningOut, block_warnings
from horatio.api.sheets import players_character
from horatio.api.troupe_equipment import (
    EquipmentItemFieldsIn,
    SpecialEffectModel,
    fields_in,
    refusal,
)
from horatio.auth.deps import CurrentUser, DbSession
from horatio.equipment import EquipmentRefused, ItemQuality
from horatio.models import (
    Answer,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    InfluenceEntry,
    Quest,
    QuestScenario,
    RandomTable,
    Response,
    ResponseItem,
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
from horatio.rules.model import TroupeRules
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


class PairOut(BaseModel):
    """An action a Cancel or Observe is paired with, or one paired with it."""

    response_id: uuid.UUID
    character_name: str
    question: str
    answer: str
    # cancel | observe, for the Cancel or Observe of the pair.
    counter: str | None = None


class AimOut(BaseModel):
    """Who an action is aimed at, for storytellers and assistant storytellers only
    (horatio.targets)."""

    targets: list[str]
    # cancel | observe
    counter: str | None
    # Aimed at someone whose Haven has Location, so it costs two actions...
    located: bool
    # ...unless staff say it isn't against them.
    not_against: bool
    # A Cancel or Observe: the target's action staff paired it with.
    paired: PairOut | None


class ResponseItemFieldsIn(EquipmentItemFieldsIn):
    # The template it was started from, for its history.
    template: str | None = Field(default=None, max_length=200)


class ResponseQualityIn(BaseModel):
    # An item the character holds.
    item_id: uuid.UUID
    name: str = Field(max_length=100)
    detail: str = Field(default="", max_length=300)


class ResponseItemIn(BaseModel):
    """What a response gives (horatio.response_items): a new item, as the Equipment
    tab gives one, or a quality on an item the character holds. One of the two."""

    item: ResponseItemFieldsIn | None = None
    quality: ResponseQualityIn | None = None


class ResponseItemFieldsOut(BaseModel):
    """A new item as staff built it, to change it before it is given."""

    name: str
    kind: str
    grade: str
    qualities: list[EquipmentItemQuality]
    crafted: bool
    archaic: bool
    effects: list[SpecialEffectModel]
    description: str
    staff_note: str
    template: str | None


class ResponseQualityOut(BaseModel):
    item_id: uuid.UUID | None
    name: str
    detail: str
    # The item's name when the quality was added.
    item_name: str


class ResponseItemOut(BaseModel):
    """Equipment a response gives the character, when it is delivered."""

    id: uuid.UUID
    # item | quality
    kind: str
    # As the results say it: "Sniper rifle (Accurate, Scoped)".
    text: str
    # When it reached the character; None until the response is delivered.
    given_at: datetime | None
    # The item made, once given; or the item a quality goes on.
    item_id: uuid.UUID | None
    # Only for those who give equipment (WorkItemOut.can_give): a new item's fields,
    # with its staff note, or the quality.
    item: ResponseItemFieldsOut | None = None
    quality: ResponseQualityOut | None = None


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
    # Who it is aimed at, and the Cancels and Observes paired with it: for
    # storytellers and assistant storytellers, never narrators.
    aim: AimOut | None = None
    countered_by: list[PairOut] = []
    # Its keyword (horatio.keywords), or what stands in for one: Narrative for an action
    # from before keywords, the influence action kind, Quest, or Question.
    keyword: str = "Narrative"
    keyword_key: str | None = None
    # Its step in the troupe's resolution order, and where it comes in that order among
    # the cycle's responses, from 1 (0 when shown alone).
    step: int = keywords.NORMAL_STEP
    step_name: str = ""
    resolution: int = 0
    # A Craft or Perform action: how many of them the character took this cycle, as
    # two raise Resources or Fame for the month (horatio.downtime_effects).
    keyword_actions: int = 0
    # What its keyword's fields say, in words: the territory, what to learn, the item.
    keyword_details: list[str] = []
    status: str
    assigned_to_user_id: uuid.UUID | None
    assigned_to_any_narrator: bool
    body: str
    # Equipment it gives the character when delivered (horatio.response_items).
    items: list[ResponseItemOut] = []
    # The reader gives equipment from it: the character's home troupe's storytellers
    # and assistant storytellers.
    can_give: bool = False


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
    closes_at: datetime
    # Responses still to write: assigned to me, and open to any narrator.
    to_write: int = 0
    open_to_narrators: int = 0


class Assignment(BaseModel):
    user_id: uuid.UUID | None = None
    any_narrator: bool = False


class BulkAssignment(Assignment):
    """Several of a cycle's responses, assigned in one go."""

    response_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


class BulkAssigned(BaseModel):
    assigned: int


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


def pair_out(item: responses.WorkItem) -> PairOut:
    return PairOut(
        response_id=item.response.id,
        character_name=item.character.name,
        question=item.question.prompt,
        answer=item.answer.body,
        counter=targets.counter_of(item.answer.structured),
    )


def aim_out(db: DbSession, item: responses.WorkItem) -> AimOut | None:
    aimed = targets.aimed_at(item.answer.structured)
    if not aimed:
        return None
    names = targets.names_of(db, [item.answer.structured])
    paired = targets.paired_item(db, item)
    return AimOut(
        targets=[names.get(t, "?") for t in aimed],
        counter=targets.counter_of(item.answer.structured),
        located=bool(targets.with_location(db, item.cycle.troupe_id, aimed)),
        not_against=item.answer.not_against,
        paired=pair_out(paired) if paired else None,
    )


def response_item_out(row: ResponseItem, gives: bool) -> ResponseItemOut:
    fields = row.fields
    return ResponseItemOut(
        id=row.id,
        kind=row.kind,
        text=response_items.text(row),
        given_at=row.given_at,
        item_id=row.item_id,
        item=(
            ResponseItemFieldsOut(
                name=fields["name"],
                kind=fields["kind"],
                grade=fields["grade"],
                qualities=[EquipmentItemQuality(**q) for q in fields.get("qualities", [])],
                crafted=fields.get("crafted", False),
                archaic=fields.get("archaic", False),
                effects=[SpecialEffectModel(**e) for e in fields.get("effects", [])],
                description=fields.get("description", ""),
                staff_note=fields.get("staff_note", ""),
                template=fields.get("template"),
            )
            if gives and row.kind == response_items.ITEM
            else None
        ),
        quality=(
            ResponseQualityOut(
                item_id=row.item_id,
                name=fields["name"],
                detail=fields.get("detail", ""),
                item_name=fields["item_name"],
            )
            if gives and row.kind == response_items.QUALITY
            else None
        ),
    )


def keyword_actions(db: DbSession, item: responses.WorkItem, key: str | None) -> int:
    """For a Craft or Perform action, how many the character's downtime has."""
    if key not in (keywords.CRAFT, keywords.PERFORM):
        return 0
    found = db.scalars(
        select(Answer.structured).where(Answer.submission_id == item.answer.submission_id)
    )
    return sum(1 for s in found if keywords.keyword_of(s) == key)


def gives_equipment(db: DbSession, user: User, troupe: Troupe) -> bool:
    """Whether the reader gives equipment from the troupe's responses."""
    return equipment.can_manage(db, user, troupe)


def placed(
    rules: TroupeRules, item: responses.WorkItem, keyword_map: Mapping[str, keywords.Keyword]
) -> keywords.Placed:
    """Where the answer comes in the troupe's resolution order."""
    kind = item.question.action_kind
    influence_type = influence.type_of(kind)
    action = (
        influence.answer_action(rules, influence_type, item.answer.structured)
        if influence_type is not None
        else None
    )
    kinds = {k: v.name for k, v in rules.action_kinds().items()}
    return keywords.place(keyword_map, item.question, item.answer.structured, kinds, action)


def item_out(
    db: DbSession,
    item: responses.WorkItem,
    *,
    running: bool,
    keyword_map: Mapping[str, keywords.Keyword] | None = None,
    resolution: int = 0,
    gives: bool = False,
    given: list[ResponseItem] | None = None,
) -> WorkItemOut:
    """`running`: for a storyteller or assistant storyteller, who sees who an action
    is aimed at; a narrator never does. `keyword_map`: the troupe's keywords, when
    the caller has them. `gives`: the reader gives the troupe's equipment. `given`:
    what the response gives, if already looked up."""
    # The rules of the troupe running the cycle, where the action was taken.
    rules = read_troupe_rules(db, item.character.splat, item.cycle.troupe_id)
    if given is None:
        given = response_items.on_responses(db, [item.response.id]).get(item.response.id, [])
    if keyword_map is None:
        keyword_map = keywords.by_key(keywords.troupe_keywords(db, item.cycle.troupe_id))
    place = placed(rules, item, keyword_map)
    return WorkItemOut(
        id=item.response.id,
        cycle_id=item.cycle.id,
        character_id=item.character.id,
        character_name=item.character.name,
        question=item.question.prompt,
        action_kind=item.question.action_kind,
        answer=item.answer.body,
        structured=item.answer.structured
        if running
        else targets.without_aim(item.answer.structured),
        influence=answer_out(rules, item.question.action_kind, item.answer.structured),
        influence_entry=entry_ref(db, item.response),
        influence_blocks=block_warnings(db, item),
        quest=quest_action_out(db, item),
        aim=aim_out(db, item) if running else None,
        countered_by=[pair_out(i) for i in targets.countered_by(db, item)] if running else [],
        keyword=place.label,
        keyword_key=place.key,
        step=place.step,
        step_name=keywords.STEPS[place.step],
        resolution=resolution,
        keyword_actions=keyword_actions(db, item, place.key),
        keyword_details=keywords.details(db, item.answer.structured),
        status=item.response.status,
        assigned_to_user_id=item.response.assigned_to_user_id,
        assigned_to_any_narrator=item.response.assigned_to_any_narrator,
        body=item.response.body,
        items=[response_item_out(r, gives) for r in given],
        can_give=gives and equipment.home_of(item.character) == item.cycle.troupe_id,
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
    cycles = list(
        db.scalars(
            select(DowntimeCycle)
            .where(DowntimeCycle.troupe_id == troupe_id, DowntimeCycle.status != "draft")
            .order_by(DowntimeCycle.id.desc())
        )
    )
    unwritten = responses.unwritten(db, user, [c.id for c in cycles])
    return [
        WorkCycle(
            id=c.id,
            name=c.name,
            status=c.status,
            closes_at=c.closes_at,
            to_write=unwritten.get(c.id, (0, 0))[0],
            open_to_narrators=unwritten.get(c.id, (0, 0))[1],
        )
        for c in cycles
    ]


@router.get("/cycles/{cycle_id}/responses")
def all_responses(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[WorkItemOut]:
    """Every response in the cycle, for storytellers and assistant storytellers."""
    cycle, troupe = staff_cycle(db, user, cycle_id, TroupeAction.ASSIGN_RESPONSES)
    return items_out(db, user, troupe, cycle, responses.work_items(db, cycle), running=True)


def items_out(
    db: DbSession,
    user: User,
    troupe: Troupe,
    cycle: DowntimeCycle,
    items: list[responses.WorkItem],
    *,
    running: bool,
) -> list[WorkItemOut]:
    """The responses as they come (by character), each with where it comes in the
    troupe's resolution order: by step, then within a step by the keywords' order (an
    influence action by its level), then by character; and what they give, looked up
    at once."""
    gives = gives_equipment(db, user, troupe)
    given = response_items.on_responses(db, [i.response.id for i in items])
    keyword_map = keywords.by_key(keywords.troupe_keywords(db, cycle.troupe_id))
    rules: dict[str, TroupeRules] = {}
    order: list[tuple[tuple[Any, ...], int]] = []
    for n, item in enumerate(items):
        splat = item.character.splat
        rules.setdefault(splat, read_troupe_rules(db, splat, cycle.troupe_id))
        place = placed(rules[splat], item, keyword_map)
        order.append(((place.step, place.rank, item.character.name, n), n))
    rank = {n: r for r, (_, n) in enumerate(sorted(order), start=1)}
    return [
        item_out(
            db,
            item,
            running=running,
            keyword_map=keyword_map,
            resolution=rank[n],
            gives=gives,
            given=given.get(item.response.id, []),
        )
        for n, item in enumerate(items)
    ]


@router.get("/cycles/{cycle_id}/responses/mine")
def my_responses(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[WorkItemOut]:
    """Responses assigned to me, and for narrators the any-narrator pool."""
    cycle, troupe = staff_cycle(db, user, cycle_id, TroupeAction.ANSWER_ASSIGNED_RESPONSES)
    running = responses.is_running(db, user, troupe)
    return items_out(db, user, troupe, cycle, responses.mine(db, user, cycle), running=running)


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
    return item_out(
        db,
        item,
        running=responses.is_running(db, user, troupe),
        gives=gives_equipment(db, user, troupe),
    )


@router.put("/cycles/{cycle_id}/responses/assignment")
def assign_many(
    cycle_id: uuid.UUID, body: BulkAssignment, db: DbSession, user: CurrentUser
) -> BulkAssigned:
    """Assign several of the cycle's responses to one staff member, to any narrator,
    or back to no one, all or none of them."""
    cycle, troupe = staff_cycle(db, user, cycle_id, TroupeAction.ASSIGN_RESPONSES)
    wanted = set(body.response_ids)
    items = responses.work_items(db, cycle, wanted)
    if len(items) != len(wanted):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such response in this cycle.")
    responses.assign_many(db, user, items, troupe, body.user_id, body.any_narrator)
    db.commit()
    return BulkAssigned(assigned=len(items))


@router.post("/responses/{response_id}/accept")
def accept(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    responses.accept(db, user, item, troupe)
    db.commit()
    return item_out(
        db,
        item,
        running=responses.is_running(db, user, troupe),
        gives=gives_equipment(db, user, troupe),
    )


@router.post("/responses/{response_id}/decline")
def decline(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    responses.decline(db, user, item, troupe)
    db.commit()
    return item_out(
        db,
        item,
        running=responses.is_running(db, user, troupe),
        gives=gives_equipment(db, user, troupe),
    )


@router.get("/responses/{response_id}")
def read_response(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    visible = responses.can_write(db, user, item, troupe) or item.response.assigned_to_any_narrator
    if not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such response.")
    return item_out(
        db,
        item,
        running=responses.is_running(db, user, troupe),
        gives=gives_equipment(db, user, troupe),
    )


@router.put("/responses/{response_id}")
def write(response_id: uuid.UUID, body: Writing, db: DbSession, user: CurrentUser) -> WorkItemOut:
    item, troupe = response_item(db, user, response_id)
    if not responses.can_write(db, user, item, troupe):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This response is not assigned to you.")
    responses.write(db, user, item, troupe, body.body)
    db.commit()
    return item_out(
        db,
        item,
        running=responses.is_running(db, user, troupe),
        gives=gives_equipment(db, user, troupe),
    )


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
    return item_out(
        db,
        item,
        running=responses.is_running(db, user, troupe),
        gives=gives_equipment(db, user, troupe),
    )


# --- equipment given from a response (horatio.response_items) -------------------------------


def giving_in(body: ResponseItemIn) -> response_items.Giving:
    if (body.item is None) == (body.quality is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Give an item or a quality, not both."
        )
    if body.item is not None:
        return response_items.NewItem(fields_in(body.item), body.item.template)
    assert body.quality is not None
    quality = body.quality
    return response_items.NewQuality(quality.item_id, ItemQuality(quality.name, quality.detail))


def response_row(item: responses.WorkItem, row_id: uuid.UUID, db: DbSession) -> ResponseItem:
    row = db.get(ResponseItem, row_id)
    if row is None or row.response_id != item.response.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The response gives no such thing.")
    return row


def given_out(db: DbSession, user: User, item: responses.WorkItem, troupe: Troupe) -> WorkItemOut:
    return item_out(
        db,
        item,
        running=responses.is_running(db, user, troupe),
        gives=gives_equipment(db, user, troupe),
    )


@router.post("/responses/{response_id}/items", status_code=status.HTTP_201_CREATED)
def give_from_response(
    response_id: uuid.UUID, body: ResponseItemIn, db: DbSession, user: CurrentUser
) -> WorkItemOut:
    """Give the character a new item, or a quality on one it holds, from the
    response: it reaches the character when the response is delivered, with the
    results. Only its home troupe's storytellers and assistant storytellers."""
    item, troupe = response_item(db, user, response_id)
    try:
        response_items.add(db, user, item, troupe, giving_in(body))
    except EquipmentRefused as error:
        raise refusal(error) from None
    db.commit()
    return given_out(db, user, item, troupe)


@router.put("/responses/{response_id}/items/{row_id}")
def change_response_item(
    response_id: uuid.UUID,
    row_id: uuid.UUID,
    body: ResponseItemIn,
    db: DbSession,
    user: CurrentUser,
) -> WorkItemOut:
    """Change what the response gives, before it is delivered."""
    item, troupe = response_item(db, user, response_id)
    row = response_row(item, row_id, db)
    try:
        response_items.change(db, user, item, troupe, row, giving_in(body))
    except EquipmentRefused as error:
        raise refusal(error) from None
    db.commit()
    return given_out(db, user, item, troupe)


@router.delete("/responses/{response_id}/items/{row_id}")
def remove_response_item(
    response_id: uuid.UUID, row_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> WorkItemOut:
    """Take it off the response, before it is delivered: nothing is given."""
    item, troupe = response_item(db, user, response_id)
    response_items.remove(db, user, item, troupe, response_row(item, row_id, db))
    db.commit()
    return given_out(db, user, item, troupe)


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
    table = responses.save_table(db, troupe_id, body.name, body.entries)
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
