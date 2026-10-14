"""A troupe's characters and log, for its storytellers and assistant storytellers."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import sheets, titles
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
    standing: str  # draft | approved
    note: str
    home: bool
    waiting: bool
    joined_at: datetime


class StandingChange(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


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
    """Every character in the troupe now, drafts first."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    rows = db.execute(
        select(TroupeMembership, Character, User.display_name)
        .join(Character, TroupeMembership.character_id == Character.id)
        .join(User, Character.player_id == User.id)
        .where(TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None))
    )
    waiting = set(
        db.scalars(
            select(Approval.character_id).where(
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
            standing=m.standing,
            note=m.standing_note,
            home=c.home_troupe_id == troupe_id,
            waiting=c.id in waiting,
            joined_at=m.joined_at,
        )
        for m, c, player in rows
    ]
    return sorted(entries, key=lambda e: (e.standing != "draft", e.character_name.lower()))


@router.post("/characters/{character_id}/return-to-draft")
def return_to_draft(
    troupe_id: uuid.UUID,
    character_id: uuid.UUID,
    body: StandingChange,
    db: DbSession,
    user: CurrentUser,
) -> RosterEntry:
    """Send an approved character back to draft in this troupe, with a reason."""
    staff_troupe(db, user, troupe_id, TroupeAction.SET_STANDING)
    character = db.get(Character, character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character.")
    sheets.return_to_draft(db, user, character, troupe_id, body.reason)
    db.commit()
    return next(e for e in roster(troupe_id, db, user) if e.character_id == character_id)


# What each logged action reads as. `{character}` and `{actor}` are filled in.
MESSAGES: dict[str, str] = {
    "troupe.join": "{character} joined the troupe as a draft.",
    "troupe.leave": "{character} left the troupe.",
    "character.deleted": "{character} was deleted by its player.",
    "approval.request": "{actor} asked for {character} to be approved.",
    "approval.approved": "{actor} approved {character}.",
    "approval.declined": "{actor} declined {character}'s request.",
    "approval.withdrawn": "{actor} withdrew {character}'s request.",
    "standing.draft": "{actor} sent {character} back to draft: {reason}",
    "home_troupe.moved_away": "{character} moved its home troupe elsewhere.",
    "xp.award": "{actor} awarded {character} {amount} XP: {reason}",
    "staff.assigned": "{actor} made {member} {role}.",
    "staff.removed": "{actor} removed {member} from the staff.",
    "troupe.lead_appointed": "{actor} appointed {member} lead storyteller.",
    "troupe.renamed": "{actor} renamed the troupe to {name}.",
    "troupe.archived": "{actor} archived the troupe.",
    "troupe.sects_limited": "{actor} set which sects may join: {sects}.",
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
}


def message(action: str, actor: str | None, character: str | None, data: dict[str, Any]) -> str:
    template = MESSAGES.get(action, action.replace("_", " ").replace(".", ": "))
    values = {**data, "actor": actor or "Someone", "character": character or "A character"}
    try:
        return template.format(**values)
    except (KeyError, IndexError):
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
