"""The custodian's tools (Custodian › Tools): maintenance that would otherwise need a
command on the server. Each previews what it would do before doing it."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from horatio import troupe_fit
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Troupe, User
from horatio.permissions import require_custodian

router = APIRouter(prefix="/tools", tags=["custodian"])


class FittedNpc(BaseModel):
    id: uuid.UUID
    name: str
    # Its sheet's worth in XP at the troupe's prices, before and after fitting.
    xp_now: int
    xp_after: int
    changed: bool


class SkippedNpc(BaseModel):
    id: uuid.UUID
    name: str
    why: str


class NpcPicksFit(BaseModel):
    troupe_id: uuid.UUID
    troupe_name: str
    fitted: list[FittedNpc]
    skipped: list[SkippedNpc]
    xp_now: int
    xp_after: int
    # How many NPCs fitting moves picks on (or moved, once fitted).
    changed: int


def custodians_troupe(db: DbSession, user: User, troupe_id: uuid.UUID) -> Troupe:
    require_custodian(user)
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return troupe


def out(troupe: Troupe, found: troupe_fit.TroupeFit) -> NpcPicksFit:
    return NpcPicksFit(
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        fitted=[
            FittedNpc(id=f.id, name=f.name, xp_now=f.xp_now, xp_after=f.xp_after, changed=f.changed)
            for f in found.fitted
        ],
        skipped=[SkippedNpc(id=s.id, name=s.name, why=s.why) for s in found.skipped],
        xp_now=sum(f.xp_now for f in found.fitted),
        xp_after=sum(f.xp_after for f in found.fitted),
        changed=found.changed,
    )


@router.get("/npc-picks/{troupe_id}")
def preview_npc_picks(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> NpcPicksFit:
    """What fitting the troupe's NPCs' creation picks would do. Changes nothing."""
    troupe = custodians_troupe(db, user, troupe_id)
    return out(troupe, troupe_fit.fit_troupe(db, troupe, apply=False))


@router.post("/npc-picks/{troupe_id}")
def fit_npc_picks(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> NpcPicksFit:
    """Fit the creation picks of the troupe's NPCs built without the wizard, keeping
    what staff set by hand. Fitting again changes nothing."""
    troupe = custodians_troupe(db, user, troupe_id)
    done = troupe_fit.fit(db, user, troupe)
    db.commit()
    return out(troupe, done)
