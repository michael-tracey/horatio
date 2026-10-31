"""Quests (horatio.quests): a troupe's settings for them, players' requests, sharing
and joining, and the staff's queue, builder, checks and sending."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import location_quests, quest_actions, quest_requirements, quests
from horatio.api.troupes import TroupeOut, troupe_out
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Character,
    Delivery,
    DowntimeCycle,
    Location,
    Quest,
    QuestLogEntry,
    QuestRequest,
    QuestRequirement,
    QuestScenario,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, require_troupe_action
from horatio.quest_requirements import Option

router = APIRouter(tags=["quests"])

Category = Literal["simple", "complex", "epic"]
Offer = Literal["character", "chosen", "unlocked", "troupe"]


# --- shapes --------------------------------------------------------------------------------


class QuestSettingsIn(BaseModel):
    enabled: bool
    # Requests each character may make in a downtime cycle.
    requests_per_cycle: int = Field(ge=0, le=20)


class QuestCharacterRef(BaseModel):
    id: uuid.UUID
    name: str


class QuestCharacterChoice(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    # Kept for the shared character picker; quests name no titles.
    title: str = ""


class QuestLocationRef(BaseModel):
    id: uuid.UUID
    name: str


class WhoseOut(BaseModel):
    """A character a Contacts lookup may mean, and the locations it controls."""

    name: str
    locations: list[str]


class QuestRequestOut(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    character_id: uuid.UUID
    character_name: str
    player_name: str
    # custom, or about a location: acquire | quality | undermine | repair | whose
    kind: str
    # What a location request names: name, address, map_link, quality, detail,
    # negative, victory, target.
    details: dict[str, str]
    # The location record it is about, for those who keep locations.
    location: QuestLocationRef | None = None
    # For a Contacts lookup: the troupe's characters it may mean, and what each controls.
    whose: list[WhoseOut] = []
    # The reader keeps locations, so can match it to one.
    can_match: bool = False
    objective: str
    reason: str
    companions: str
    # new | working | answered | withdrawn
    status: str
    # quest | not_needed | refused, once answered.
    outcome: str | None
    note: str
    created_at: datetime
    answered_at: datetime | None
    assigned_to_user_id: uuid.UUID | None
    assigned_to_name: str | None
    assigned_to_any_narrator: bool
    quest_id: uuid.UUID | None
    quest_name: str | None
    quest_status: str | None
    # Staff who marked it read.
    read_by: list[str]
    # The reader may build a quest from it, answer it, and assign it.
    can_work: bool
    can_assign: bool


class OptionOut(BaseModel):
    # The alternative as stored (horatio.quest_requirements), and as it reads.
    option: dict[str, Any]
    label: str
    expends: bool


class RequirementCheckOut(BaseModel):
    character_id: uuid.UUID
    name: str
    # Whether its sheet meets each alternative now; None where Horatio cannot tell.
    meets: list[bool | None]


class RequirementOut(BaseModel):
    id: uuid.UUID
    label: str
    options: list[OptionOut]
    met: bool
    met_by_character_id: uuid.UUID | None
    met_by_name: str
    met_label: str | None
    met_patron: bool
    # What meeting it spent, as it reads: "logged as E3".
    spent: str
    # The party's sheets against it, for those who see sheets.
    checks: list[RequirementCheckOut]


class ResourcesOut(BaseModel):
    """Resources expended on a location quest's scenario (Vol. II Issue 1, p. 120)."""

    character_id: uuid.UUID
    name: str
    dots: int
    successes: int


class ScenarioOut(BaseModel):
    number: int
    success_text: str
    fail_text: str
    # passed | failed, once recorded.
    result: str | None
    result_text: str
    sent_at: datetime | None
    # Recorded through this downtime cycle's Quest actions (horatio.quest_actions),
    # and still to go out with its delivery.
    cycle_name: str | None = None
    awaiting_delivery: bool = False
    resources: list[ResourcesOut] = []


class MemberOut(BaseModel):
    character_id: uuid.UUID
    name: str
    player_name: str
    # invited | joined | left
    status: str


class LogOut(BaseModel):
    at: datetime
    actor_name: str | None
    text: str


class QuestDeliveryOut(BaseModel):
    id: uuid.UUID
    character_name: str
    subject: str
    channel: str
    status: str
    last_error: str | None


class QuestDowntimeOut(BaseModel):
    """Who put in a Quest action for the quest in the troupe's current cycle."""

    cycle_id: uuid.UUID
    cycle_name: str
    acted: list[str]
    # For a Complex or Epic quest, party members who put in none, so have not spent
    # the action its scenario needs (Nothing's Simple, Vol. II Issue 1, p. 102).
    not_spent: list[str]


class Guidance(BaseModel):
    # The book's numbers for its category and difficulty (pp. 99-100).
    requirements: int
    scenarios: int


class QuestLocationOut(BaseModel):
    """The location a quest changes when it is completed, and how."""

    id: uuid.UUID
    name: str
    # acquire | quality | swap | upgrade | negative | infiltrate
    kind: str
    change: str


