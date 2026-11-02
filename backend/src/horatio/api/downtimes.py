"""Downtime cycles for staff, and downtime forms for players."""

import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import (
    downtimes,
    feeding,
    influence,
    pictures,
    quest_actions,
    quests,
    rack,
    resonance,
    social_age,
    territories,
    xp_range,
)
from horatio.api.influence import InfluenceStandingOut, standing_out
from horatio.api.sheets import players_character
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Character,
    CycleParticipant,
    DowntimeCycle,
    FeedingCard,
    FeedingTerritory,
    Quest,
    Question,
    Submission,
    Troupe,
    User,
    XpEntry,
)
from horatio.permissions import TroupeAction, require_troupe_action
from horatio.rules import feeding as feeding_rules

router = APIRouter(tags=["downtimes"])

AnswerType = Literal["long_text", "short_text", "choice", "number", "yes_no"]
Humor = Literal["choleric", "melancholic", "phlegmatic", "sanguine"]


class QuestionIn(BaseModel):
    id: uuid.UUID | None = None
    # An action question, a custom one, or the Quest action (horatio.quest_actions).
    kind: Literal["action", "custom", "quest"]
    # The kind of action it spends; for the Quest action, general unless the troupe
    # chooses another.
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


class CycleClose(BaseModel):
    # Also add the cycle's XP for completing it to the troupe's XP ceiling.
    add_to_ceiling: bool = True


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
    # The troupe's action kinds, key to name, for the form's questions to spend.
    action_kinds: dict[str, str] = {}
    # The troupe runs quests, so its form may have the Quest action.
    quests_enabled: bool = False
    # The troupe tracks feeding (horatio.feeding), so the cycle has its Feeding tab.
    feeding: bool = True


class CycleSummaryOut(BaseModel):
    """A cycle in the troupe's list: when it is due and how far it has got."""

    id: uuid.UUID
    name: str
    status: str
    closes_at: datetime
    grace_ends_at: datetime
    participants: int
    submitted: int
    responses: int
    written: int


class AllowanceLineOut(BaseModel):
    action_kind: str
    source: str
    amount: int
    # What the actions mean (Hunted's are owed to staying hidden, and what not
    # spending them does).
    note: str = ""


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
    # Who plays it, to chase.
    player_id: uuid.UUID
    player_handle: str
    allowance: dict[str, int]
    breakdown: list[AllowanceLineOut]
    adjustments: list[AdjustmentOut]
    # Actions taken off beyond the allowance, which stops at zero: more influence
    # spent at games than the month allows.
    shortfall: dict[str, int]
    removed: bool
    late_accepted: bool
    submission_status: str | None
    submitted_late: bool
    # When the player last saved the form, and when they submitted it.
    saved_at: datetime | None
    submitted_at: datetime | None
    # The XP given for completing this downtime, once submitted.
    completion_xp_awarded: int | None


class CharacterChoice(BaseModel):
    character_id: uuid.UUID


class ParticipantChoiceOut(BaseModel):
    """A character staff can add to an open cycle."""

    character_id: uuid.UUID
    name: str
    player_handle: str
    # Taken out of this cycle earlier: adding it puts it back.
    removed: bool


class RemindedOut(BaseModel):
    players: int
    characters: int


class ReminderOut(BaseModel):
    at: datetime
    by: str
    # How many players it reached.
    players: int


class AdjustmentIn(BaseModel):
    action_kind: str
    delta: int
    reason: str = Field(min_length=1)


class NeedLineOut(BaseModel):
    """One reason in a character's feeding number: its clan's number, a trait, or
    a storyteller's adjustment."""

    source: str
    amount: int
    kind: Literal["clan", "trait", "adjustment"]
    note: str
    page: str | None
    # As the form shows it: "Gangrel 1", "Disease Carrier +1".
    text: str


class FeedingNeedOut(BaseModel):
    needed: int
    lines: list[NeedLineOut]
    # What each dot of Herd counts for: 0 when the character cannot use Herd.
    herd_factor: int
    # No feeding brings the character to full Blood.
    always_half: bool


