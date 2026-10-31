"""What is waiting on a troupe's staff (issue #149), for the Waiting on you box on
its About tab: one line per kind of work, each with a count and a link straight
to it, in one request.

Each kind of work has its own small function, and shows only to staff who may
act on it (`LINES`). A line with nothing waiting is left out. Links are pages of
the app, not of the API.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import downtimes, influence_effects, responses
from horatio.api.responses import cycle_progress
from horatio.api.troupes import get_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Approval,
    Character,
    CharacterTrait,
    CycleParticipant,
    DowntimeCycle,
    InfluenceEntry,
    Submission,
    TraitCategory,
    TraitDefinition,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, allows, require_troupe_action, troupe_role
from horatio.rules.status import STATUS_CATEGORY

router = APIRouter(tags=["troupes"])

# How far ahead "effects ending this week" looks.
A_WEEK = timedelta(days=7)


class WaitingLine(BaseModel):
    # What kind of work it is, such as "approvals" or "cycle_unwritten".
    kind: str
    label: str
    count: int
    # The page of the app where the work is done.
    link: str


Gather = Callable[[Session, User, Troupe], list[WaitingLine]]


def now() -> datetime:
    return datetime.now(UTC)


def cycles(db: Session, troupe: Troupe, *statuses: str) -> list[DowntimeCycle]:
    return list(
        db.scalars(
            select(DowntimeCycle)
            .where(DowntimeCycle.troupe_id == troupe.id, DowntimeCycle.status.in_(statuses))
            .order_by(DowntimeCycle.id)
        )
    )


def approvals(db: Session, _user: User, troupe: Troupe) -> list[WaitingLine]:
    """Every pending approval, of any kind: what the Approvals tab's count shows."""
    count = db.scalar(
        select(func.count(Approval.id))
        .join(Character, Approval.character_id == Character.id)
        .where(Approval.troupe_id == troupe.id, Approval.status == "pending")
    )
    return [
        WaitingLine(
            kind="approvals",
            label="Approvals waiting",
            count=count or 0,
            link=f"/troupes/{troupe.id}/approvals",
        )
    ]


def late_drafts(db: Session, cycle: DowntimeCycle) -> int:
    """Downtimes started but not submitted by the end of the grace period, which
    only a storyteller's say-so now lets in."""
    if cycle.status != "open" or now() <= cycle.grace_ends_at:
        return 0
    return (
        db.scalar(
            select(func.count(Submission.id))
            .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
            .where(
                CycleParticipant.cycle_id == cycle.id,
                CycleParticipant.removed_at.is_(None),
                CycleParticipant.late_accepted_by.is_(None),
                Submission.status == "draft",
            )
        )
        or 0
    )


def cycle_work(db: Session, _user: User, troupe: Troupe) -> list[WaitingLine]:
    """The cycle under way, from its progress: downtimes in, late ones to accept,
    and responses to assign and to write. A closed cycle still has responses to
    write until it is complete."""
    lines: list[WaitingLine] = []
    for cycle in cycles(db, troupe, "open", "closed"):
        progress = cycle_progress(db, cycle)
        base = f"/cycles/{cycle.id}"
        if cycle.status == "open":
            lines.append(
                WaitingLine(
                    kind="cycle_submitted",
                    label=f"{cycle.name}: downtimes submitted, of {progress.participants}",
                    count=progress.submitted,
                    link=f"{base}/participants",
                )
            )
        lines += [
            WaitingLine(
                kind="cycle_late",
                label=f"{cycle.name}: late downtimes to accept",
                count=late_drafts(db, cycle),
                link=f"{base}/participants",
            ),
            WaitingLine(
                kind="cycle_unassigned",
                label=f"{cycle.name}: responses to assign",
                count=progress.unassigned,
                link=f"{base}/responses",
            ),
            WaitingLine(
                kind="cycle_unwritten",
                label=f"{cycle.name}: responses not yet written",
                count=progress.responses - progress.written,
                link=f"{base}/responses",
            ),
        ]
    return lines


def my_responses(db: Session, user: User, troupe: Troupe) -> list[WaitingLine]:
    """Responses assigned to the viewer, and for narrators to any narrator, not yet
    written: what My work lists."""
    return [
        WaitingLine(
            kind="my_responses",
            label=f"{cycle.name}: responses for you to write",
            count=sum(i.response.status != "written" for i in responses.mine(db, user, cycle)),
            link=f"/troupes/{troupe.id}/work/{cycle.id}",
        )
        for cycle in cycles(db, troupe, "open", "closed")
    ]


