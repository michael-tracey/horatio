"""A troupe's XP floor and ceiling (issue #74): what makes them up, and staff
setting them by hand."""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import xp_range
from horatio.api.troupes import get_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.permissions import TroupeAction, require_troupe_action

router = APIRouter(prefix="/troupes/{troupe_id}/xp-range", tags=["xp range"])


class XpRangeEntryOut(BaseModel):
    id: uuid.UUID
    kind: str  # game | downtime | set
    floor_change: int
    ceiling_change: int
    reason: str
    entered_on: date


class XpRangeOut(BaseModel):
    starting_xp: int
    floor: int
    ceiling: int
    # How many games and downtime cycles added to them, and their XP in all.
    games: int
    game_xp: int
    downtimes: int
    downtime_xp: int
    # What setting them by hand has added (negative: taken away).
    set_floor: int
    set_ceiling: int
    entries: list[XpRangeEntryOut]


class XpRangeChange(BaseModel):
    # Either or both; None leaves that figure as it is.
    floor: int | None = Field(default=None, ge=0, le=100000)
    ceiling: int | None = Field(default=None, ge=0, le=100000)
    reason: str = Field(min_length=1, max_length=500)


def range_out(db: DbSession, troupe_id: uuid.UUID) -> XpRangeOut:
    troupe = get_troupe(db, troupe_id)
    f = xp_range.figures(db, troupe)
    return XpRangeOut(
        starting_xp=f.starting,
        floor=f.floor,
        ceiling=f.ceiling,
        games=f.games,
        game_xp=f.game_xp,
        downtimes=f.downtimes,
        downtime_xp=f.downtime_xp,
        set_floor=f.set_floor,
        set_ceiling=f.set_ceiling,
        entries=[
            XpRangeEntryOut(
                id=e.id,
                kind=e.kind,
                floor_change=e.floor_change,
                ceiling_change=e.ceiling_change,
                reason=e.reason,
                entered_on=e.entered_on,
            )
            for e in reversed(xp_range.entries(db, troupe))
        ],
    )


@router.get("")
def read_range(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> XpRangeOut:
    """Anyone can see where a troupe stands, as they can see the troupe."""
    troupe = get_troupe(db, troupe_id)
    if troupe.archived_at is not None and not user.is_custodian:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return range_out(db, troupe_id)


@router.put("")
def set_range(
    troupe_id: uuid.UUID, body: XpRangeChange, db: DbSession, user: CurrentUser
) -> XpRangeOut:
    """Storytellers set the floor or ceiling by hand, for a chronicle that began
    before Horatio. Games and downtimes still add to them afterwards."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
    xp_range.set_by_hand(db, user, troupe, body.floor, body.ceiling, body.reason.strip())
    db.commit()
    return range_out(db, troupe_id)
