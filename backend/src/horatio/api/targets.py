"""Downtime actions aimed at characters, for the storytellers and assistant
storytellers who resolve them (horatio.targets)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import responses, targets
from horatio.api.downtimes import staff_cycle
from horatio.api.responses import PairOut, WorkItemOut, item_out, pair_out, response_item
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import TroupeAction, require_troupe_action

router = APIRouter(tags=["targets"])


class AimedOut(BaseModel):
    """One action aimed at a character."""

    response_id: uuid.UUID
    character_id: uuid.UUID
    character_name: str
    question: str
    answer: str
    # Who else it is aimed at.
    also: list[str]
    # cancel | watch
    counter: str | None
    # The target's Haven has Location, so it costs two actions unless it isn't
    # against them.
    located: bool
    not_against: bool
    # A Cancel or Watch: the target's action staff paired it with.
    paired: PairOut | None
    status: str


class TargetOut(BaseModel):
    character_id: uuid.UUID
    character_name: str
    actions: list[AimedOut]
    # Its own actions this cycle, to pair a Cancel or Watch with.
    own: list[PairOut]


class NotAgainstIn(BaseModel):
    not_against: bool


class PairingIn(BaseModel):
    # The target's action, by its response; None to undo the pairing.
    response_id: uuid.UUID | None


@router.get("/cycles/{cycle_id}/aimed")
def aimed(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[TargetOut]:
    """Each character the cycle's submitted actions are aimed at, by name, with those
    actions: who, which question, and the answer."""
    cycle, _ = staff_cycle(db, user, cycle_id, TroupeAction.ASSIGN_RESPONSES)
    found = targets.by_target(db, cycle)
    names = targets.names_of(db, [a.item.answer.structured for t in found for a in t.actions])
    return [
        TargetOut(
            character_id=t.character.id,
            character_name=t.character.name,
            actions=[
                AimedOut(
                    response_id=a.item.response.id,
                    character_id=a.item.character.id,
                    character_name=a.item.character.name,
                    question=a.item.question.prompt,
                    answer=a.item.answer.body,
                    also=[
                        names.get(other, "?")
                        for other in targets.aimed_at(a.item.answer.structured)
                        if other != t.character.id
                    ],
                    counter=targets.counter_of(a.item.answer.structured),
                    located=a.located,
                    not_against=a.item.answer.not_against,
                    paired=pair_out(a.paired) if a.paired else None,
                    status=a.item.response.status,
                )
                for a in t.actions
            ],
            own=[pair_out(i) for i in t.own if targets.counter_of(i.answer.structured) is None],
        )
        for t in found
    ]


@router.put("/responses/{response_id}/not-against")
def set_not_against(
    response_id: uuid.UUID, body: NotAgainstIn, db: DbSession, user: CurrentUser
) -> WorkItemOut:
    """Say the action isn't against those it is aimed at, such as a friendly visit,
    so a Haven's Location doesn't double it; or that it is after all."""
    item, troupe = response_item(db, user, response_id)
    require_troupe_action(db, user, troupe, TroupeAction.ASSIGN_RESPONSES)
    targets.set_not_against(db, user, item, troupe, body.not_against)
    db.commit()
    return item_out(db, item, running=True)


@router.put("/responses/{response_id}/pairing")
def set_pairing(
    response_id: uuid.UUID, body: PairingIn, db: DbSession, user: CurrentUser
) -> WorkItemOut:
    """Pair a Cancel or Watch with the action of its target's it works on."""
    item, troupe = response_item(db, user, response_id)
    require_troupe_action(db, user, troupe, TroupeAction.ASSIGN_RESPONSES)
    paired = responses.item_for(db, body.response_id) if body.response_id else None
    if body.response_id and paired is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such response.")
    targets.pair(db, user, item, troupe, paired)
    db.commit()
    return item_out(db, item, running=True)