class QuestOut(BaseModel):
    """A quest as staff see it."""

    id: uuid.UUID
    troupe_id: uuid.UUID
    name: str
    objective: str
    category: Category
    difficulty: int
    downtime_only: bool
    staff_notes: str
    # draft | active | completed | failed | closed
    status: str
    leader: QuestCharacterRef | None
    offer: Offer
    unlock_quest_id: uuid.UUID | None
    unlock_quest_name: str | None
    unlock_scenario: int | None
    assigned_to_user_id: uuid.UUID | None
    assigned_to_name: str | None
    assigned_to_any_narrator: bool
    read_by: list[str]
    sent_at: datetime | None
    ended_on: date | None
    finished_by: list[str]
    closed_at: datetime | None
    close_note: str
    tale: str
    tale_approved: bool
    guidance: Guidance
    requirements: list[RequirementOut]
    scenarios: list[ScenarioOut]
    members: list[MemberOut]
    log: list[LogOut]
    request: QuestRequestOut | None
    deliveries: list[QuestDeliveryOut]
    # Quest actions for it in the troupe's open (or last closed) downtime cycle.
    downtime: QuestDowntimeOut | None = None
    # The location it changes, for those who keep locations.
    location: QuestLocationOut | None = None
    # The reader may change it, assign it, send it and check sheets against it.
    can_edit: bool
    can_assign: bool
    can_send: bool
    can_check: bool


class QuestRowOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    category: Category
    difficulty: int
    leader_name: str | None
    offer: Offer
    assigned_to_name: str | None
    assigned_to_any_narrator: bool
    created_at: datetime


class PlayerRequirementOut(BaseModel):
    label: str
    met: bool
    met_by_name: str


class PlayerScenarioOut(BaseModel):
    number: int
    result: str
    text: str
    sent_at: datetime | None


class PlayerQuestOut(BaseModel):
    """A quest as one of its characters' players sees it."""

    id: uuid.UUID
    name: str
    objective: str
    category: Category
    difficulty: int
    downtime_only: bool
    # active | completed | failed | closed
    status: str
    # leader | joined | invited | offered | left
    role: str
    leader_name: str | None
    party: list[str]
    requirements: list[PlayerRequirementOut]
    scenario_count: int
    # Results sent, for its party.
    results: list[PlayerScenarioOut]
    ended_on: date | None
    finished_by: list[str]
    close_note: str
    tale: str
    tale_approved: bool
    can_join: bool
    can_share: bool
    can_write_tale: bool


class PlayerRequestOut(BaseModel):
    id: uuid.UUID
    kind: str
    objective: str
    reason: str
    companions: str
    # waiting | working | answered | withdrawn
    status: str
    outcome: str | None
    note: str
    created_at: datetime
    answered_at: datetime | None
    # The quest it was answered with.
    quest_id: uuid.UUID | None
    can_withdraw: bool


class CharacterQuestsOut(BaseModel):
    # Quests are on in the character's home troupe; nothing else is said if not.
    enabled: bool
    limit: int
    used: int
    cycle_name: str | None
    # Why it cannot ask now, if it cannot.
    refusal: str | None
    requests: list[PlayerRequestOut]
    quests: list[PlayerQuestOut]


class RequestIn(BaseModel):
    objective: str = Field(min_length=1, max_length=4000)
    reason: str = Field(default="", max_length=4000)
    companions: str = Field(default="", max_length=1000)


class AssignmentIn(BaseModel):
    user_id: uuid.UUID | None = None
    any_narrator: bool = False


class RequestAnswerIn(BaseModel):
    # done: a repair or a Contacts lookup answered without a quest.
    outcome: Literal["not_needed", "refused", "done"]
    note: str = Field(max_length=4000)


class ScenarioIn(BaseModel):
    success_text: str = Field(default="", max_length=8000)
    fail_text: str = Field(default="", max_length=8000)


class QuestIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=8000)
    category: Category = "simple"
    # 1 to 5; a location's qualities can raise it further (Vol. II Issue 1, p. 126).
    difficulty: int = Field(default=1, ge=1, le=10)
    downtime_only: bool = False
    staff_notes: str = Field(default="", max_length=8000)
    leader_id: uuid.UUID | None = None
    offer: Offer = "character"
    unlock_quest_id: uuid.UUID | None = None
    unlock_scenario: int | None = Field(default=None, ge=1, le=20)
    # The request it answers.
    request_id: uuid.UUID | None = None
    # Its scenarios; the book's number of empty ones if left out.
    scenarios: list[ScenarioIn] | None = Field(default=None, max_length=20)


class RequirementIn(BaseModel):
    options: list[Option] = Field(min_length=1, max_length=6)


class MetIn(BaseModel):
    character_id: uuid.UUID
    # Which alternative.
    option: int = Field(default=0, ge=0)


class MembersIn(BaseModel):
    character_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    # In the party now (at a game), rather than able to join.
    joined: bool = False


class ResultIn(BaseModel):
    result: Literal["passed", "failed"]
    # The success or fail text, if changed as it is sent.
    text: str | None = Field(default=None, max_length=8000)
    # A failed result ends the quest as failed, rather than to be tried again.
    ends: bool = False


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class TaleIn(BaseModel):
    tale: str = Field(max_length=20000)
    # Staff: approve it as the official account.
    approve: bool = False


class LogIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ShareIn(BaseModel):
    character_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


# --- finding things ------------------------------------------------------------------------


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"No such {what}.")


def forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "You cannot do that in this troupe.")


