"""What is waiting on a troupe's staff (issue #149), for the Waiting on you box on
its About tab, the counts on its tabs and the staff's home page (issue #373): one
line per kind of work, each with a count and a link straight to it, in one request.

Each kind of work has its own small function, and shows only to staff who may
act on it (`LINES`). A line with nothing waiting is left out, except the open
cycle's, which always shows, first. Links are pages of the app, not of the API.

Every troupe page asks for it, for its tab counts, so each line keeps to a query
or two, and the cycles under way are loaded once for all of them (`Asked`).
"""

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import backstories, downtimes, influence_effects, quests, responses
from horatio.api.responses import cycle_progress
from horatio.api.troupes import get_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    AllowanceAdjustment,
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
    # How many wait. None on the open cycle's line, which shows however many do
    # and gives its figures in its label.
    count: int | None
    # The page of the app where the work is done.
    link: str
    # When the open cycle's downtimes are due.
    due_at: datetime | None = None


@dataclass(frozen=True)
class Asked:
    """Who asks, about which troupe, and what every line shares."""

    db: Session
    user: User
    troupe: Troupe
    # The cycles under way, open and closed, oldest first.
    cycles: list[DowntimeCycle]

    def under_way(self, *statuses: str) -> list[DowntimeCycle]:
        return [c for c in self.cycles if c.status in statuses]


Gather = Callable[[Asked], list[WaitingLine]]


def now() -> datetime:
    return datetime.now(UTC)


def approvals(asked: Asked) -> list[WaitingLine]:
    """Every pending approval, of any kind: what the Approvals tab's count shows."""
    troupe = asked.troupe
    count = asked.db.scalar(
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


def backstories_to_read(asked: Asked) -> list[WaitingLine]:
    """Backstories waiting for the troupe's storytellers to read
    (horatio.backstories.waiting). The link opens the backstory when there is one,
    else the roster, which marks each."""
    troupe = asked.troupe
    found = backstories.waiting(asked.db, troupe)
    return [
        WaitingLine(
            kind="backstories",
            label="Backstories to read",
            count=len(found),
            link=f"/characters/{found[0]}/backstory?troupe={troupe.id}"
            if len(found) == 1
            else f"/troupes/{troupe.id}/characters",
        )
    ]


def quest_requests(asked: Asked) -> list[WaitingLine]:
    """Quest requests not yet answered, as the Quests tab's To answer lists them: for
    a narrator, those assigned to them or to any narrator."""
    troupe = asked.troupe
    if not troupe.quests_enabled:
        return []
    return [
        WaitingLine(
            kind="quest_requests",
            label="Quest requests to answer",
            count=len(quests.queue(asked.db, asked.user, troupe, "open")),
            link=f"/troupes/{troupe.id}/quests",
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


def cycle_work(asked: Asked) -> list[WaitingLine]:
    """The cycles under way, from their progress: the open one always, with how
    many downtimes are in and when they are due; late ones to accept; and
    responses to assign and to write. A closed cycle still has responses to write
    until it is complete."""
    lines: list[WaitingLine] = []
    for cycle in asked.under_way("open", "closed"):
        progress = cycle_progress(asked.db, cycle)
        base = f"/cycles/{cycle.id}"
        if cycle.status == "open":
            submitted = f"{progress.submitted} of {progress.participants} submitted"
            lines.append(
                WaitingLine(
                    kind="cycle_open",
                    label=f"{cycle.name}: {submitted}",
                    count=None,
                    link=f"{base}/participants",
                    due_at=cycle.closes_at,
                )
            )
        lines += [
            WaitingLine(
                kind="cycle_late",
                label=f"{cycle.name}: late downtimes to accept",
                count=late_drafts(asked.db, cycle),
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


def my_responses(asked: Asked) -> list[WaitingLine]:
    """Responses assigned to the viewer, and for narrators to any narrator, not yet
    written: what My work lists."""
    return [
        WaitingLine(
            kind="my_responses",
            label=f"{cycle.name}: responses for you to write",
            count=sum(
                i.response.status != "written" for i in responses.mine(asked.db, asked.user, cycle)
            ),
            link=f"/troupes/{asked.troupe.id}/work/{cycle.id}",
        )
        for cycle in asked.under_way("open", "closed")
    ]


def deliveries(asked: Asked) -> list[WaitingLine]:
    """Downtimes of a closed cycle with every response written and something its
    player has not had: first results, or an update."""
    return [
        WaitingLine(
            kind="deliveries",
            label=f"{cycle.name}: results ready to deliver",
            count=sum(r.finished and r.due for r in responses.readiness(asked.db, cycle)),
            link=f"/cycles/{cycle.id}/delivery",
        )
        for cycle in asked.under_way("closed")
    ]


def influence_details(asked: Asked) -> list[WaitingLine]:
    troupe = asked.troupe
    count = asked.db.scalar(
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


def effects_ending(asked: Asked) -> list[WaitingLine]:
    """Attacks, Boosts and Blocks holding now that will have ended a week from now."""
    db, troupe = asked.db, asked.troupe
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


def shortfalls(asked: Asked) -> list[WaitingLine]:
    """Participants of an open cycle with more actions taken off than their
    allowance had, such as influence spent at games. Their adjustments come in one
    query, not one each."""
    db = asked.db
    lines: list[WaitingLine] = []
    for cycle in asked.under_way("open"):
        participants = list(
            db.scalars(
                select(CycleParticipant).where(
                    CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None)
                )
            )
        )
        adjusted: dict[uuid.UUID, list[AllowanceAdjustment]] = defaultdict(list)
        for adjustment in db.scalars(
            select(AllowanceAdjustment)
            .where(AllowanceAdjustment.participant_id.in_([p.id for p in participants]))
            .order_by(AllowanceAdjustment.id)
        ):
            adjusted[adjustment.participant_id].append(adjustment)
        lines.append(
            WaitingLine(
                kind="shortfalls",
                label=f"{cycle.name}: allowance shortfalls",
                count=sum(bool(downtimes.shortfall(db, p, adjusted[p.id])) for p in participants),
                link=f"/cycles/{cycle.id}/participants",
            )
        )
    return lines


def status_to_resolve(asked: Asked) -> list[WaitingLine]:
    """The troupe's characters holding status traits from before status was derived
    that nothing gives now (horatio.sect_status.resolve). The link opens the first."""
    troupe = asked.troupe
    found = list(
        asked.db.scalars(
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
    (TroupeAction.APPROVE_CHANGES, backstories_to_read),
    (TroupeAction.VIEW_STAFF, quest_requests),
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
    cycles = list(
        db.scalars(
            select(DowntimeCycle)
            .where(
                DowntimeCycle.troupe_id == troupe.id, DowntimeCycle.status.in_(("open", "closed"))
            )
            .order_by(DowntimeCycle.id)
        )
    )
    asked = Asked(db, user, troupe, cycles)
    lines = [
        line
        for action, gather in LINES
        if allows(role, action, is_custodian=user.is_custodian)
        for line in gather(asked)
        if line.count is None or line.count > 0
    ]
    # The open cycle first: what the rest of the month turns on.
    return sorted(lines, key=lambda line: line.count is not None)


@router.get("/troupes/{troupe_id}/waiting")
def read_waiting(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[WaitingLine]:
    """What is waiting on the viewer in this troupe, for its staff only: the open
    cycle first, then each kind of work with its count."""
    troupe = get_troupe(db, troupe_id)
    require_troupe_action(db, user, troupe, TroupeAction.VIEW_STAFF)
    return waiting(db, user, troupe)
