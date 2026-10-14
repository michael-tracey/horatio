"""A troupe's characters and log, for its storytellers and assistant storytellers."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Select, select

from horatio import titles
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Approval, AuditEvent, Character, TroupeMembership, User
from horatio.permissions import TroupeAction

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["roster"])


class RosterEntry(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str
    kind: str  # pc | npc
    titles: list[str]
    # The troupe holds the character's sheet; otherwise the character visits.
    home: bool
    # Waiting for this troupe to accept it as home.
    waiting: bool
    # Discipline dots waiting on this troupe.
    disciplines_waiting: int
    joined_at: datetime


class LogEntry(BaseModel):
    id: uuid.UUID
    at: datetime
    action: str
    message: str
    actor_name: str | None
    character_id: uuid.UUID | None
    character_name: str | None
    data: dict[str, Any]


@router.get("/characters")
def roster(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[RosterEntry]:
    """Every character in the troupe now: those whose home it is first, then visitors."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    rows = db.execute(
        select(TroupeMembership, Character, User.display_name)
        .join(Character, TroupeMembership.character_id == Character.id)
        .join(User, Character.player_id == User.id)
        .where(TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None))
    )
    pending = list(
        db.execute(
            select(Approval.character_id, Approval.kind).where(
                Approval.troupe_id == troupe_id, Approval.status == "pending"
            )
        )
    )
    entries = [
        RosterEntry(
            character_id=c.id,
            character_name=c.name,
            player_name=player if c.kind == "pc" else "NPC",
            kind=c.kind,
            titles=titles.held(db, troupe_id, c.id),
            home=c.home_troupe_id == troupe_id,
            waiting=(c.id, "home_troupe_change") in pending,
            disciplines_waiting=sum(1 for p in pending if p == (c.id, "discipline")),
            joined_at=m.joined_at,
        )
        for m, c, player in rows
    ]
    return sorted(entries, key=lambda e: (not e.home, e.character_name.lower()))


# What each logged action reads as. `{character}` and `{actor}` are filled in.
MESSAGES: dict[str, str] = {
    "troupe.join": "{character} joined the troupe.",
    "troupe.leave": "{character} left the troupe.",
    "character.deleted": "{character} was deleted by its player.",
    "approval.request": "{actor} asked for {character} to be approved.",
    "approval.request.discipline": "{actor} bought {name} {rating} for {character}; pending.",
    "approval.approved.discipline": "{actor} approved {character}'s {name} {rating}.",
    "approval.declined.discipline": "{actor} declined {character}'s {name} {rating}; refunded.",
    "approval.withdrawn.discipline": "{actor} withdrew {character}'s {name} {rating}; refunded.",
    "approval.request.home_troupe_change": "{actor} asked to make this {character}'s home.",
    "approval.approved.home_troupe_change": "{actor} accepted {character}; this is its home.",
    "approval.approved": "{actor} approved {character}.",
    "approval.declined": "{actor} declined {character}'s request.",
    "approval.withdrawn": "{actor} withdrew {character}'s request.",
    # From before characters had one home troupe; kept so old log entries read.
    "standing.draft": "{actor} sent {character} back to draft: {reason}",
    "home_troupe.moved_away": "{character} moved its home troupe elsewhere.",
    "xp.award": "{actor} awarded {character} {amount} XP: {reason}",
    "staff.assigned": "{actor} made {member} {role}.",
    "staff.removed": "{actor} removed {member} from the staff.",
    "troupe.lead_appointed": "{actor} appointed {member} lead storyteller.",
    "troupe.renamed": "{actor} renamed the troupe to {name}.",
    "troupe.archived": "{actor} archived the troupe.",
    "downtime.cycle_created": "{actor} created a downtime cycle.",
    "downtime.cycle_opened": "{actor} opened a downtime cycle ({participants} taking part).",
    "downtime.cycle_closed": "{actor} closed a downtime cycle.",
    "downtime.submitted": "{character} submitted a downtime.",
    "downtime.delivered": "{actor} delivered {count} downtime results.",
    "downtime.participant_added": "{actor} added {character} to a downtime cycle.",
    "downtime.participant_removed": "{actor} removed {character} from a downtime cycle.",
    "downtime.allowance_adjusted": "{actor} adjusted {character}'s actions: {reason}",
    "npc.created": "{actor} made an NPC, {character}.",
    "npc.deleted": "{actor} deleted the NPC {character}.",
    "title.given": "{actor} gave {character} the title {title}.",
    "title.taken": "{actor} took the title {title} from {character}.",
    "title.added": "{actor} added the title {title} to the troupe.",
    "title.removed_from_troupe": "{actor} removed the title {title} from the troupe.",
    "troupe.sects_limited": "{actor} set which sects may join: {sects}.",
    "sheet.choose": "{actor} chose {name} as {character}'s {category}.",
    "creation.pick": "{actor} picked {name} {rating} for {character}.",
    "creation.unpick": "{actor} took back {character}'s creation pick of {name}.",
    "creation.set_category": "{actor} set {character}'s starting {category}: {picks}.",
    "creation.complete": "{actor} finished creating {character}.",
}


def purchase_message(data: dict[str, Any]) -> str:
    name = data["name"] + (f": {data['detail']}" if data.get("detail") else "")
    name = name.replace("{", "{{").replace("}", "}}")
    before, after, cost = data["from_rating"] or 0, data["to_rating"], data["cost"]
    if after == 0:
        change = f"removed {{character}}'s {name}"
    elif before == 0:
        change = f"bought {name} {after} for {{character}}"
    else:
        verb = "raised" if after > before else "lowered"
        change = f"{verb} {{character}}'s {name} from {before} to {after}"
    price = f" ({cost} XP)" if cost > 0 else f" ({-cost} XP back)" if cost < 0 else ""
    return f"{{actor}} {change}{price}."


def message(action: str, actor: str | None, character: str | None, data: dict[str, Any]) -> str:
    values = {**data, "actor": actor or "Someone", "character": character or "A character"}
    if isinstance(values.get("category"), str):
        values["category"] = values["category"].replace("_", " ")
    if isinstance(values.get("picks"), dict):
        picks: dict[str, Any] = values["picks"]
        values["picks"] = ", ".join(f"{n} {r}" for n, r in picks.items()) or "none"
    try:
        if action == "sheet.purchase":
            template = purchase_message(data)
        else:
            template = MESSAGES.get(
                f"{action}.{data.get('kind')}",
                MESSAGES.get(action, action.replace("_", " ").replace(".", ": ")),
            )
        return template.format(**values)
    except (KeyError, IndexError, TypeError):
        return action.replace("_", " ").replace(".", ": ")


@router.get("/log")
def log(
    troupe_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    before: datetime | None = None,
    limit: int = 100,
) -> list[LogEntry]:
    """What has happened in the troupe, newest first."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_LOG)
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(AuditEvent.troupe_id == troupe_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(min(max(limit, 1), 500))
    )
    if before is not None:
        query = query.where(AuditEvent.created_at < before)
    return log_entries(db, query)


def log_entries(db: DbSession, query: Select[AuditEvent, str]) -> list[LogEntry]:
    """Read the events `query` selects, with their actors' names, as log entries."""
    entries: list[LogEntry] = []
    for event, actor in db.execute(query):
        name = event.data.get("character_name")
        entries.append(
            LogEntry(
                id=event.id,
                at=event.created_at,
                action=event.action,
                message=message(event.action, actor, name, event.data),
                actor_name=actor,
                character_id=event.character_id,
                character_name=name,
                data=event.data,
            )
        )
    return entries
