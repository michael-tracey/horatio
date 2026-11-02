"""A troupe's game XP settings (issue #438, horatio.game_xp): its chart of XP by
earned-XP band and attendance kind, adjustments, the monthly cap and absentee games.
Its storytellers set them; anyone who may read its house rules reads them."""

import uuid

from fastapi import APIRouter, HTTPException, status

from horatio import game_xp
from horatio.auth.deps import CurrentUser, DbSession
from horatio.game_xp import GameXpSettings
from horatio.models import Troupe
from horatio.permissions import TroupeAction, require_troupe_action

router = APIRouter(prefix="/troupes/{troupe_id}/game-xp", tags=["game xp"])


@router.get("")
def read_game_xp(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> GameXpSettings:
    """The troupe's game XP settings. Like its house rules, anyone signed in may read them."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or (troupe.archived_at is not None and not user.is_custodian):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    return game_xp.settings(troupe)


@router.put("")
def save_game_xp(
    troupe_id: uuid.UUID, body: GameXpSettings, db: DbSession, user: CurrentUser
) -> GameXpSettings:
    """Set the troupe's game XP, all of it at once. The defaults are the book's way."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    require_troupe_action(db, user, troupe, TroupeAction.MANAGE_HOUSE_RULES)
    saved = game_xp.save(db, user, troupe, body)
    db.commit()
    return saved