def staff_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    """A troupe whose quests the user may see as staff: running staff, or a narrator."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise not_found("troupe")
    require_troupe_action(db, user, troupe, TroupeAction.ANSWER_ASSIGNED_RESPONSES)
    return troupe


def staff_request(db: DbSession, user: User, request_id: uuid.UUID) -> tuple[QuestRequest, Troupe]:
    request = db.get(QuestRequest, request_id)
    if request is None:
        raise not_found("request")
    troupe = staff_troupe(db, user, request.troupe_id)
    if not quests.is_running(db, user, troupe) and not quests.narrator_may_see(user, request):
        raise not_found("request")
    return request, troupe


def staff_quest(db: DbSession, user: User, quest_id: uuid.UUID) -> tuple[Quest, Troupe]:
    quest = db.get(Quest, quest_id)
    if quest is None:
        raise not_found("quest")
    troupe = staff_troupe(db, user, quest.troupe_id)
    if not quests.is_running(db, user, troupe) and not quests.narrator_may_see(user, quest):
        raise not_found("quest")
    return quest, troupe


def running_quest(db: DbSession, user: User, quest_id: uuid.UUID) -> tuple[Quest, Troupe]:
    quest, troupe = staff_quest(db, user, quest_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_QUESTS)
    return quest, troupe


def worked_quest(db: DbSession, user: User, quest_id: uuid.UUID) -> tuple[Quest, Troupe]:
    """A quest the user may change: running staff, or the narrator it is assigned to."""
    quest, troupe = staff_quest(db, user, quest_id)
    if not quests.may_work_on(db, user, troupe, quest):
        raise forbidden()
    return quest, troupe


def own_character(db: DbSession, user: User, character_id: uuid.UUID) -> Character:
    """The user's own PC (or any, for the custodian)."""
    character = db.get(Character, character_id)
    if character is None or not (
        user.is_custodian or (character.kind == "pc" and character.player_id == user.id)
    ):
        raise not_found("character")
    return character


def seen_quest(
    db: DbSession, character: Character, quest_id: uuid.UUID
) -> tuple[Quest, quests.Role_]:
    quest = db.get(Quest, quest_id)
    troupe = db.get(Troupe, quest.troupe_id) if quest else None
    role = quests.role_of(db, quest, character) if quest else None
    if quest is None or troupe is None or not troupe.quests_enabled or role is None:
        raise not_found("quest")
    return quest, role


def names(db: DbSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    return {
        u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(set(user_ids))))
    }


# --- out -----------------------------------------------------------------------------------


def request_out(
    db: DbSession, user: User, troupe: Troupe, request: QuestRequest
) -> QuestRequestOut:
    character = db.get_one(Character, request.character_id)
    people = names(
        db,
        [
            request.requested_by,
            *([request.assigned_to_user_id] if request.assigned_to_user_id else []),
            *(uuid.UUID(u) for u in request.read_by),
        ],
    )
    quest = db.get(Quest, request.quest_id) if request.quest_id else None
    running = quests.is_running(db, user, troupe)
    location = db.get(Location, request.location_id) if request.location_id and running else None
    open_ = request.status in ("new", "working")
    return QuestRequestOut(
        id=request.id,
        troupe_id=request.troupe_id,
        character_id=character.id,
        character_name=character.name,
        player_name=people.get(request.requested_by, ""),
        kind=request.kind,
        details={k: str(v) for k, v in request.details.items()},
        location=QuestLocationRef(id=location.id, name=location.name) if location else None,
        whose=[
            WhoseOut(name=w.name, locations=w.locations)
            for w in location_quests.whose(db, troupe, request.details.get("target", ""))
        ]
        if running and request.kind == "whose" and open_
        else [],
        can_match=running and open_ and request.kind in ("acquire", "undermine"),
        objective=request.objective,
        reason=request.reason,
        companions=request.companions,
        status=request.status,
        outcome=request.outcome,
        note=request.note,
        created_at=request.created_at,
        answered_at=request.answered_at,
        assigned_to_user_id=request.assigned_to_user_id,
        assigned_to_name=people.get(request.assigned_to_user_id)
        if request.assigned_to_user_id
        else None,
        assigned_to_any_narrator=request.assigned_to_any_narrator,
        quest_id=quest.id if quest else None,
        quest_name=quest.name if quest else None,
        quest_status=quest.status if quest else None,
        read_by=[people[uuid.UUID(u)] for u in request.read_by if uuid.UUID(u) in people],
        can_work=quests.may_work_on(db, user, troupe, request)
        and request.status in ("new", "working"),
        can_assign=running and request.status in ("new", "working"),
    )


def options_out(options: list[Option]) -> list[OptionOut]:
    return [
        OptionOut(
            option=o.model_dump(),
            label=quest_requirements.label(o),
            expends=quest_requirements.expends(o),
        )
        for o in options
    ]


def requirement_out(
    db: DbSession, quest: Quest, requirement: QuestRequirement, with_checks: bool
) -> RequirementOut:
    options = quest_requirements.parse(requirement.options)
    met = requirement.met_at is not None
    met_label = (
        quest_requirements.label(options[requirement.met_option])
        if met and requirement.met_option is not None and requirement.met_option < len(options)
        else None
    )
    return RequirementOut(
        id=requirement.id,
        label=quest_requirements.requirement_label(options),
        options=options_out(options),
        met=met,
        met_by_character_id=requirement.met_by_character_id,
        met_by_name=requirement.met_by_name,
        met_label=met_label,
        met_patron=requirement.met_patron,
        spent=quests.spent_text(requirement.spent),
        checks=[
            RequirementCheckOut(character_id=c.id, name=c.name, meets=meets)
            for c, meets in (quests.checks(db, quest, requirement) if with_checks else [])
        ],
    )


