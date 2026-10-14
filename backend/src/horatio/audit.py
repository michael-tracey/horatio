"""Writing the audit log."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from horatio.models import AuditEvent, Character, User


def record(
    db: Session,
    actor: User | None,
    action: str,
    *,
    troupe_id: uuid.UUID | None = None,
    character_id: uuid.UUID | None = None,
    **data: Any,
) -> None:
    if character_id is not None and "character_name" not in data:
        # Kept with the event, so the log still reads after a character is deleted.
        character = db.get(Character, character_id)
        if character is not None:
            data["character_name"] = character.name
    db.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            troupe_id=troupe_id,
            character_id=character_id,
            action=action,
            data={k: str(v) if isinstance(v, uuid.UUID) else v for k, v in data.items()},
        )
    )