class GiftIn(BaseModel):
    character_id: uuid.UUID
    amount: int = Field(ge=0, le=20)


class PatrolIn(BaseModel):
    territory_id: uuid.UUID
    actions: int = Field(ge=0, le=20)


class FeedingIn(BaseModel):
    """The Feeding section of the form."""

    # Downtime actions spent feeding, out of the general actions.
    actions: int = Field(default=0, ge=0, le=20)
    where: str = Field(default="", max_length=500)
    # How the character's Herd dots are shared out; never more than its rating.
    herd_own: int = Field(default=0, ge=0, le=20)
    gifts: list[GiftIn] = []
    herd_saved: int = Field(default=0, ge=0, le=20)
    herd_other: int = Field(default=0, ge=0, le=20)
    herd_other_text: str = Field(default="", max_length=500)
    # With Blood Resonance: the humor the character hunts for, "" for any.
    resonance: Humor | Literal[""] = ""
    # With feeding territories and book feeding: the territory it feeds in, by id, ""
    # for none; and the downtime actions it spends patrolling the territories it holds.
    territory: str = Field(default="", max_length=40)
    patrols: list[PatrolIn] = []


class TerritoryOut(BaseModel):
    """A feeding territory (horatio.territories), as the domain knows it."""

    id: uuid.UUID
    name: str
    size: Literal["small", "moderate", "notable", "significant", "large"]
    # "Small", and the vessels it holds.
    size_name: str
    vessels: int
    area: str
    # Who the proclamation reserves it for, in its words.
    held_by: str
    holder_ids: list[uuid.UUID]
    holders: list[str]
    # The character asking holds it (on the downtime form).
    mine: bool = False


class FeedingCardOut(BaseModel):
    """A Feeding Card (horatio.rack): a vessel to feed on."""

    id: uuid.UUID
    number: int
    # rack | territory | herd | hunt
    source: Literal["rack", "territory", "herd", "hunt"]
    resonance: Humor
    dyscrasia: str
    # What its Dyscrasia does, in a line.
    dyscrasia_summary: str
    descriptor: str
    territory_id: uuid.UUID | None
    territory_name: str | None
    # The character asking took it (on the downtime form); its feeding restriction
    # lets it feed there.
    mine: bool = False
    suits: bool = True
    # For staff: who took it, and who it was dealt to.
    taken_by: str | None = None
    dealt_to: str | None = None


class DyscrasiaOut(BaseModel):
    name: str
    # What it does, in a line.
    summary: str


class HumorOut(BaseModel):
    """One of Blood Resonance's four humors (horatio.resonance)."""

    key: Humor
    name: str
    # The feelings its blood brings: "anger, violence, passion, envy or aggression".
    feelings: str
    dyscrasias: list[DyscrasiaOut]


class ReceivedOut(BaseModel):
    character_id: uuid.UUID
    character_name: str
    amount: int
    # The giver has submitted; until then the gift may change.
    submitted: bool


class RecipientOut(BaseModel):
    character_id: uuid.UUID
    name: str


class MyFeedingOut(BaseModel):
    need: FeedingNeedOut
    # The character's Herd rating when the cycle opened.
    herd: int
    answer: FeedingIn
    received: list[ReceivedOut]
    # Who Herd can be given to: everyone else taking part.
    recipients: list[RecipientOut]
    # A storyteller has answered it, so it can no longer change.
    locked: bool
    # With Blood Resonance on, the humors to hunt for; empty while it is off.
    humors: list[HumorOut] = []
    # With feeding territories on, the domain's territories; empty while it is off.
    territories: list[TerritoryOut] = []
    # With the Rack on: it is played, the cards the character can take (and the one it
    # took), how its hunt outside the Rack went (win | tie | lose, "" before it hunts),
    # and its feeding restriction in words ("" for none).
    rack: bool = False
    cards: list[FeedingCardOut] = []
    hunt: str = ""
    restriction: str = ""


class VesselIn(BaseModel):
    # The card to take, or None to give back the one taken.
    card_id: uuid.UUID | None


