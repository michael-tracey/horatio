"""Feeding in a downtime cycle, for storytellers and assistant storytellers: each
clan's difficulty, each character's number and tally, and the answer; with the
optional rules, the troupe's feeding territories and the cycle's Rack."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import audit, downtimes, feeding, rack, territories
from horatio.api.downtimes import (
    FeedingCardOut,
    FeedingIn,
    FeedingNeedOut,
    Humor,
    HumorOut,
    ReceivedOut,
    TerritoryOut,
    card_out,
    cycle_participant,
    feeding_in,
    humors_out,
    need_out,
    received_out,
    staff_cycle,
    staff_troupe,
    territory_out,
)
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, CycleParticipant, DowntimeCycle, Troupe
from horatio.permissions import TroupeAction, can_see_whos_who

router = APIRouter(tags=["feeding"])

Result = Literal["full", "half", "other"]


class PatrolByOut(BaseModel):
    character_id: uuid.UUID
    character_name: str
    actions: int


class FeedingNumbers(BaseModel):
    """A feeding restriction with the Rack (Vol. 2, p. 301): the last digits of the
    card numbers the character may only, or may never, feed from."""

    mode: Literal["only", "never"]
    endings: list[int] = Field(min_length=1, max_length=10)
    # In words: "Only cards ending in 5 or 9".
    text: str = ""


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
    # With Blood Resonance: the humor of the blood it fed on, and its Dyscrasia ("" for
    # none).
    resonance: Humor | None = None
    dyscrasia: str = ""
    answered_at: datetime | None
    delivered: bool
    # With the Rack: the card it took, and its feeding restriction.
    vessel: FeedingCardOut | None = None
    restriction: FeedingNumbers | None = None
    # With feeding territories: where it poached, if it did, who patrolled there, and
    # which of them staff say caught it.
    poaching: str | None = None
    patrols: list[PatrolByOut] = []
    caught_by: list[uuid.UUID] = []


class TerritoryUseOut(TerritoryOut):
    # With book feeding: who feeds there this cycle, which may be more than it holds.
    feeding: list[str] = []
    # Who patrols it this cycle, from submitted downtimes.
    patrols: list[PatrolByOut] = []


class RackOut(BaseModel):
    cards: list[FeedingCardOut]
    # Characters taking part, and the book's number of cards for them (p. 306).
    players: int
    suggested: int


class CycleFeedingOut(BaseModel):
    clans: list[ClanFeedingOut]
    characters: list[CharacterFeedingOut]
    # With Blood Resonance on, the humors and their Dyscrasias to answer with; empty
    # while it is off.
    humors: list[HumorOut] = []
    # With feeding territories on, the troupe's territories and this cycle's use.
    territories: list[TerritoryUseOut] = []
    # With the Rack on, the cycle's Rack.
    rack: RackOut | None = None


class FeedingAdjustmentIn(BaseModel):
    delta: int = Field(ge=-10, le=10)
    reason: str = Field(min_length=1, max_length=300)


class FeedingAnswerIn(BaseModel):
    # None takes the answer back.
    result: Result | None
    # Flavour with a full or half answer; with other, the answer itself.
    reply: str = Field(default="", max_length=2000)
    # With Blood Resonance: the humor of the blood it fed on, and the Dyscrasia it
    # carried, one of that humor's by name ("" for none).
    resonance: Humor | None = None
    dyscrasia: str = Field(default="", max_length=100)
    # With feeding territories: the patrollers who caught it poaching.
    caught_by: list[uuid.UUID] = []


def patrols_out(found: list[feeding.PatrolBy]) -> list[PatrolByOut]:
    return [
        PatrolByOut(character_id=p.character_id, character_name=p.character_name, actions=p.actions)
        for p in found
    ]


def numbers_out(rule: dict[str, object] | None) -> FeedingNumbers | None:
    if not rule:
        return None
    return FeedingNumbers.model_validate({**rule, "text": rack.restriction_text(rule)})


def character_out(
    db: DbSession,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    character: Character,
    show: feeding.Shown,
) -> CharacterFeedingOut | None:
    from horatio.responses import delivered

    basis = feeding.participant_basis(db, participant, character, cycle)
    need = feeding.need(db, cycle, participant, basis)
    if need is None:
        return None
    submission = downtimes.submission_for(db, participant)
    answer = feeding.answer_of(submission)
    counted = feeding.tally(
        db,
        cycle,
        character,
        need,
        submission,
        submitted_only=True,
        with_territories=show.territories,
    )
    taken = rack.taken(db, participant) if show.rack else None
    poached = feeding.poached(db, participant, answer, show)
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
        summary=feeding.summary(db, answer, show=show, participant=participant)
        if not answer.empty or show.rack
        else "",
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
        resonance=submission.feeding_resonance if submission and show.resonance else None,  # type: ignore[arg-type]
        dyscrasia=submission.feeding_dyscrasia if submission and show.resonance else "",
        answered_at=submission.feeding_answered_at if submission else None,
        delivered=submission is not None and delivered(db, submission.id),
        vessel=card_out(db, taken, participant, character, staff=True) if taken else None,
        restriction=numbers_out(character.feeding_numbers) if show.rack else None,
        poaching=poached.name if poached else None,
        patrols=patrols_out(feeding.patrols_of(db, cycle, poached.id, character.id))
        if poached
        else [],
        caught_by=[uuid.UUID(i) for i in submission.feeding_caught_by] if submission else [],
    )


def territories_out(
    db: DbSession, cycle: DowntimeCycle, troupe: Troupe, show: feeding.Shown
) -> list[TerritoryUseOut]:
    """The troupe's territories, with who feeds in each this cycle (book feeding) and
    who patrols it."""
    rows = list(
        db.execute(
            select(downtimes.Submission, Character)
            .join(CycleParticipant, downtimes.Submission.participant_id == CycleParticipant.id)
            .join(Character, CycleParticipant.character_id == Character.id)
            .where(CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None))
            .order_by(Character.name)
        )
    )
    found: list[TerritoryUseOut] = []
    for territory in territories.listed(db, troupe):
        feeding_here = (
            []
            if show.rack
            else [
                c.name for sub, c in rows if feeding.answer_of(sub).territory == str(territory.id)
            ]
        )
        found.append(
            TerritoryUseOut(
                **territory_out(db, territory).model_dump(),
                feeding=feeding_here,
                patrols=patrols_out(feeding.patrols_of(db, cycle, territory.id, uuid.UUID(int=0))),
            )
        )
    return found


def cycle_feeding(db: DbSession, cycle: DowntimeCycle, troupe: Troupe) -> CycleFeedingOut:
    show = feeding.shown(troupe)
    rows = list(
        db.execute(
            select(CycleParticipant, Character)
            .join(Character, CycleParticipant.character_id == Character.id)
            .where(CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None))
            .order_by(Character.name)
        )
    )
    characters = [c for p, ch in rows if (c := character_out(db, cycle, p, ch, show)) is not None]
    counts: dict[str, int] = {}
    for c in characters:
        counts[c.clan] = counts.get(c.clan, 0) + 1
    clans: list[ClanFeedingOut] = []
    for clan in feeding.troupe_clans(db, troupe):
        amount, reason = feeding.clan_difficulty(cycle, clan)
        clans.append(
            ClanFeedingOut(clan=clan, amount=amount, reason=reason, characters=counts.get(clan, 0))
        )
    return CycleFeedingOut(
        clans=clans,
        characters=characters,
        humors=humors_out() if show.resonance else [],
        territories=territories_out(db, cycle, troupe, show) if show.territories else [],
        rack=RackOut(
            cards=[card_out(db, c, staff=True) for c in rack.cards(db, cycle)],
            players=len(characters),
            suggested=rack.suggested(len(characters)),
        )
        if show.rack
        else None,
    )


def feeding_cycle(
    db: DbSession,
    user: CurrentUser,
    cycle_id: uuid.UUID,
    action: TroupeAction = TroupeAction.MANAGE_CYCLES,
) -> tuple[DowntimeCycle, Troupe]:
    """The cycle and its troupe, for its staff, while the troupe tracks feeding."""
    cycle, troupe = staff_cycle(db, user, cycle_id, action)
    if not feeding.tracked(troupe):
        raise feeding.not_tracked()
    return cycle, troupe


@router.get("/cycles/{cycle_id}/feeding")
def read_feeding(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CycleFeedingOut:
    cycle, troupe = feeding_cycle(db, user, cycle_id)
    return cycle_feeding(db, cycle, troupe)


@router.put("/cycles/{cycle_id}/feeding/clans/{clan}")
def set_clan_feeding(
    cycle_id: uuid.UUID, clan: str, body: ClanFeedingIn, db: DbSession, user: CurrentUser
) -> CycleFeedingOut:
    """Set how many feeding actions a clan needs this cycle, with the reason."""
    cycle, troupe = feeding_cycle(db, user, cycle_id)
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
    cycle, troupe = feeding_cycle(db, user, cycle_id, TroupeAction.ADJUST_ALLOWANCES)
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
    """Full Blood next game, half Blood, or something else; with Blood Resonance, the
    Resonance it fed on and any Dyscrasia."""
    cycle, troupe = feeding_cycle(db, user, cycle_id, TroupeAction.ASSIGN_RESPONSES)
    participant = cycle_participant(db, cycle, participant_id)
    character = db.get_one(Character, participant.character_id)
    feeding.write_answer(
        db,
        user,
        cycle,
        troupe,
        participant,
        character,
        body.result,
        body.reply,
        body.resonance,
        body.dyscrasia,
        body.caught_by,
    )
    db.commit()
    return cycle_feeding(db, cycle, troupe)


# --- the Rack -----------------------------------------------------------------------------


class DealIn(BaseModel):
    # Cards to lay on the Rack, and how many in 100 carry a Dyscrasia.
    count: int = Field(ge=0, le=200)
    share: int = Field(default=50, ge=0, le=100)


class CardIn(BaseModel):
    resonance: Humor
    dyscrasia: str = Field(default="", max_length=100)
    descriptor: str = Field(default="", max_length=300)


def rack_cycle(
    db: DbSession, user: CurrentUser, cycle_id: uuid.UUID, action: TroupeAction
) -> tuple[DowntimeCycle, Troupe]:
    cycle, troupe = feeding_cycle(db, user, cycle_id, action)
    if not rack.on(troupe):
        raise HTTPException(status.HTTP_409_CONFLICT, "This troupe doesn't play the Rack.")
    return cycle, troupe


@router.post("/cycles/{cycle_id}/rack")
def deal_rack(
    cycle_id: uuid.UUID, body: DealIn, db: DbSession, user: CurrentUser
) -> CycleFeedingOut:
    """Lay out cards on the cycle's Rack, at random: and each territory's, and each
    character's Herd cards, if they have none yet."""
    cycle, troupe = rack_cycle(db, user, cycle_id, TroupeAction.MANAGE_CYCLES)
    rack.deal(db, user, cycle, troupe, body.count, body.share)
    db.commit()
    return cycle_feeding(db, cycle, troupe)