def scenario_out(db: DbSession, s: QuestScenario) -> ScenarioOut:
    cycle = db.get(DowntimeCycle, s.cycle_id) if s.cycle_id else None
    return ScenarioOut(
        number=s.number,
        success_text=s.success_text,
        fail_text=s.fail_text,
        result=s.result,
        result_text=s.result_text,
        sent_at=s.sent_at,
        cycle_name=cycle.name if cycle else None,
        awaiting_delivery=quests.awaiting_delivery(s),
        resources=[ResourcesOut(**r) for r in s.resources],
    )


def downtime_out(db: DbSession, quest: Quest) -> QuestDowntimeOut | None:
    if quest.sent_at is None:
        return None
    cycle = quest_actions.cycle_now(db, quest.troupe_id)
    if cycle is None:
        return None
    acted = quest_actions.actions(db, quest, cycle)
    if quest.status != "active" and not acted:
        return None
    return QuestDowntimeOut(
        cycle_id=cycle.id,
        cycle_name=cycle.name,
        acted=[a.character.name for a in acted],
        not_spent=[c.name for c in quest_actions.not_spent(db, quest, cycle)]
        if quest.status == "active"
        else [],
    )


def quest_out(db: DbSession, user: User, troupe: Troupe, quest: Quest) -> QuestOut:
    running = quests.is_running(db, user, troupe)
    leader = db.get(Character, quest.leader_id) if quest.leader_id else None
    unlock = db.get(Quest, quest.unlock_quest_id) if quest.unlock_quest_id else None
    log_rows = list(
        db.scalars(
            select(QuestLogEntry)
            .where(QuestLogEntry.quest_id == quest.id)
            .order_by(QuestLogEntry.created_at.desc(), QuestLogEntry.id.desc())
        )
    )
    found_members = quests.members(db, quest)
    people = names(
        db,
        [
            *([quest.assigned_to_user_id] if quest.assigned_to_user_id else []),
            *(uuid.UUID(u) for u in quest.read_by),
            *(e.actor_id for e in log_rows if e.actor_id),
            *(c.player_id for _, c in found_members),
        ],
    )
    request = quests.request_of(db, quest)
    sent_out = db.execute(
        select(Delivery, Character.name)
        .join(Character, Delivery.character_id == Character.id)
        .where(Delivery.quest_id == quest.id)
        .order_by(Delivery.created_at)
    )
    requirements_, scenarios_ = quests.guidance(quest.category, quest.difficulty)
    may_work = quests.may_work_on(db, user, troupe, quest)
    open_ = quest.status in ("draft", "active")
    return QuestOut(
        id=quest.id,
        troupe_id=quest.troupe_id,
        name=quest.name,
        objective=quest.objective,
        category=quest.category,  # type: ignore[arg-type]  # checked by the database
        difficulty=quest.difficulty,
        downtime_only=quest.downtime_only,
        staff_notes=quest.staff_notes,
        status=quest.status,
        leader=QuestCharacterRef(id=leader.id, name=leader.name) if leader else None,
        offer=quest.offer,  # type: ignore[arg-type]  # checked by the database
        unlock_quest_id=quest.unlock_quest_id,
        unlock_quest_name=unlock.name if unlock else None,
        unlock_scenario=quest.unlock_scenario,
        assigned_to_user_id=quest.assigned_to_user_id,
        assigned_to_name=people.get(quest.assigned_to_user_id)
        if quest.assigned_to_user_id
        else None,
        assigned_to_any_narrator=quest.assigned_to_any_narrator,
        read_by=[people[uuid.UUID(u)] for u in quest.read_by if uuid.UUID(u) in people],
        sent_at=quest.sent_at,
        ended_on=quest.ended_on,
        finished_by=[f["name"] for f in quest.finished_by],
        closed_at=quest.closed_at,
        close_note=quest.close_note,
        tale=quest.tale,
        tale_approved=quest.tale_approved_at is not None,
        guidance=Guidance(requirements=requirements_, scenarios=scenarios_),
        requirements=[
            requirement_out(db, quest, r, running) for r in quests.requirements(db, quest)
        ],
        scenarios=[scenario_out(db, s) for s in quests.scenarios(db, quest)],
        members=[
            MemberOut(
                character_id=c.id,
                name=c.name,
                player_name=people.get(c.player_id, "") if c.kind == "pc" else "NPC",
                status=m.status,
            )
            for m, c in found_members
        ],
        log=[
            LogOut(
                at=e.created_at,
                actor_name=people.get(e.actor_id) if e.actor_id else None,
                text=e.text,
            )
            for e in log_rows
        ],
        request=request_out(db, user, troupe, request) if request else None,
        deliveries=[
            QuestDeliveryOut(
                id=d.id,
                character_name=name,
                subject=d.subject,
                channel=d.channel,
                status=d.status,
                last_error=d.last_error,
            )
            for d, name in sent_out
        ],
        downtime=downtime_out(db, quest),
        location=location_out(db, quest) if running else None,
        can_edit=may_work and open_,
        can_assign=running and open_,
        can_send=running and open_,
        can_check=running,
    )


