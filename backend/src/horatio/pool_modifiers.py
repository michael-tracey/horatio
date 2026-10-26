"""A player's own modifiers to a character's test pools (issue #188), kept per
character. The Pools tab and the printed sheet work out what they change."""

import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.models import Character, PoolModifier


class ModifierOut(BaseModel):
    id: uuid.UUID
    label: str
    amount: int
    # "all", "attack", "defense", an attribute, or "pool:<key>".
    pools: str
    when: str
    on: bool


def modifiers_out(db: Session, character: Character, *, only_on: bool = False) -> list[ModifierOut]:
    query = select(PoolModifier).where(PoolModifier.character_id == character.id)
    if only_on:
        query = query.where(PoolModifier.on.is_(True))
    return [
        ModifierOut(id=m.id, label=m.label, amount=m.amount, pools=m.pools, when=m.when, on=m.on)
        for m in db.scalars(query.order_by(PoolModifier.created_at, PoolModifier.id))
    ]