@router.put("/cycles/{cycle_id}/rack/{card_id}")
def change_card(
    cycle_id: uuid.UUID, card_id: uuid.UUID, body: CardIn, db: DbSession, user: CurrentUser
) -> CycleFeedingOut:
    cycle, troupe = rack_cycle(db, user, cycle_id, TroupeAction.MANAGE_CYCLES)
    card = rack.card_of(db, cycle, card_id)
    rack.change_card(db, cycle, card, body.resonance, body.dyscrasia, body.descriptor)
    db.commit()
    return cycle_feeding(db, cycle, troupe)


@router.delete("/cycles/{cycle_id}/rack/{card_id}")
def remove_card(
    cycle_id: uuid.UUID, card_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CycleFeedingOut:
    cycle, troupe = rack_cycle(db, user, cycle_id, TroupeAction.MANAGE_CYCLES)
    rack.remove_card(db, cycle, rack.card_of(db, cycle, card_id))
    db.commit()
    return cycle_feeding(db, cycle, troupe)


class FeedingNumbersIn(BaseModel):
    # None takes the restriction away.
    rule: FeedingNumbers | None


@router.put("/cycles/{cycle_id}/participants/{participant_id}/feeding-numbers")
def set_feeding_numbers(
    cycle_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: FeedingNumbersIn,
    db: DbSession,
    user: CurrentUser,
) -> CycleFeedingOut:
    """A character's feeding restriction with the Rack, such as Prey Exclusion or the
    Ventrue clan weakness: the card numbers it may only, or never, feed from. It
    stays with the character from cycle to cycle."""
    cycle, troupe = rack_cycle(db, user, cycle_id, TroupeAction.ADJUST_ALLOWANCES)
    participant = cycle_participant(db, cycle, participant_id)
    character = db.get_one(Character, participant.character_id)
    rule = body.rule
    if rule is not None and any(not 0 <= e <= 9 for e in rule.endings):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A last digit is 0 to 9.")
    character.feeding_numbers = (
        {"mode": rule.mode, "endings": sorted(set(rule.endings))} if rule else None
    )
    audit.record(
        db,
        user,
        "downtime.feeding_numbers",
        troupe_id=troupe.id,
        character_id=character.id,
        rule=rack.restriction_text(character.feeding_numbers).lower() or "none",
    )
    db.commit()
    return cycle_feeding(db, cycle, troupe)


# --- feeding territories ------------------------------------------------------------------


class TerritoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    size: Literal["small", "moderate", "notable", "significant", "large"]
    area: str = Field(default="", max_length=300)
    held_by: str = Field(default="", max_length=200)
    holder_ids: list[uuid.UUID] = []


def territory_troupe(
    db: DbSession, user: CurrentUser, troupe_id: uuid.UUID, action: TroupeAction | None
) -> Troupe:
    if action is None:
        troupe = db.get(Troupe, troupe_id)
        if troupe is None or not can_see_whos_who(db, user, troupe):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    else:
        troupe = staff_troupe(db, user, troupe_id, action)
    if not territories.on(troupe):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This troupe doesn't play feeding territories."
        )
    return troupe