def location_out(db: DbSession, quest: Quest) -> QuestLocationOut | None:
    location = db.get(Location, quest.location_id) if quest.location_id else None
    if location is None or quest.location_change is None:
        return None
    change = location_quests.Change(**quest.location_change)
    return QuestLocationOut(
        id=location.id,
        name=location.name,
        kind=change.kind,
        change=location_quests.describe_change(location, change),
    )


def quest_row(db: DbSession, quest: Quest) -> QuestRowOut:
    leader = db.get(Character, quest.leader_id) if quest.leader_id else None
    assignee = db.get(User, quest.assigned_to_user_id) if quest.assigned_to_user_id else None
    return QuestRowOut(
        id=quest.id,
        name=quest.name,
        status=quest.status,
        category=quest.category,  # type: ignore[arg-type]  # checked by the database
        difficulty=quest.difficulty,
        leader_name=leader.name if leader else None,
        offer=quest.offer,  # type: ignore[arg-type]  # checked by the database
        assigned_to_name=assignee.display_name if assignee else None,
        assigned_to_any_narrator=quest.assigned_to_any_narrator,
        created_at=quest.created_at,
    )


def player_quest_out(
    db: DbSession, character: Character, quest: Quest, role: quests.Role_
) -> PlayerQuestOut:
    leader = db.get(Character, quest.leader_id) if quest.leader_id else None
    in_party = role in ("leader", "joined")
    all_scenarios = quests.scenarios(db, quest)
    # A result recorded through a downtime cycle shows once that cycle is delivered,
    # and so does the end it brought.
    sent = [s for s in all_scenarios if s.result is not None and s.sent_at is not None]
    waiting = any(quests.awaiting_delivery(s) for s in all_scenarios)
    status = "active" if waiting and quest.status in ("completed", "failed") else quest.status
    ended = status in ("completed", "failed")
    return PlayerQuestOut(
        id=quest.id,
        name=quest.name,
        objective=quest.objective,
        category=quest.category,  # type: ignore[arg-type]  # checked by the database
        difficulty=quest.difficulty,
        downtime_only=quest.downtime_only,
        status=status,
        role=role,
        leader_name=leader.name if leader else None,
        party=[c.name for c in quests.party(db, quest)],
        requirements=[
            PlayerRequirementOut(
                label=quest_requirements.requirement_label(quest_requirements.parse(r.options)),
                met=r.met_at is not None,
                met_by_name=r.met_by_name,
            )
            for r in quests.requirements(db, quest)
        ],
        scenario_count=len(all_scenarios),
        results=[
            PlayerScenarioOut(
                number=s.number, result=s.result or "", text=s.result_text, sent_at=s.sent_at
            )
            for s in sent
        ]
        if in_party
        else [],
        ended_on=quest.ended_on if ended else None,
        finished_by=[f["name"] for f in quest.finished_by] if ended else [],
        close_note=quest.close_note,
        tale=quest.tale if in_party else "",
        tale_approved=quest.tale_approved_at is not None,
        can_join=quest.status == "active" and role in ("invited", "offered"),
        can_share=quest.status == "active" and role == "leader",
        can_write_tale=role == "leader" and ended and quest.tale_approved_at is None,
    )


PLAYER_STATUS = {"new": "waiting", "working": "working", "answered": "answered"}


def player_request_out(db: DbSession, request: QuestRequest) -> PlayerRequestOut:
    quest = db.get(Quest, request.quest_id) if request.quest_id else None
    return PlayerRequestOut(
        id=request.id,
        kind=request.kind,
        objective=request.objective,
        reason=request.reason,
        companions=request.companions,
        status=PLAYER_STATUS.get(request.status, request.status),
        outcome=request.outcome,
        note=request.note,
        created_at=request.created_at,
        answered_at=request.answered_at,
        quest_id=quest.id if quest and quest.sent_at is not None else None,
        can_withdraw=request.status == "new",
    )


def character_quests_out(db: DbSession, character: Character) -> CharacterQuestsOut:
    troupe = quests.home_troupe(db, character)
    if troupe is None or not troupe.quests_enabled:
        # Quests elsewhere it was shared on still show, while their troupes run them.
        shown = quests.visible_quests(db, character)
        return CharacterQuestsOut(
            enabled=bool(shown),
            limit=0,
            used=0,
            cycle_name=None,
            refusal="This character's home troupe does not run quests.",
            requests=[],
            quests=[player_quest_out(db, character, q, r) for q, r in shown],
        )
    found = quests.allowance(db, troupe, character)
    requests = db.scalars(
        select(QuestRequest)
        .where(QuestRequest.character_id == character.id, QuestRequest.troupe_id == troupe.id)
        .order_by(QuestRequest.created_at.desc())
    )
    return CharacterQuestsOut(
        enabled=True,
        limit=found.limit,
        used=found.used,
        cycle_name=found.cycle.name if found.cycle else None,
        refusal=found.refusal,
        requests=[player_request_out(db, r) for r in requests],
        quests=[
            player_quest_out(db, character, q, r) for q, r in quests.visible_quests(db, character)
        ],
    )


