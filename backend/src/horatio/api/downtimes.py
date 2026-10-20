"""Downtime cycles for staff, and downtime forms for players."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import downtimes, pictures, social_age
from horatio.api.sheets import players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    Question,
    Submission,
    Troupe,
    User,
    XpEntry,
)
from horatio.permissions import TroupeAction, require_troupe_action

router = APIRouter(tags=["downtimes"])

AnswerType = Literal["long_text", "short_text", "choice", "number", "yes_no"]


class QuestionIn(BaseModel):
    id: uuid.UUID | None = None
    kind: Literal["action", "custom"]
    action_kind: str | None = None
    prompt: str = Field(min_length=1)
    help_text: str = ""
    answer_type: AnswerType = "long_text"
    options: list[str] = []
    required: bool = False
    max_answers: int | None = None
    visible_to: dict[str, Any] | None = None


class QuestionOut(QuestionIn):
    id: uuid.UUID  # type: ignore[assignment]


class NewCycle(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    closes_at: datetime
    grace_ends_at: datetime
    # XP for completing it; leave out for the troupe's usual amount.
    completion_xp: int | None = Field(default=None, ge=0, le=100)


class CycleChanges(BaseModel):
    completion_xp: int = Field(ge=0, le=100)


class CycleOut(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    name: str
    status: str
    opened_at: datetime | None
    closes_at: datetime
    grace_ends_at: datetime
    closed_at: datetime | None
    # XP each character gets for submitting its downtime.
    completion_xp: int
    questions: list[QuestionOut]


class AllowanceLineOut(BaseModel):
    action_kind: str
    source: str
    amount: int


class AdjustmentOut(BaseModel):
    action_kind: str
    delta: int
    reason: str


class ParticipantOut(BaseModel):
    id: uuid.UUID
    character_id: uuid.UUID
    character_name: str
    # The character's picture (horatio.pictures) and clan, for its placeholder.
    picture: str | None
    clan: str | None
    allowance: dict[str, int]
    breakdown: list[AllowanceLineOut]
    adjustments: list[AdjustmentOut]
    removed: bool
    late_accepted: bool
    submission_status: str | None
    submitted_late: bool
    # The XP given for completing this downtime, once submitted.
    completion_xp_awarded: int | None


class CharacterChoice(BaseModel):
    character_id: uuid.UUID


class AdjustmentIn(BaseModel):
    action_kind: str
    delta: int
    reason: str = Field(min_length=1)


class AnswerIn(BaseModel):
    question_id: uuid.UUID
    slot: int = 1
    body: str
    structured: dict[str, Any] | None = None


class AnswersIn(BaseModel):
    answers: list[AnswerIn]


class AnswerOut(AnswerIn):
    structured: dict[str, Any]  # type: ignore[assignment]


class MyDowntime(BaseModel):
    cycle_id: uuid.UUID
    cycle_name: str
    closes_at: datetime
    grace_ends_at: datetime
    allowance: dict[str, int]
    breakdown: list[AllowanceLineOut]
    adjustments: list[AdjustmentOut]
    questions: list[QuestionOut]
    answers: list[AnswerOut]
    status: str  # draft | submitted
    late: bool
    # What submitting earns, and what it did earn once submitted.
    completion_xp: int
    completion_xp_awarded: int | None


# --- helpers ----------------------------------------------------------------------------


def question_out(q: Question) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        kind=q.kind,  # type: ignore[arg-type]
        action_kind=q.action_kind,
        prompt=q.prompt,
        help_text=q.help_text,
        answer_type=q.answer_type,  # type: ignore[arg-type]
        options=q.options,
        required=q.required,
        max_answers=q.max_answers,
        visible_to=q.visible_to,
    )


def cycle_out(db: DbSession, cycle: DowntimeCycle) -> CycleOut:
    return CycleOut(
        id=cycle.id,
        troupe_id=cycle.troupe_id,
        name=cycle.name,
        status=cycle.status,
        opened_at=cycle.opened_at,
        closes_at=cycle.closes_at,
        grace_ends_at=cycle.grace_ends_at,
        closed_at=cycle.closed_at,
        completion_xp=cycle.completion_xp,
        questions=[question_out(q) for q in downtimes.questions(db, cycle)],
    )


def completion_awarded(db: DbSession, p: CycleParticipant) -> int | None:
    if p.completion_xp_entry_id is None:
        return None
    return db.get_one(XpEntry, p.completion_xp_entry_id).amount


def participant_out(db: DbSession, p: CycleParticipant) -> ParticipantOut:
    character = db.get_one(Character, p.character_id)
    submission = downtimes.submission_for(db, p)
    return ParticipantOut(
        id=p.id,
        character_id=p.character_id,
        character_name=character.name,
        picture=pictures.picture_url(character.id, character.picture_id),
        clan=social_age.standings(db, [character.id])[character.id].clan,
        allowance=downtimes.effective_allowance(db, p),
        breakdown=[AllowanceLineOut(**line) for line in p.allowance_breakdown],
        adjustments=[
            AdjustmentOut(action_kind=a.action_kind, delta=a.delta, reason=a.reason)
            for a in downtimes.adjustments(db, p)
        ],
        removed=p.removed_at is not None,
        late_accepted=p.late_accepted_by is not None,
        submission_status=submission.status if submission else None,
        submitted_late=submission.late if submission else False,
        completion_xp_awarded=completion_awarded(db, p),
    )


def staff_troupe(db: DbSession, user: User, troupe_id: uuid.UUID, action: TroupeAction) -> Troupe:
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    require_troupe_action(db, user, troupe, action)
    return troupe


def staff_cycle(
    db: DbSession,
    user: User,
    cycle_id: uuid.UUID,
    action: TroupeAction = TroupeAction.MANAGE_CYCLES,
) -> tuple[DowntimeCycle, Troupe]:
    cycle = db.get(DowntimeCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such cycle.")
    return cycle, staff_troupe(db, user, cycle.troupe_id, action)


def cycle_participant(
    db: DbSession, cycle: DowntimeCycle, participant_id: uuid.UUID
) -> CycleParticipant:
    participant = db.get(CycleParticipant, participant_id)
    if participant is None or participant.cycle_id != cycle.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such participant.")
    return participant


# --- staff ------------------------------------------------------------------------------


@router.get("/troupes/{troupe_id}/cycles")
def list_cycles(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[CycleOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CYCLES)
    cycles = db.scalars(
        select(DowntimeCycle)
        .where(DowntimeCycle.troupe_id == troupe_id)
        .order_by(DowntimeCycle.id.desc())
    )
    return [cycle_out(db, c) for c in cycles]


@router.post("/troupes/{troupe_id}/cycles", status_code=status.HTTP_201_CREATED)
def create_cycle(
    troupe_id: uuid.UUID, body: NewCycle, db: DbSession, user: CurrentUser
) -> CycleOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CYCLES)
    cycle = downtimes.create_cycle(
        db, user, troupe, body.name, body.closes_at, body.grace_ends_at, body.completion_xp
    )
    db.commit()
    return cycle_out(db, cycle)


@router.get("/cycles/{cycle_id}")
def read_cycle(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CycleOut:
    cycle, _ = staff_cycle(db, user, cycle_id)
    return cycle_out(db, cycle)


@router.patch("/cycles/{cycle_id}")
def change_cycle(
    cycle_id: uuid.UUID, body: CycleChanges, db: DbSession, user: CurrentUser
) -> CycleOut:
    cycle, _ = staff_cycle(db, user, cycle_id)
    downtimes.set_completion_xp(db, user, cycle, body.completion_xp)
    db.commit()
    return cycle_out(db, cycle)


@router.put("/cycles/{cycle_id}/questions")
def replace_questions(
    cycle_id: uuid.UUID, body: list[QuestionIn], db: DbSession, user: CurrentUser
) -> CycleOut:
    cycle, troupe = staff_cycle(db, user, cycle_id)
    downtimes.write_questions(
        db,
        user,
        cycle,
        [downtimes.QuestionSpec(**q.model_dump()) for q in body],
        troupe,
    )
    db.commit()
    return cycle_out(db, cycle)


@router.post("/cycles/{cycle_id}/open")
def open_cycle(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CycleOut:
    cycle, troupe = staff_cycle(db, user, cycle_id)
    downtimes.open_cycle(db, user, cycle, troupe)
    db.commit()
    return cycle_out(db, cycle)


@router.post("/cycles/{cycle_id}/close")
def close_cycle(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CycleOut:
    cycle, _ = staff_cycle(db, user, cycle_id)
    downtimes.close_cycle(db, user, cycle)
    db.commit()
    return cycle_out(db, cycle)


@router.get("/cycles/{cycle_id}/participants")
def list_participants(
    cycle_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[ParticipantOut]:
    cycle, _ = staff_cycle(db, user, cycle_id)
    participants = db.scalars(
        select(CycleParticipant)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(CycleParticipant.cycle_id == cycle.id)
        .order_by(Character.name)
    )
    return [participant_out(db, p) for p in participants]


@router.post("/cycles/{cycle_id}/participants", status_code=status.HTTP_201_CREATED)
def add_participant(
    cycle_id: uuid.UUID, body: CharacterChoice, db: DbSession, user: CurrentUser
) -> ParticipantOut:
    cycle, troupe = staff_cycle(db, user, cycle_id)
    character = db.get(Character, body.character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    participant = downtimes.add_participant(db, user, cycle, troupe, character)
    db.commit()
    return participant_out(db, participant)


@router.delete(
    "/cycles/{cycle_id}/participants/{participant_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_participant(
    cycle_id: uuid.UUID, participant_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> None:
    cycle, troupe = staff_cycle(db, user, cycle_id)
    downtimes.remove_participant(db, user, cycle_participant(db, cycle, participant_id), troupe)
    db.commit()


@router.post(
    "/cycles/{cycle_id}/participants/{participant_id}/adjustments",
    status_code=status.HTTP_201_CREATED,
)
def adjust_allowance(
    cycle_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: AdjustmentIn,
    db: DbSession,
    user: CurrentUser,
) -> ParticipantOut:
    cycle, troupe = staff_cycle(db, user, cycle_id, TroupeAction.ADJUST_ALLOWANCES)
    participant = cycle_participant(db, cycle, participant_id)
    downtimes.adjust_allowance(
        db, user, participant, troupe, body.action_kind, body.delta, body.reason
    )
    db.commit()
    return participant_out(db, participant)


@router.post("/cycles/{cycle_id}/participants/{participant_id}/accept-late")
def accept_late(
    cycle_id: uuid.UUID, participant_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> ParticipantOut:
    cycle, troupe = staff_cycle(db, user, cycle_id)
    participant = cycle_participant(db, cycle, participant_id)
    downtimes.accept_late(db, user, participant, troupe)
    db.commit()
    return participant_out(db, participant)


# --- players ----------------------------------------------------------------------------


def my_participation(
    db: DbSession, user: User, character_id: uuid.UUID
) -> tuple[Character, DowntimeCycle, CycleParticipant]:
    character = players_character(db, user, character_id)
    found = downtimes.current_participation(db, character)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This character has no open downtime.")
    return character, found[0], found[1]


def my_downtime_out(
    db: DbSession, character: Character, cycle: DowntimeCycle, participant: CycleParticipant
) -> MyDowntime:
    allowance = downtimes.effective_allowance(db, participant)
    submission: Submission | None = downtimes.submission_for(db, participant)
    return MyDowntime(
        cycle_id=cycle.id,
        cycle_name=cycle.name,
        closes_at=cycle.closes_at,
        grace_ends_at=cycle.grace_ends_at,
        allowance=allowance,
        breakdown=[AllowanceLineOut(**line) for line in participant.allowance_breakdown],
        adjustments=[
            AdjustmentOut(action_kind=a.action_kind, delta=a.delta, reason=a.reason)
            for a in downtimes.adjustments(db, participant)
        ],
        questions=[
            question_out(q) for q in downtimes.visible_questions(db, cycle, character, allowance)
        ],
        answers=[
            AnswerOut(question_id=a.question_id, slot=a.slot, body=a.body, structured=a.structured)
            for a in (downtimes.answers_for(db, submission) if submission else [])
        ],
        status=submission.status if submission else "draft",
        late=submission.late if submission else False,
        completion_xp=cycle.completion_xp,
        completion_xp_awarded=completion_awarded(db, participant),
    )


@router.get("/characters/{character_id}/downtime")
def my_downtime(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> MyDowntime:
    character, cycle, participant = my_participation(db, user, character_id)
    return my_downtime_out(db, character, cycle, participant)


@router.put("/characters/{character_id}/downtime/answers")
def save_answers(
    character_id: uuid.UUID, body: AnswersIn, db: DbSession, user: CurrentUser
) -> MyDowntime:
    character, cycle, participant = my_participation(db, user, character_id)
    downtimes.save_answers(
        db,
        user,
        character,
        cycle,
        participant,
        [downtimes.AnswerSpec(**a.model_dump()) for a in body.answers],
    )
    db.commit()
    return my_downtime_out(db, character, cycle, participant)


@router.post("/characters/{character_id}/downtime/submit")
def submit(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> MyDowntime:
    character, cycle, participant = my_participation(db, user, character_id)
    downtimes.submit(db, user, character, cycle, participant)
    db.commit()
    return my_downtime_out(db, character, cycle, participant)
