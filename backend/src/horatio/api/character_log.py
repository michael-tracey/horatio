"""A character's own log: what was done to it, when and by whom."""

import uuid
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import or_, select

from horatio.api.roster import LogEntry, log_entries
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import AuditEvent, Troupe, User
from horatio.permissions import TroupeAction, allows, troupe_role, visible_character

router = APIRouter(prefix="/characters/{character_id}", tags=["log"])


@router.get("/log")
def character_log(
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    before: datetime | None = None,
    limit: int = 200,
) -> list[LogEntry]:
    """Everything that happened to the character, newest first. Its player sees it
    all; a troupe's staff see the sheet's own history and what happened in their
    troupe, not in the character's other troupes."""
    character = visible_character(db, user, character_id)
    query = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(AuditEvent.character_id == character.id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(min(max(limit, 1), 500))
    )
    if not (user.is_custodian or (character.kind == "pc" and character.player_id == user.id)):
        troupe_ids = set(
            db.scalars(select(AuditEvent.troupe_id).where(AuditEvent.character_id == character.id))
        ) - {None}
        mine = [
            t.id
            for t in db.scalars(select(Troupe).where(Troupe.id.in_(troupe_ids)))
            if allows(troupe_role(db, user, t), TroupeAction.VIEW_MEMBER_CHARACTERS)
        ]
        query = query.where(or_(AuditEvent.troupe_id.is_(None), AuditEvent.troupe_id.in_(mine)))
    if before is not None:
        query = query.where(AuditEvent.created_at < before)
    return log_entries(db, query)
