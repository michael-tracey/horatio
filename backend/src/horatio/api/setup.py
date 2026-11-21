"""How far a troupe is set up (issue #377), for the Setup tab of its Customise
group: the few things a new lead does first, each done or not, and how many house
rules it has in each part of Rules. In one request, from what the troupe already
holds; its other settings are on the troupe itself.

And Getting your troupe ready (#1049), the steps a new troupe takes in order, for
its Overview: each done or not from what the troupe holds now, never ticked by
hand. Its storytellers hide the card, and bring it back from Setup."""

import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import exists, func, or_, select

from horatio import audit
from horatio.api.connectors import connectors_out
from horatio.api.downtimes import staff_troupe
from horatio.api.house_rules import checks_out, other_settings, splat_house_rules
from horatio.api.troupe_profiles import Profile
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Approval,
    Character,
    DowntimeCycle,
    HouseTrait,
    ScheduledGame,
    Troupe,
    TroupeMembership,
    TroupeStaff,
    XpRangeEntry,
)
from horatio.permissions import TroupeAction
from horatio.rules.splats import SPLATS
from horatio.troupe_settings_share import column_default

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


@dataclass(frozen=True)
class HouseRuleCounts:
    """How many house rules the troupe has in each part of Rules."""

    checks: int
    checks_total: int
    costs: int
    starting: int
    actions: int
    house_traits: int
    other: int

    @property
    def total(self) -> int:
        return (
            self.checks + self.costs + self.starting + self.actions + self.house_traits + self.other
        )


def house_rule_counts(db: DbSession, troupe: Troupe) -> HouseRuleCounts:
    splats = ["vampire", *(s for s in troupe.allowed_splats if s != "vampire" and s in SPLATS)]
    by_splat = [splat_house_rules(db, troupe.id, s) for s in splats]
    checks = checks_out(db, troupe.id)
    return HouseRuleCounts(
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
    )


def profiled(troupe: Troupe) -> bool:
    """It has a profile that says more than its name: a picture, a contact, or any of its text."""
    return bool(troupe.portrait_id or troupe.banner_id or troupe.contact_id) or (
        Profile.model_validate(troupe.profile) != Profile()
    )


def staff_count(db: DbSession, troupe: Troupe) -> int:
    """Its staff besides the lead storyteller."""
    return (
        db.scalar(
            select(func.count()).select_from(TroupeStaff).where(TroupeStaff.troupe_id == troupe.id)
        )
        or 0
    )


@router.get("/troupes/{troupe_id}/setup")
def troupe_setup(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> SetupOut:
    """What a new lead sets up first, for the troupe's running staff."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    rules = house_rule_counts(db, troupe)
    return SetupOut(
        described=bool(troupe.description.strip()),
        profile=profiled(troupe),
        staff=staff_count(db, troupe),
        cycles=db.scalar(
            select(func.count())
            .select_from(DowntimeCycle)
            .where(DowntimeCycle.troupe_id == troupe.id)
        )
        or 0,
        checks=rules.checks,
        checks_total=rules.checks_total,
        costs=rules.costs,
        starting=rules.starting,
        actions=rules.actions,
        house_traits=rules.house_traits,
        other=rules.other,
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


# --- Getting your troupe ready (#1049) -------------------------------------------------------

ReadyStep = Literal[
    "profile", "features", "joining", "starting", "house_rules", "staff", "first_game", "players"
]

# The optional features (the Features list's, frontend features.ts), each a setting that a
# troupe starts with as Horatio's default: one set otherwise is a feature chosen.
FEATURE_SETTINGS = (
    "boons",
    "blood_bonds",
    "player_nominations",
    "remembrances",
    "court_history_players",
    "chronicle_players",
    "quests_enabled",
    "feeding",
    "golconda_enlightened",
    "items_expire",
    "play_tabs_off",
)
# Starting XP and what each game and downtime gives: Troupe settings › XP.
XP_SETTINGS = ("starting_xp", "session_xp", "downtime_xp", "new_character_incentive", "game_xp")


class ReadyStepOut(BaseModel):
    step: ReadyStep
    done: bool


class GettingReadyOut(BaseModel):
    # Its storytellers hid the card from the Overview.
    hidden: bool
    # In order: the profile, features, who may join, starting points and XP, house
    # rules, staff, the first game, and players.
    steps: list[ReadyStepOut]


class GettingReadyChange(BaseModel):
    hidden: bool


def _changed(troupe: Troupe, keys: tuple[str, ...]) -> bool:
    """Any of these settings is no longer what a new troupe has."""
    return any(getattr(troupe, k) != column_default(k) for k in keys)


def getting_ready(db: DbSession, troupe: Troupe) -> GettingReadyOut:
    """Each step done or not, from what the troupe holds now. A setting counts once it
    is set otherwise than a new troupe has it, so a new troupe has nothing done."""
    rules = house_rule_counts(db, troupe)
    splats_or_sects = bool(troupe.allowed_sects) or sorted(troupe.allowed_splats) != ["vampire"]
    xp_set_by_hand = db.scalar(
        select(exists().where(XpRangeEntry.troupe_id == troupe.id, XpRangeEntry.kind == "set"))
    )
    games = db.scalar(select(exists().where(ScheduledGame.troupe_id == troupe.id)))
    # A player's character here, home or visiting, now or before, or asking to make the
    # troupe its home (#1114). Asking starts a visit too, which stays if the request is
    # declined or withdrawn; the request itself counts only while it waits.
    visited = (
        exists()
        .where(TroupeMembership.troupe_id == troupe.id)
        .where(Character.id == TroupeMembership.character_id, Character.kind == "pc")
    )
    asking = exists().where(
        Approval.troupe_id == troupe.id,
        Approval.kind == "home_troupe_change",
        Approval.status == "pending",
        Character.id == Approval.character_id,
        Character.kind == "pc",
    )
    players = db.scalar(select(or_(visited, asking)))
    done: dict[ReadyStep, bool] = {
        "profile": bool(troupe.description.strip()) and profiled(troupe),
        "features": _changed(troupe, FEATURE_SETTINGS),
        "joining": splats_or_sects,
        "starting": rules.starting > 0 or _changed(troupe, XP_SETTINGS) or bool(xp_set_by_hand),
        "house_rules": rules.total > 0,
        "staff": staff_count(db, troupe) > 0,
        "first_game": bool(games),
        "players": bool(players),
    }
    return GettingReadyOut(
        hidden=troupe.getting_ready_hidden,
        steps=[ReadyStepOut(step=step, done=d) for step, d in done.items()],
    )


@router.get("/troupes/{troupe_id}/getting-ready")
def read_getting_ready(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> GettingReadyOut:
    """The steps of getting the troupe ready, for its running staff."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    return getting_ready(db, troupe)


@router.put("/troupes/{troupe_id}/getting-ready")
def change_getting_ready(
    troupe_id: uuid.UUID, body: GettingReadyChange, db: DbSession, user: CurrentUser
) -> GettingReadyOut:
    """Hide Getting your troupe ready from the Overview, or bring it back: its storytellers'."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.MANAGE_HOUSE_RULES)
    if body.hidden != troupe.getting_ready_hidden:
        troupe.getting_ready_hidden = body.hidden
        audit.record(
            db,
            user,
            "troupe.getting_ready",
            troupe_id=troupe.id,
            what="hid" if body.hidden else "brought back",
        )
    db.commit()
    return getting_ready(db, troupe)