def fields_from(body: QuestIn) -> quests.QuestFields:
    return quests.QuestFields(
        name=body.name,
        objective=body.objective,
        category=body.category,
        difficulty=body.difficulty,
        downtime_only=body.downtime_only,
        staff_notes=body.staff_notes,
        leader_id=body.leader_id,
        offer=body.offer,
        unlock_quest_id=body.unlock_quest_id,
        unlock_scenario=body.unlock_scenario,
    )


def texts_from(body: QuestIn) -> list[tuple[str, str]] | None:
    if body.scenarios is None:
        return None
    return [(s.success_text, s.fail_text) for s in body.scenarios]


# --- the troupe's settings -----------------------------------------------------------------


@router.put("/troupes/{troupe_id}/quest-settings")
def set_quest_settings(
    troupe_id: uuid.UUID, body: QuestSettingsIn, db: DbSession, user: CurrentUser
) -> TroupeOut:
    """Turn quests on or off, and set how many requests a character may make a cycle."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise not_found("troupe")
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
    quests.set_settings(db, user, troupe, body.enabled, body.requests_per_cycle)
    db.commit()
    return troupe_out(db, user, troupe)


# --- players -------------------------------------------------------------------------------


@router.get("/characters/{character_id}/quests")
def character_quests(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CharacterQuestsOut:
    """The character's quest requests and the quests it may see. Nothing while its
    home troupe has quests off."""
    return character_quests_out(db, own_character(db, user, character_id))


@router.post("/characters/{character_id}/quest-requests", status_code=status.HTTP_201_CREATED)
def request_quest(
    character_id: uuid.UUID, body: RequestIn, db: DbSession, user: CurrentUser
) -> PlayerRequestOut:
    """Ask the home troupe's staff for a custom quest. Refused, with the reason, past
    the troupe's limit for the cycle."""
    character = own_character(db, user, character_id)
    request = quests.make_request(
        db,
        user,
        character,
        objective=body.objective,
        reason=body.reason,
        companions=body.companions,
    )
    db.commit()
    return player_request_out(db, request)