def deliveries(db: Session, _user: User, troupe: Troupe) -> list[WaitingLine]:
    """Downtimes of a closed cycle with every response written and something its
    player has not had: first results, or an update."""
    return [
        WaitingLine(
            kind="deliveries",
            label=f"{cycle.name}: results ready to deliver",
            count=sum(r.finished and r.due for r in responses.readiness(db, cycle)),
            link=f"/cycles/{cycle.id}/delivery",
        )
        for cycle in cycles(db, troupe, "closed")
    ]


def influence_details(db: Session, _user: User, troupe: Troupe) -> list[WaitingLine]:
    count = db.scalar(
        select(func.count(InfluenceEntry.id)).where(
            InfluenceEntry.troupe_id == troupe.id, InfluenceEntry.needs_details
        )
    )
    return [
        WaitingLine(
            kind="influence_details",
            label="Influence entries that need details",
            count=count or 0,
            link=f"/troupes/{troupe.id}/influence?needs=details",
        )
    ]


def effects_ending(db: Session, _user: User, troupe: Troupe) -> list[WaitingLine]:
    """Attacks, Boosts and Blocks holding now that will have ended a week from now."""
    week_on = now() + A_WEEK
    ending = [
        effect
        for effect, held in influence_effects.troupe_effects(db, troupe.id)
        if held.active and not influence_effects.lasting(db, effect, week_on).active
    ]
    return [
        WaitingLine(
            kind="effects_ending",
            label="Influence effects ending this week",
            count=len(ending),
            link=f"/troupes/{troupe.id}/influence/effects",
        )
    ]


def shortfalls(db: Session, _user: User, troupe: Troupe) -> list[WaitingLine]:
    """Participants of an open cycle with more actions taken off than their
    allowance had, such as influence spent at games."""
    lines: list[WaitingLine] = []
    for cycle in cycles(db, troupe, "open"):
        participants = db.scalars(
            select(CycleParticipant).where(
                CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None)
            )
        )
        lines.append(
            WaitingLine(
                kind="shortfalls",
                label=f"{cycle.name}: allowance shortfalls",
                count=sum(bool(downtimes.shortfall(db, p)) for p in participants),
                link=f"/cycles/{cycle.id}/participants",
            )
        )
    return lines


def status_to_resolve(db: Session, _user: User, troupe: Troupe) -> list[WaitingLine]:
    """The troupe's characters holding status traits from before status was derived
    that nothing gives now (horatio.sect_status.resolve). The link opens the first."""
    found = list(
        db.scalars(
            select(Character.id)
            .join(CharacterTrait, CharacterTrait.character_id == Character.id)
            .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(
                (Character.home_troupe_id == troupe.id) | (Character.owner_troupe_id == troupe.id),
                Character.status == "active",
                TraitCategory.key == STATUS_CATEGORY,
                func.coalesce(CharacterTrait.rating, 0) > CharacterTrait.granted_rating,
            )
            .distinct()
            .order_by(Character.id)
        )
    )
    return [
        WaitingLine(
            kind="status_to_resolve",
            label="Characters with old status to resolve",
            count=len(found),
            link=f"/characters/{found[0]}" if found else "",
        )
    ]


# Each kind of work, with what a staff member must be allowed to do to see it.
LINES: list[tuple[TroupeAction, Gather]] = [
    (TroupeAction.APPROVE_CHANGES, approvals),
    (TroupeAction.MANAGE_CYCLES, cycle_work),
    (TroupeAction.ANSWER_ASSIGNED_RESPONSES, my_responses),
    (TroupeAction.DELIVER_RESPONSES, deliveries),
    (TroupeAction.MANAGE_INFLUENCE_LOG, influence_details),
    (TroupeAction.MANAGE_INFLUENCE_LOG, effects_ending),
    (TroupeAction.ADJUST_ALLOWANCES, shortfalls),
    (TroupeAction.CHANGE_STATUS, status_to_resolve),
]


def waiting(db: Session, user: User, troupe: Troupe) -> list[WaitingLine]:
    role = troupe_role(db, user, troupe)
    return [
        line
        for action, gather in LINES
        if allows(role, action, is_custodian=user.is_custodian)
        for line in gather(db, user, troupe)
        if line.count > 0
    ]


@router.get("/troupes/{troupe_id}/waiting")
def read_waiting(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[WaitingLine]:
    """What is waiting on the viewer in this troupe, for its staff only."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.VIEW_STAFF)
    return waiting(db, user, troupe)
