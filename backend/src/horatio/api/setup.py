"""How far a troupe is set up (issue #377), for the Overview tab of its Customise
group: the few things a new lead does first, each done or not, and how many house
rules it has in each part of Rules. In one request, from what the troupe already
holds; its other settings are on the troupe itself."""

import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from horatio.api.connectors import connectors_out
from horatio.api.downtimes import staff_troupe
from horatio.api.house_rules import checks_out, other_settings, splat_house_rules
from horatio.api.troupe_profiles import Profile
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import DowntimeCycle, HouseTrait, TroupeStaff
from horatio.permissions import TroupeAction
from horatio.rules.splats import SPLATS

router = APIRouter(tags=["troupes"])


class SetupConnector(BaseModel):
    kind: str
    name: str
    # "on", "test" (on, in test mode), "off", or "unavailable" (not set up on this server).
    state: Literal["on", "test", "off", "unavailable"]


class SetupOut(BaseModel):
    # It has a description, and a profile that says more than its name.
    described: bool
    profile: bool
    # Its staff besides the lead storyteller.
    staff: int
    # Downtime cycles it has opened, ever.
    cycles: int
    # Its house rules in each part of Rules: checks it plays differently (of all
    # there are), prices, starting points and downtime actions (for every splat it
    # takes), its own merits and flaws, and its other settings that differ from the book.
    checks: int
    checks_total: int
    costs: int
    starting: int
    actions: int
    house_traits: int
    other: int
    connectors: list[SetupConnector]


@router.get("/troupes/{troupe_id}/setup")
def troupe_setup(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> SetupOut:
    """What a new lead sets up first, for the troupe's running staff."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    splats = ["vampire", *(s for s in troupe.allowed_splats if s != "vampire" and s in SPLATS)]
    by_splat = [splat_house_rules(db, troupe.id, s) for s in splats]
    checks = checks_out(db, troupe.id)
    return SetupOut(
        described=bool(troupe.description.strip()),
        profile=bool(troupe.portrait_id or troupe.banner_id or troupe.contact_id)
        or Profile.model_validate(troupe.profile) != Profile(),
        staff=db.scalar(
            select(func.count()).select_from(TroupeStaff).where(TroupeStaff.troupe_id == troupe.id)
        )
        or 0,
        cycles=db.scalar(
            select(func.count())
            .select_from(DowntimeCycle)
            .where(DowntimeCycle.troupe_id == troupe.id)
        )
        or 0,
        checks=sum(1 for c in checks if c.house),
        checks_total=len(checks),
        costs=sum(len(s.costs) for s in by_splat),
        starting=sum(len(s.starting) for s in by_splat),
        actions=sum(len(s.actions) for s in by_splat),
        house_traits=db.scalar(
            select(func.count())
            .select_from(HouseTrait)
            .where(HouseTrait.troupe_id == troupe.id, HouseTrait.archived_at.is_(None))
        )
        or 0,
        other=len(other_settings(db, troupe)),
        connectors=[
            SetupConnector(
                kind=c.kind,
                name=c.name,
                state="unavailable"
                if c.unavailable and not c.enabled
                else ("test" if c.test_mode else "on")
                if c.enabled
                else "off",
            )
            for c in connectors_out(db, troupe.id, user)
        ],
    )