class AnswerIn(BaseModel):
    question_id: uuid.UUID
    slot: int = 1
    body: str
    structured: dict[str, Any] | None = None


class QuestChoiceOut(BaseModel):
    """A quest the character can choose for a Quest action."""

    id: uuid.UUID
    name: str
    category: str
    difficulty: int
    downtime_only: bool
    # leader | joined | invited | offered: choosing one it is not in joins it.
    role: str
    # The scenario the party faces next, of how many.
    scenario: int | None
    scenario_count: int


class AnswersIn(BaseModel):
    answers: list[AnswerIn]
    # The Feeding section; left out, it stays as it was.
    feeding: FeedingIn | None = None


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
    # Actions of each kind the allowance cannot cover, where flaws and debts take
    # more than it has.
    short: dict[str, int] = {}
    questions: list[QuestionOut]
    answers: list[AnswerOut]
    status: str  # draft | submitted
    late: bool
    # What submitting earns, and what it did earn once submitted.
    completion_xp: int
    completion_xp_awarded: int | None
    # For each influence type the form asks about: the character's rating,
    # specialisations and the actions it can name.
    influence: list[InfluenceStandingOut] = []
    # The Feeding section, for a character that feeds.
    feeding: MyFeedingOut | None = None
    # The quests its Quest action can name, when the form has one.
    quests: list[QuestChoiceOut] = []
    # Why the downtime is closed to this character though the cycle is open: the
    # troupe's absentee downtimes ask for a game attended lately (horatio.game_xp).
    closed: str | None = None


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
    troupe = db.get_one(Troupe, cycle.troupe_id)
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
        action_kinds=downtimes.troupe_action_kinds(db, troupe),
        quests_enabled=troupe.quests_enabled,
        feeding=feeding.tracked(troupe),
    )


def quest_choices(
    db: DbSession, character: Character, cycle: DowntimeCycle, submission: Submission | None
) -> list[QuestChoiceOut]:
    """The quests the character can choose now, and any its answers already name."""
    found = quest_actions.choices(db, character, cycle)
    offered = {q.id for q, _ in found}
    for answer in downtimes.answers_for(db, submission) if submission else []:
        quest_id = quest_actions.quest_id_of(answer.structured)
        quest = db.get(Quest, quest_id) if quest_id and quest_id not in offered else None
        role = quests.role_of(db, quest, character) if quest else None
        if quest is not None and role is not None:
            found.append((quest, role))
            offered.add(quest.id)
    out: list[QuestChoiceOut] = []
    for quest, role in found:
        scenario = quests.current_scenario(db, quest)
        out.append(
            QuestChoiceOut(
                id=quest.id,
                name=quest.name,
                category=quest.category,
                difficulty=quest.difficulty,
                downtime_only=quest.downtime_only,
                role=role,
                scenario=scenario.number if scenario else None,
                scenario_count=len(quests.scenarios(db, quest)),
            )
        )
    return out


def completion_awarded(db: DbSession, p: CycleParticipant) -> int | None:
    if p.completion_xp_entry_id is None:
        return None
    return db.get_one(XpEntry, p.completion_xp_entry_id).amount


def participant_out(
    db: DbSession,
    p: CycleParticipant,
    found: tuple[Character, User, Submission | None] | None = None,
) -> ParticipantOut:
    """`found`, when the caller has them already: the character, its player and the
    submission."""
    if found is None:
        character = db.get_one(Character, p.character_id)
        found = (character, db.get_one(User, character.player_id), downtimes.submission_for(db, p))
    character, player, submission = found
    return ParticipantOut(
        id=p.id,
        character_id=p.character_id,
        character_name=character.name,
        picture=pictures.picture_url(character.id, character.picture_id),
        clan=social_age.standings(db, [character.id])[character.id].clan,
        player_id=player.id,
        player_handle=player.handle,
        allowance=downtimes.effective_allowance(db, p),
        breakdown=[AllowanceLineOut(**line) for line in p.allowance_breakdown],
        adjustments=[
            AdjustmentOut(action_kind=a.action_kind, delta=a.delta, reason=a.reason)
            for a in downtimes.adjustments(db, p)
        ],
        shortfall=downtimes.shortfall(db, p),
        removed=p.removed_at is not None,
        late_accepted=p.late_accepted_by is not None,
        submission_status=submission.status if submission else None,
        submitted_late=submission.late if submission else False,
        saved_at=submission.updated_at if submission else None,
        submitted_at=submission.submitted_at if submission else None,
        completion_xp_awarded=completion_awarded(db, p),
    )