@router.post("/quest-requests/{request_id}/withdraw")
def withdraw_request(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PlayerRequestOut:
    request = db.get(QuestRequest, request_id)
    if request is None:
        raise not_found("request")
    own_character(db, user, request.character_id)
    quests.withdraw(db, user, request)
    db.commit()
    return player_request_out(db, request)


@router.get("/characters/{character_id}/quests/{quest_id}")
def character_quest(
    character_id: uuid.UUID, quest_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> PlayerQuestOut:
    character = own_character(db, user, character_id)
    quest, role = seen_quest(db, character, quest_id)
    return player_quest_out(db, character, quest, role)


@router.post("/characters/{character_id}/quests/{quest_id}/join")
def join_quest(
    character_id: uuid.UUID, quest_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> PlayerQuestOut:
    """Join a quest shared with or offered to the character."""
    character = own_character(db, user, character_id)
    quest, _ = seen_quest(db, character, quest_id)
    quests.join(db, user, quest, character)
    db.commit()
    quest, role = seen_quest(db, character, quest_id)
    return player_quest_out(db, character, quest, role)


@router.get("/characters/{character_id}/quests/{quest_id}/share-choices")
def share_choices(
    character_id: uuid.UUID, quest_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[QuestCharacterChoice]:
    """The troupe's other characters the leader can share the quest with."""
    character = own_character(db, user, character_id)
    quest, role = seen_quest(db, character, quest_id)
    if role != "leader":
        raise forbidden()
    taken = {c.id for _, c in quests.members(db, quest)} | {character.id}
    return [
        QuestCharacterChoice(id=c.id, name=c.name, kind=c.kind)
        for c in quests.troupe_characters(db, quest.troupe_id)
        if c.id not in taken
    ]


@router.post("/characters/{character_id}/quests/{quest_id}/share")
def share_quest(
    character_id: uuid.UUID, quest_id: uuid.UUID, body: ShareIn, db: DbSession, user: CurrentUser
) -> PlayerQuestOut:
    """The leader's player shares the quest with other characters of the troupe, who
    may then see it and join."""
    character = own_character(db, user, character_id)
    quest, role = seen_quest(db, character, quest_id)
    if role != "leader":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only its leader shares a quest.")
    quests.ensure_active(quest)
    chosen = list(db.scalars(select(Character).where(Character.id.in_(body.character_ids))))
    if len(chosen) != len(set(body.character_ids)):
        raise not_found("character")
    quests.add_members(db, user, quest, chosen, joined=False)
    db.commit()
    return player_quest_out(db, character, quest, role)


@router.put("/characters/{character_id}/quests/{quest_id}/tale")
def tell_tale(
    character_id: uuid.UUID, quest_id: uuid.UUID, body: TaleIn, db: DbSession, user: CurrentUser
) -> PlayerQuestOut:
    """The leader's player tells the tale of a quest that has ended (p. 102)."""
    character = own_character(db, user, character_id)
    quest, role = seen_quest(db, character, quest_id)
    if role != "leader":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Its leader's player tells the tale.")
    quests.write_tale(db, user, quest, body.tale, staff=False, approve=False)
    db.commit()
    return player_quest_out(db, character, quest, role)


# --- staff: requests -----------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/quest-requests")
def quest_requests(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    show: quests.Show = "open",
) -> list[QuestRequestOut]:
    """The troupe's quest requests, oldest first: open ones, new ones, those assigned
    to the reader or to any narrator, those whose quest waits to be sent, or those
    answered."""
    troupe = staff_troupe(db, user, troupe_id)
    return [request_out(db, user, troupe, r) for r in quests.queue(db, user, troupe, show)]


@router.put("/quest-requests/{request_id}/assignment")
def assign_request(
    request_id: uuid.UUID, body: AssignmentIn, db: DbSession, user: CurrentUser
) -> QuestRequestOut:
    request, troupe = staff_request(db, user, request_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_QUESTS)
    quests.assign(db, user, troupe, request, body.user_id, body.any_narrator)
    db.commit()
    return request_out(db, user, troupe, request)


@router.post("/quest-requests/{request_id}/accept")
def accept_request(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuestRequestOut:
    """A narrator takes a request assigned to any narrator."""
    request, troupe = staff_request(db, user, request_id)
    quests.accept(db, user, request)
    db.commit()
    return request_out(db, user, troupe, request)


@router.post("/quest-requests/{request_id}/answer")
def answer_request(
    request_id: uuid.UUID, body: RequestAnswerIn, db: DbSession, user: CurrentUser
) -> QuestRequestOut:
    """Answer without a quest: not needed, which gives the slot back, or refused."""
    request, troupe = staff_request(db, user, request_id)
    if not quests.may_work_on(db, user, troupe, request):
        raise forbidden()
    if body.outcome == "done" and request.kind not in ("repair", "whose"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Answer it with a quest, as not needed, or refuse it.",
        )
    quests.answer(db, user, request, body.outcome, body.note)
    db.commit()
    return request_out(db, user, troupe, request)


@router.post("/quest-requests/{request_id}/read")
def read_request(request_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuestRequestOut:
    request, troupe = staff_request(db, user, request_id)
    quests.mark_read(request, user)
    db.commit()
    return request_out(db, user, troupe, request)


# --- staff: quests -------------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/quests")
def troupe_quests(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    show: Literal["open", "draft", "active", "ended", "closed", "all"] = "open",
) -> list[QuestRowOut]:
    """The troupe's quests, newest first. A narrator sees those assigned to them or to
    any narrator."""
    troupe = staff_troupe(db, user, troupe_id)
    states = {
        "open": ("draft", "active"),
        "draft": ("draft",),
        "active": ("active",),
        "ended": ("completed", "failed"),
        "closed": ("closed",),
        "all": ("draft", "active", "completed", "failed", "closed"),
    }[show]
    found = db.scalars(
        select(Quest)
        .where(Quest.troupe_id == troupe.id, Quest.status.in_(states))
        .order_by(Quest.created_at.desc())
    )
    running = quests.is_running(db, user, troupe)
    return [quest_row(db, q) for q in found if running or quests.narrator_may_see(user, q)]


@router.get("/troupes/{troupe_id}/quest-characters")
def quest_characters(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[QuestCharacterChoice]:
    """The troupe's active characters, to lead, join or meet a quest's requirements."""
    troupe = staff_troupe(db, user, troupe_id)
    return [
        QuestCharacterChoice(id=c.id, name=c.name, kind=c.kind)
        for c in quests.troupe_characters(db, troupe.id)
    ]


@router.post("/troupes/{troupe_id}/quests", status_code=status.HTTP_201_CREATED)
def build_quest(troupe_id: uuid.UUID, body: QuestIn, db: DbSession, user: CurrentUser) -> QuestOut:
    """Build a quest, in draft: from a request, or from nothing. Running staff build
    any; a narrator builds from a request assigned to them."""
    troupe = staff_troupe(db, user, troupe_id)
    request = None
    if body.request_id is not None:
        request = db.get(QuestRequest, body.request_id)
        if request is None or request.troupe_id != troupe.id:
            raise not_found("request")
        if not quests.may_work_on(db, user, troupe, request):
            raise forbidden()
    else:
        require_troupe_action(db, user, troupe, TroupeAction.MANAGE_QUESTS)
    texts = texts_from(body)
    quest = quests.create(
        db, user, troupe, fields_from(body), request=request, scenario_texts=texts or ()
    )
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.get("/quests/{quest_id}")
def read_quest(quest_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuestOut:
    quest, troupe = staff_quest(db, user, quest_id)
    return quest_out(db, user, troupe, quest)


@router.put("/quests/{quest_id}")
def change_quest(quest_id: uuid.UUID, body: QuestIn, db: DbSession, user: CurrentUser) -> QuestOut:
    quest, troupe = worked_quest(db, user, quest_id)
    quests.change(db, user, troupe, quest, fields_from(body), texts_from(body))
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.put("/quests/{quest_id}/assignment")
def assign_quest(
    quest_id: uuid.UUID, body: AssignmentIn, db: DbSession, user: CurrentUser
) -> QuestOut:
    quest, troupe = running_quest(db, user, quest_id)
    quests.assign(db, user, troupe, quest, body.user_id, body.any_narrator)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/accept")
def accept_quest(quest_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuestOut:
    quest, troupe = staff_quest(db, user, quest_id)
    quests.accept(db, user, quest)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/read")
def read_mark_quest(quest_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuestOut:
    quest, troupe = staff_quest(db, user, quest_id)
    quests.mark_read(quest, user)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/requirements", status_code=status.HTTP_201_CREATED)
def add_requirement(
    quest_id: uuid.UUID, body: RequirementIn, db: DbSession, user: CurrentUser
) -> QuestOut:
    quest, troupe = worked_quest(db, user, quest_id)
    quests.add_requirement(db, user, quest, body.options)
    db.commit()
    return quest_out(db, user, troupe, quest)


def requirement_of(db: DbSession, quest: Quest, requirement_id: uuid.UUID) -> QuestRequirement:
    requirement = db.get(QuestRequirement, requirement_id)
    if requirement is None or requirement.quest_id != quest.id:
        raise not_found("requirement")
    return requirement


@router.put("/quests/{quest_id}/requirements/{requirement_id}")
def change_requirement(
    quest_id: uuid.UUID,
    requirement_id: uuid.UUID,
    body: RequirementIn,
    db: DbSession,
    user: CurrentUser,
) -> QuestOut:
    quest, troupe = worked_quest(db, user, quest_id)
    quests.change_requirement(
        db, user, quest, requirement_of(db, quest, requirement_id), body.options
    )
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.delete("/quests/{quest_id}/requirements/{requirement_id}")
def remove_requirement(
    quest_id: uuid.UUID, requirement_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> QuestOut:
    quest, troupe = worked_quest(db, user, quest_id)
    quests.remove_requirement(db, user, quest, requirement_of(db, quest, requirement_id))
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/requirements/{requirement_id}/met")
def meet_requirement(
    quest_id: uuid.UUID,
    requirement_id: uuid.UUID,
    body: MetIn,
    db: DbSession,
    user: CurrentUser,
) -> QuestOut:
    """Mark a requirement met by a character, a party member or a patron, spending
    what its alternative expends."""
    quest, troupe = running_quest(db, user, quest_id)
    character = db.get(Character, body.character_id)
    if character is None:
        raise not_found("character")
    quests.meet(
        db, user, troupe, quest, requirement_of(db, quest, requirement_id), character, body.option
    )
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.delete("/quests/{quest_id}/requirements/{requirement_id}/met")
def unmeet_requirement(
    quest_id: uuid.UUID, requirement_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> QuestOut:
    quest, troupe = running_quest(db, user, quest_id)
    quests.unmeet(db, user, quest, requirement_of(db, quest, requirement_id))
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/send")
def send_quest(quest_id: uuid.UUID, db: DbSession, user: CurrentUser) -> QuestOut:
    """Send the requirements to the leader and party: the quest is under way."""
    quest, troupe = running_quest(db, user, quest_id)
    quests.send(db, user, quest)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/members")
def add_members(quest_id: uuid.UUID, body: MembersIn, db: DbSession, user: CurrentUser) -> QuestOut:
    """Offer the quest to characters, who may join; or put them in its party."""
    quest, troupe = running_quest(db, user, quest_id)
    chosen = list(db.scalars(select(Character).where(Character.id.in_(body.character_ids))))
    if len(chosen) != len(set(body.character_ids)):
        raise not_found("character")
    quests.add_members(db, user, quest, chosen, joined=body.joined)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.delete("/quests/{quest_id}/members/{character_id}")
def remove_member(
    quest_id: uuid.UUID, character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> QuestOut:
    quest, troupe = running_quest(db, user, quest_id)
    character = db.get(Character, character_id)
    if character is None:
        raise not_found("character")
    quests.remove_member(db, user, quest, character)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/scenarios/{number}/result")
def send_result(
    quest_id: uuid.UUID, number: int, body: ResultIn, db: DbSession, user: CurrentUser
) -> QuestOut:
    """Send a scenario's result to the party. The last one passed completes the quest."""
    quest, troupe = running_quest(db, user, quest_id)
    scenario = db.scalar(
        select(QuestScenario).where(
            QuestScenario.quest_id == quest.id, QuestScenario.number == number
        )
    )
    if scenario is None:
        raise not_found("scenario")
    quests.send_result(db, user, quest, scenario, body.result, body.text, ends=body.ends)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/close")
def close_quest(quest_id: uuid.UUID, body: NoteIn, db: DbSession, user: CurrentUser) -> QuestOut:
    """Switch the quest off, with a note its characters see."""
    quest, troupe = running_quest(db, user, quest_id)
    quests.close(db, user, quest, body.note)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.put("/quests/{quest_id}/tale")
def staff_tale(quest_id: uuid.UUID, body: TaleIn, db: DbSession, user: CurrentUser) -> QuestOut:
    """Edit the tale, and approve it as the official account."""
    quest, troupe = running_quest(db, user, quest_id)
    quests.write_tale(db, user, quest, body.tale, staff=True, approve=body.approve)
    db.commit()
    return quest_out(db, user, troupe, quest)


@router.post("/quests/{quest_id}/log")
def add_log(quest_id: uuid.UUID, body: LogIn, db: DbSession, user: CurrentUser) -> QuestOut:
    quest, troupe = staff_quest(db, user, quest_id)
    quests.log(db, quest, user, body.text.strip())
    db.commit()
    return quest_out(db, user, troupe, quest)
