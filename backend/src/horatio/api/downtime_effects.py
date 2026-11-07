"""What a downtime response does besides its words (horatio.downtime_effects): owed
actions on another character, and backgrounds raised or lowered for a while."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from horatio import downtime_effects
from horatio.api.responses import response_item
from horatio.auth.deps import CurrentUser, DbSession
from horatio.downtime_effects import Kind
from horatio.models import Character, Troupe, User
from horatio.permissions import TroupeAction, require_troupe_action, visible_character
from horatio.responses import WorkItem

router = APIRouter(tags=["downtime effects"])


class AppliedOut(BaseModel):
    id: uuid.UUID
    kind: str
    character_name: str
    # "Call of the Hungry Dead: Bram −1".
    text: str


class EffectTargetOut(BaseModel):
    id: uuid.UUID
    name: str


class ResponseEffectsOut(BaseModel):
    applied: list[AppliedOut]
    # Who an effect on another character can be aimed at.
    targets: list[EffectTargetOut]
    # What an indirect attack through this answer costs its target; None for an answer
    # that is not a general influence action.
    indirect_cost: int | None
    # The character's Resources are recovering from overtaxing, so three actions here
    # can halve the wait; and whether that is done already.
    recovering: bool
    halved: bool


class EffectIn(BaseModel):
    kind: Kind
    # The character an effect on another is aimed at.
    character_id: uuid.UUID | None = None


class BackgroundChangeOut(BaseModel):
    # crafts | performance | overtaxed
    source: str
    delta: int
    starts_at: datetime
    # Overtaxed: when its time is up, and the games still to play. None for a boost,
    # which lasts until the troupe's next cycle opens.
    ends_at: datetime | None
    games_left: int


class BackgroundNowOut(BaseModel):
    """A background raised or lowered for now: "Resources 3 (+1 this month, Crafts)"."""

    trait: str
    # On the sheet, and as it stands now.
    rating: int
    now: int
    changes: list[BackgroundChangeOut]


def background_changes(db: DbSession, character: Character) -> list[BackgroundNowOut]:
    return [
        BackgroundNowOut(
            trait=c.trait,
            rating=c.rating,
            now=c.now,
            changes=[
                BackgroundChangeOut(
                    source=change.source,
                    delta=change.delta,
                    starts_at=change.starts_at,
                    ends_at=held.ends_at,
                    games_left=held.games_left,
                )
                for change, held in c.changes
            ],
        )
        for c in downtime_effects.changed(db, character)
    ]


def effects_out(db: DbSession, item: WorkItem, troupe: Troupe) -> ResponseEffectsOut:
    overtaxed = downtime_effects.overtaxed_now(db, item.character)
    return ResponseEffectsOut(
        applied=[AppliedOut(**vars(a)) for a in downtime_effects.applied(db, item)],
        targets=[
            EffectTargetOut(id=c.id, name=c.name)
            for c in downtime_effects.target_choices(db, troupe)
        ],
        indirect_cost=downtime_effects.indirect_cost(db, item),
        recovering=overtaxed is not None,
        halved=overtaxed is not None and overtaxed.halved_by_response_id is not None,
    )


def staff_item(db: DbSession, user: User, response_id: uuid.UUID) -> tuple[WorkItem, Troupe]:
    """A response, for storytellers and assistants, who change allowances."""
    item, troupe = response_item(db, user, response_id)
    require_troupe_action(db, user, troupe, TroupeAction.ADJUST_ALLOWANCES)
    return item, troupe


@router.get("/responses/{response_id}/effects")
def read_effects(response_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ResponseEffectsOut:
    """What staff have applied from this response, and what they can."""
    item, troupe = staff_item(db, user, response_id)
    return effects_out(db, item, troupe)


@router.post("/responses/{response_id}/effects")
def apply_effect(
    response_id: uuid.UUID, body: EffectIn, db: DbSession, user: CurrentUser
) -> ResponseEffectsOut:
    item, troupe = staff_item(db, user, response_id)
    downtime_effects.apply(db, user, troupe, item, body.kind, body.character_id)
    db.commit()
    return effects_out(db, item, troupe)


@router.delete("/responses/{response_id}/effects/{effect_id}")
def remove_effect(
    response_id: uuid.UUID, effect_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> ResponseEffectsOut:
    item, troupe = staff_item(db, user, response_id)
    downtime_effects.remove(db, user, troupe, item, effect_id)
    db.commit()
    return effects_out(db, item, troupe)


@router.get("/characters/{character_id}/background-changes")
def read_background_changes(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[BackgroundNowOut]:
    """The character's backgrounds raised or lowered for now, for its sheet."""
    return background_changes(db, visible_character(db, user, character_id))