def need_out(need: feeding_rules.Need) -> FeedingNeedOut:
    return FeedingNeedOut(
        needed=need.needed,
        lines=[
            NeedLineOut(
                source=line.source,
                amount=line.amount,
                kind=line.kind,  # type: ignore[arg-type]  # one of the three
                note=line.note,
                page=line.page,
                text=line.text,
            )
            for line in need.lines
        ],
        herd_factor=need.herd_factor,
        always_half=need.always_half,
    )


def feeding_in(answer: feeding.FeedingAnswer) -> FeedingIn:
    return FeedingIn(
        actions=answer.actions,
        where=answer.where,
        herd_own=answer.herd_own,
        gifts=[GiftIn(character_id=g.character_id, amount=g.amount) for g in answer.gifts],
        herd_saved=answer.herd_saved,
        herd_other=answer.herd_other,
        herd_other_text=answer.herd_other_text,
        resonance=answer.resonance,  # type: ignore[arg-type]  # checked when saved
        territory=answer.territory,
        patrols=[PatrolIn(territory_id=p.territory_id, actions=p.actions) for p in answer.patrols],
    )


def humors_out() -> list[HumorOut]:
    return [
        HumorOut(
            key=h.key,  # type: ignore[arg-type]  # one of the four
            name=h.name,
            feelings=h.feelings,
            dyscrasias=[DyscrasiaOut(name=d.name, summary=d.summary) for d in h.dyscrasias],
        )
        for h in resonance.HUMORS.values()
    ]


def feeding_answer(body: FeedingIn) -> feeding.FeedingAnswer:
    return feeding.FeedingAnswer(
        actions=body.actions,
        where=body.where,
        herd_own=body.herd_own,
        gifts=[feeding.Gift(g.character_id, g.amount) for g in body.gifts],
        herd_saved=body.herd_saved,
        herd_other=body.herd_other,
        herd_other_text=body.herd_other_text,
        resonance=body.resonance,
        territory=body.territory,
        patrols=[feeding.Patrol(p.territory_id, p.actions) for p in body.patrols],
    )


def received_out(found: list[feeding.Received]) -> list[ReceivedOut]:
    return [
        ReceivedOut(
            character_id=r.character_id,
            character_name=r.character_name,
            amount=r.amount,
            submitted=r.submitted,
        )
        for r in found
    ]


def my_feeding_out(
    db: DbSession,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    submission: Submission | None,
) -> MyFeedingOut | None:
    troupe = db.get_one(Troupe, cycle.troupe_id)
    show = feeding.shown(troupe)
    if not show.tracked:
        return None
    basis = feeding.participant_basis(db, participant, character, cycle)
    need = feeding.need(db, cycle, participant, basis)
    if need is None:
        return None
    answer = feeding.answer_of(submission)
    return MyFeedingOut(
        need=need_out(need),
        herd=int(basis.get("herd", 0)),
        answer=feeding_in(answer),
        received=received_out(feeding.received(db, cycle, character.id)),
        recipients=[
            RecipientOut(character_id=i, name=n)
            for i, n in feeding.recipients(db, cycle, character)
        ],
        locked=submission is not None and submission.feeding_result is not None,
        humors=humors_out() if show.resonance else [],
        territories=[territory_out(db, t, character.id) for t in territories.listed(db, troupe)]
        if show.territories
        else [],
        rack=show.rack,
        cards=[
            card_out(db, c, participant, character)
            for c in rack.visible(db, cycle, participant)
            if show.territories or c.source != "territory"
        ]
        if show.rack
        else [],
        hunt=answer.hunt,
        restriction=rack.restriction_text(character.feeding_numbers) if show.rack else "",
    )


