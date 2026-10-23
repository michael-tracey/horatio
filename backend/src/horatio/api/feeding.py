"""Feeding in a downtime cycle, for storytellers and assistant storytellers: each
clan's difficulty, each character's number and tally, and the answer."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import downtimes, feeding
from horatio.api.downtimes import (
    FeedingIn,
    FeedingNeedOut,
    ReceivedOut,
    cycle_participant,
    feeding_in,
    need_out,
    received_out,
    staff_cycle,
)
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, CycleParticipant, DowntimeCycle, Troupe
from horatio.permissions import TroupeAction

router = APIRouter(tags=["feeding"])

Result = Literal["full", "half", "other"]


class ClanFeedingOut(BaseModel):
    clan: str
    amount: int
    reason: str
    # Characters of the clan taking part.
    characters: int


class ClanFeedingIn(BaseModel):
    amount: int = Field(ge=0, le=10)
    reason: str = Field(default="", max_length=300)


class TallyPartOut(BaseModel):
    label: str
    amount: int


class TallyOut(BaseModel):
    needed: int
    parts: list[TallyPartOut]
    total: int
    # Enough to come to the next game at full Blood. Advisory only.
    enough: bool


class FeedingAdjustmentOut(BaseModel):
    delta: int
    reason: str


class CharacterFeedingOut(BaseModel):
    participant_id: uuid.UUID
    character_id: uuid.UUID
    character_name: str
    clan: str
    need: FeedingNeedOut
    herd: int
    adjustments: list[FeedingAdjustmentOut]
    submission_status: str | None
    answer: FeedingIn
    # The answer in one line: "1 feeding action (the docks) · Herd: 2 to Bram".
    summary: str
    received: list[ReceivedOut]
    # Counting only gifts from submitted downtimes.
    tally: TallyOut
    # The storytellers' answer, once given.
    result: Result | None
    reply: str
    working: str
    answered_at: datetime | None
    delivered: bool


class CycleFeedingOut(BaseModel):
    clans: list[ClanFeedingOut]
    characters: list[CharacterFeedingOut]


class FeedingAdjustmentIn(BaseModel):
    delta: int = Field(ge=-10, le=10)
    reason: str = Field(min_length=1, max_length=300)


class FeedingAnswerIn(BaseModel):
    # None takes the answer back.
    result: Result | None
    # Flavour with a full or half answer; with other, the answer itself.
    reply: str = Field(default="", max_length=2000)


def character_out(
    db: DbSession, cycle: DowntimeCycle, participant: CycleParticipant, character: Character
) -> CharacterFeedingOut | None:
    from horatio.responses import delivered

    basis = feeding.participant_basis(db, participant, character, cycle)
    need = feeding.need(db, cycle, participant, basis)
    if need is None:
        return None
    submission = downtimes.submission_for(db, participant)
    answer = feeding.answer_of(submission)
    counted = feeding.tally(db, cycle, character, need, submission, submitted_only=True)
    return CharacterFeedingOut(
        participant_id=participant.id,
        character_id=character.id,
        character_name=character.name,
        clan=basis["clan"],
        need=need_out(need),
        herd=int(basis.get("herd", 0)),
        adjustments=[
            FeedingAdjustmentOut(delta=a.delta, reason=a.reason)
            for a in feeding.adjustments(db, participant)
        ],
        submission_status=submission.status if submission else None,
        answer=feeding_in(answer),
        summary=feeding.summary(db, answer) if not answer.empty else "",
        received=received_out(feeding.received(db, cycle, character.id)),
        tally=TallyOut(
            needed=counted.needed,
            parts=[TallyPartOut(label=label, amount=n) for label, n in counted.parts],
            total=counted.total,
            enough=counted.enough,
        ),
        result=submission.feeding_result if submission else None,  # type: ignore[arg-type]
        reply=submission.feeding_reply if submission else "",
        working=submission.feeding_working if submission else "",
        answered_at=submission.feeding_answered_at if submission else None,
        delivered=submission is not None and delivered(db, submission.id),
    )


def cycle_feeding(db: DbSession, cycle: DowntimeCycle, troupe: Troupe) -> CycleFeedingOut:
    rows = db.execute(
        select(CycleParticipant, Character)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None))
        .order_by(Character.name)
    )
    characters = [c for p, ch in rows if (c := character_out(db, cycle, p, ch)) is not None]
    counts: dict[str, int] = {}
    for c in characters:
        counts[c.clan] = counts.get(c.clan, 0) + 1
    clans: list[ClanFeedingOut] = []
    for clan in feeding.troupe_clans(db, troupe):
        amount, reason = feeding.clan_difficulty(cycle, clan)
        clans.append(
            ClanFeedingOut(clan=clan, amount=amount, reason=reason, characters=counts.get(clan, 0))
        )
    return CycleFeedingOut(clans=clans, characters=characters)


@router.get("/cycles/{cycle_id}/feeding")
def read_feeding(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CycleFeedingOut:
    cycle, troupe = staff_cycle(db, user, cycle_id)
    return cycle_feeding(db, cycle, troupe)


@router.put("/cycles/{cycle_id}/feeding/clans/{clan}")
def set_clan_feeding(
    cycle_id: uuid.UUID, clan: str, body: ClanFeedingIn, db: DbSession, user: CurrentUser
) -> CycleFeedingOut:
    """Set how many feeding actions a clan needs this cycle, with the reason."""
    cycle, troupe = staff_cycle(db, user, cycle_id)
    feeding.set_difficulty(db, user, cycle, troupe, clan, body.amount, body.reason)
    db.commit()
    return cycle_feeding(db, cycle, troupe)


@router.post("/cycles/{cycle_id}/participants/{participant_id}/feeding-adjustments")
def adjust_feeding(
    cycle_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: FeedingAdjustmentIn,
    db: DbSession,
    user: CurrentUser,
) -> CycleFeedingOut:
    """Change one character's feeding number for this cycle, with a reason."""
    cycle, troupe = staff_cycle(db, user, cycle_id, TroupeAction.ADJUST_ALLOWANCES)
    participant = cycle_participant(db, cycle, participant_id)
    feeding.adjust(db, user, participant, troupe, body.delta, body.reason)
    db.commit()
    return cycle_feeding(db, cycle, troupe)


@router.put("/cycles/{cycle_id}/participants/{participant_id}/feeding-answer")
def answer_feeding(
    cycle_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: FeedingAnswerIn,
    db: DbSession,
    user: CurrentUser,
) -> CycleFeedingOut:
    """Full Blood next game, half Blood, or something else."""
    cycle, troupe = staff_cycle(db, user, cycle_id, TroupeAction.ASSIGN_RESPONSES)
    participant = cycle_participant(db, cycle, participant_id)
    character = db.get_one(Character, participant.character_id)
    feeding.write_answer(db, user, cycle, troupe, participant, character, body.result, body.reply)
    db.commit()
    return cycle_feeding(db, cycle, troupe)
