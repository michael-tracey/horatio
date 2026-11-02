"""A troupe's house rules for Retainers (horatio.retainer_upkeep): upkeep and growth,
each off unless its staff switch it on."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import retainer_upkeep
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe
from horatio.permissions import TroupeAction

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["house rules"])


class UpkeepRule(BaseModel):
    # So much Blood or Willpower for each Retainer, or each ghoul Retainer only.
    amount: int = Field(ge=1, le=retainer_upkeep.MOST_UPKEEP)
    pool: Literal["blood", "willpower"]
    ghouls_only: bool = False
    # Each "game", taken as the night starts, or each "month": taken at the month's
    # first "game", or charged when a "downtime" cycle closes.
    per: Literal["game", "month"] = "game"
    month_at: Literal["game", "downtime"] = "game"


class RetainerRulesIn(BaseModel):
    # None for no upkeep, and no growth.
    upkeep: UpkeepRule | None = None
    # XP a month for each Retainer, given as a downtime cycle closes.
    growth: int | None = Field(default=None, ge=1, le=retainer_upkeep.MOST_GROWTH)


class RetainerRulesOut(RetainerRulesIn):
    # Each in plain words, as the House rules tab has it; None while off.
    upkeep_text: str | None
    growth_text: str | None


def rules_out(troupe: Troupe) -> RetainerRulesOut:
    rules = retainer_upkeep.rules_of(troupe)
    upkeep = rules.upkeep
    return RetainerRulesOut(
        upkeep=UpkeepRule(
            amount=upkeep.amount,
            pool=upkeep.pool,
            ghouls_only=upkeep.ghouls_only,
            per=upkeep.per,
            month_at=upkeep.month_at,
        )
        if upkeep
        else None,
        growth=rules.growth,
        upkeep_text=upkeep.text() if upkeep else None,
        growth_text=rules.growth_text(),
    )


@router.get("/retainer-rules")
def read_retainer_rules(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> RetainerRulesOut:
    """Anyone signed in may read them, as they may the troupe's other house rules."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or (troupe.archived_at is not None and not user.is_custodian):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return rules_out(troupe)


@router.put("/retainer-rules")
def set_retainer_rules(
    troupe_id: uuid.UUID, body: RetainerRulesIn, db: DbSession, user: CurrentUser
) -> RetainerRulesOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    upkeep = body.upkeep
    retainer_upkeep.set_rules(
        db,
        user,
        troupe,
        retainer_upkeep.Rules(
            upkeep=retainer_upkeep.Upkeep(
                amount=upkeep.amount,
                pool=upkeep.pool,
                ghouls_only=upkeep.ghouls_only,
                per=upkeep.per,
                month_at=upkeep.month_at if upkeep.per == "month" else "game",
            )
            if upkeep
            else None,
            growth=body.growth,
        ),
    )
    db.commit()
    return rules_out(troupe)