def territory_spec(body: TerritoryIn) -> territories.Spec:
    return territories.Spec(body.name, body.size, body.area, body.held_by, body.holder_ids)


@router.get("/troupes/{troupe_id}/feeding-territories")
def read_territories(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[TerritoryOut]:
    """The troupe's feeding territories, which the whole domain knows: for its staff
    and the players of its characters."""
    troupe = territory_troupe(db, user, troupe_id, None)
    return [territory_out(db, t, None) for t in territories.listed(db, troupe)]


@router.post("/troupes/{troupe_id}/feeding-territories", status_code=status.HTTP_201_CREATED)
def add_territory(
    troupe_id: uuid.UUID, body: TerritoryIn, db: DbSession, user: CurrentUser
) -> TerritoryOut:
    troupe = territory_troupe(db, user, troupe_id, TroupeAction.MANAGE_LOCATIONS)
    found = territories.save(db, user, troupe, territory_spec(body), None)
    db.commit()
    return territory_out(db, found)


@router.put("/troupes/{troupe_id}/feeding-territories/{territory_id}")
def change_territory(
    troupe_id: uuid.UUID,
    territory_id: uuid.UUID,
    body: TerritoryIn,
    db: DbSession,
    user: CurrentUser,
) -> TerritoryOut:
    """Change a territory: its size, where it is, or who the Authority assigns it to."""
    troupe = territory_troupe(db, user, troupe_id, TroupeAction.MANAGE_LOCATIONS)
    territory = territories.territory_of(db, troupe, territory_id)
    found = territories.save(db, user, troupe, territory_spec(body), territory)
    db.commit()
    return territory_out(db, found)


@router.delete(
    "/troupes/{troupe_id}/feeding-territories/{territory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_territory(
    troupe_id: uuid.UUID, territory_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    """Revoke a territory, or record it lost: it leaves the list, and is kept."""
    troupe = territory_troupe(db, user, troupe_id, TroupeAction.MANAGE_LOCATIONS)
    territories.archive(db, user, troupe, territories.territory_of(db, troupe, territory_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
