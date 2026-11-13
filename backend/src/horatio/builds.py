"""Characters being built to a troupe's rules that haven't asked to join it yet (#774).

A player builds a character by a troupe's rules until a home troupe accepts it
(Character.building_troupe_id; horatio.sheets.rules_troupe). Once its player asks
that troupe to make it home, it waits in the troupe's approval queue. Before then,
its storytellers and assistant storytellers see it here, under Being built: to know
who is coming, help a player who is stuck, and see a build that won't pass.

A character with a home troupe plays by that troupe's rules, whatever troupe it was
once built for, so only one with no home troupe is being built for a troupe.
"""

import uuid

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.orm import Session

from horatio.models import Approval, Character


def building_for(troupe_id: uuid.UUID) -> ColumnElement[bool]:
    """The condition on Character: an active PC built by the troupe's rules, with no
    home troupe and no request waiting to make the troupe its home."""
    asked = exists().where(
        Approval.character_id == Character.id,
        Approval.troupe_id == troupe_id,
        Approval.kind == "home_troupe_change",
        Approval.status == "pending",
    )
    return (
        (Character.kind == "pc")
        & (Character.status == "active")
        & Character.home_troupe_id.is_(None)
        & (Character.building_troupe_id == troupe_id)
        & ~asked
    )


def count(db: Session, troupe_id: uuid.UUID) -> int:
    found = select(func.count()).select_from(Character).where(building_for(troupe_id))
    return db.scalar(found) or 0


def is_building_for(db: Session, character: Character, troupe_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(select(exists().where(Character.id == character.id, building_for(troupe_id))))
    )