def territory_out(
    db: DbSession, territory: FeedingTerritory, asking: uuid.UUID | None = None
) -> TerritoryOut:
    size = territories.SIZES[territory.size]
    return TerritoryOut(
        id=territory.id,
        name=territory.name,
        size=territory.size,  # type: ignore[arg-type]  # checked by the database
        size_name=size.name,
        vessels=size.vessels,
        area=territory.area,
        held_by=territory.held_by,
        holder_ids=[uuid.UUID(i) for i in territory.holder_ids],
        holders=territories.holder_names(db, territory),
        mine=asking is not None and territories.holds(territory, asking),
    )


def card_out(
    db: DbSession,
    card: FeedingCard,
    participant: CycleParticipant | None = None,
    character: Character | None = None,
    *,
    staff: bool = False,
) -> FeedingCardOut:
    carried = resonance.dyscrasia(card.resonance, card.dyscrasia)
    territory = db.get(FeedingTerritory, card.territory_id) if card.territory_id else None

    def name_of(participant_id: uuid.UUID | None) -> str | None:
        if participant_id is None:
            return None
        found = db.get_one(CycleParticipant, participant_id)
        return db.get_one(Character, found.character_id).name

    return FeedingCardOut(
        id=card.id,
        number=card.number,
        source=card.source,  # type: ignore[arg-type]  # checked by the database
        resonance=card.resonance,  # type: ignore[arg-type]  # checked by the database
        dyscrasia=card.dyscrasia,
        dyscrasia_summary=carried.summary if carried else "",
        descriptor=card.descriptor,
        territory_id=card.territory_id,
        territory_name=territory.name if territory else None,
        mine=participant is not None and card.taken_by == participant.id,
        suits=character is None or rack.suits(character, card),
        taken_by=name_of(card.taken_by) if staff else None,
        dealt_to=name_of(card.dealt_to) if staff else None,
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
def list_cycles(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[CycleSummaryOut]:
    staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_CYCLES)
    cycles = list(
        db.scalars(
            select(DowntimeCycle)
            .where(DowntimeCycle.troupe_id == troupe_id)
            .order_by(DowntimeCycle.id.desc())
        )
    )
    counts = downtimes.counts(db, [c.id for c in cycles])
    return [
        CycleSummaryOut(
            id=c.id,
            name=c.name,
            status=c.status,
            closes_at=c.closes_at,
            grace_ends_at=c.grace_ends_at,
            **asdict(counts.get(c.id, downtimes.Counts())),
        )
        for c in cycles
    ]


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
def close_cycle(
    cycle_id: uuid.UUID, db: DbSession, user: CurrentUser, body: CycleClose | None = None
) -> CycleOut:
    cycle, _ = staff_cycle(db, user, cycle_id)
    downtimes.close_cycle(db, user, cycle)
    if body is None or body.add_to_ceiling:
        xp_range.add_downtime(db, user, cycle)
    db.commit()
    return cycle_out(db, cycle)


@router.get("/cycles/{cycle_id}/participants")
def list_participants(
    cycle_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[ParticipantOut]:
    cycle, _ = staff_cycle(db, user, cycle_id)
    rows = db.execute(
        select(CycleParticipant, Character, User, Submission)
        .join(Character, CycleParticipant.character_id == Character.id)
        .join(User, Character.player_id == User.id)
        .outerjoin(Submission, Submission.participant_id == CycleParticipant.id)
        .where(CycleParticipant.cycle_id == cycle.id)
        .order_by(Character.name)
    )
    return [participant_out(db, p, (c, u, s)) for p, c, u, s in rows]


@router.get("/cycles/{cycle_id}/participant-choices")
def participant_choices(
    cycle_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[ParticipantChoiceOut]:
    """The characters that could be added to the cycle."""
    cycle, _ = staff_cycle(db, user, cycle_id)
    removed = set(
        db.scalars(
            select(CycleParticipant.character_id).where(
                CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_not(None)
            )
        )
    )
    return [
        ParticipantChoiceOut(
            character_id=c.id, name=c.name, player_handle=u.handle, removed=c.id in removed
        )
        for c, u in downtimes.addable(db, cycle)
    ]


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


@router.post("/cycles/{cycle_id}/reminders")
def remind(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> RemindedOut:
    """Remind the players whose downtimes are not submitted."""
    cycle, troupe = staff_cycle(db, user, cycle_id)
    reminded = downtimes.remind(db, user, cycle, troupe)
    db.commit()
    return RemindedOut(players=reminded.players, characters=reminded.characters)


@router.get("/cycles/{cycle_id}/reminders")
def list_reminders(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[ReminderOut]:
    """When staff reminded players to submit, newest first."""
    cycle, _ = staff_cycle(db, user, cycle_id)
    return [
        ReminderOut(at=r.at, by=r.by, players=r.players) for r in downtimes.reminders(db, cycle)
    ]


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
    questions = downtimes.visible_questions(db, cycle, character, allowance)
    asked = {influence.type_of(q.action_kind) for q in questions} - {None}
    standings = influence.standings(db, character) if asked else {}
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
        short=downtimes.shortfall(db, participant),
        questions=[question_out(q) for q in questions],
        answers=[
            AnswerOut(question_id=a.question_id, slot=a.slot, body=a.body, structured=a.structured)
            for a in (downtimes.answers_for(db, submission) if submission else [])
        ],
        status=submission.status if submission else "draft",
        late=submission.late if submission else False,
        completion_xp=cycle.completion_xp,
        completion_xp_awarded=completion_awarded(db, participant),
        influence=[standing_out(s) for t, s in standings.items() if t in asked],
        feeding=my_feeding_out(db, character, cycle, participant, submission),
        quests=quest_choices(db, character, cycle, submission)
        if any(q.kind == "quest" for q in questions)
        else [],
        closed=downtimes.closed_to(db, cycle, participant),
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
        feeding_answer(body.feeding) if body.feeding is not None else None,
    )
    db.commit()
    return my_downtime_out(db, character, cycle, participant)


@router.post("/characters/{character_id}/downtime/vessel")
def take_vessel(
    character_id: uuid.UUID, body: VesselIn, db: DbSession, user: CurrentUser
) -> MyDowntime:
    """With the Rack: take a Feeding Card, giving back any taken before, or give it back."""
    character, cycle, participant = my_participation(db, user, character_id)
    troupe = db.get_one(Troupe, cycle.troupe_id)
    if not rack.on(troupe):
        raise HTTPException(status.HTTP_409_CONFLICT, "This troupe doesn't play the Rack.")
    rack.take(
        db,
        cycle,
        troupe,
        participant,
        character,
        downtimes.submission_for(db, participant),
        body.card_id,
    )
    db.commit()
    return my_downtime_out(db, character, cycle, participant)


@router.post("/characters/{character_id}/downtime/hunt")
def hunt_outside_the_rack(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> MyDowntime:
    """With the Rack: hunt outside it, once a cycle. Horatio throws the simple challenge
    and deals 3, 2 or 1 cards to choose from."""
    character, cycle, participant = my_participation(db, user, character_id)
    troupe = db.get_one(Troupe, cycle.troupe_id)
    if not rack.on(troupe):
        raise HTTPException(status.HTTP_409_CONFLICT, "This troupe doesn't play the Rack.")
    submission = downtimes.submission_for(db, participant)
    if submission is None:
        submission = Submission(participant_id=participant.id)
        db.add(submission)
        db.flush()
    rack.hunt(db, cycle, participant, submission)
    db.commit()
    return my_downtime_out(db, character, cycle, participant)


@router.post("/characters/{character_id}/downtime/submit")
def submit(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> MyDowntime:
    character, cycle, participant = my_participation(db, user, character_id)
    downtimes.submit(db, user, character, cycle, participant)
    db.commit()
    return my_downtime_out(db, character, cycle, participant)
