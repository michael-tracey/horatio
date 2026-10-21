"""Awarding a game's XP to a troupe's characters at once (issue #55): everyone gets
a set amount, raised or lowered per character, with one note as the reason."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import sheets, xp_range
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, User
from horatio.permissions import TroupeAction

router = APIRouter(prefix="/troupes/{troupe_id}/xp-awards", tags=["xp awards"])


class AwardableCharacter(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str


class AwardsOut(BaseModel):
    # What the set amount starts at: the troupe's usual XP for a session.
    session_xp: int
    characters: list[AwardableCharacter]


class CharacterAward(BaseModel):
    character_id: uuid.UUID
    # 0 gives this character nothing, such as someone who missed the game.
    amount: int = Field(ge=0, le=1000)


class BulkAward(BaseModel):
    # The reason every character's entry gets, such as "Game, 18 October".
    reason: str = Field(min_length=1, max_length=500)
    awards: list[CharacterAward]
    # The game's XP, as everyone got it before any was raised or lowered: added to
    # the troupe's XP floor and ceiling. None leaves them as they are.
    game_xp: int | None = Field(default=None, ge=0, le=1000)


class BulkAwarded(BaseModel):
    characters: int
    total: int


def awardable(db: DbSession, troupe_id: uuid.UUID) -> list[tuple[Character, User]]:
    """Active player characters whose home this troupe is: the ones it awards XP.
    Visitors are awarded by their own home troupes; NPCs earn none."""
    rows = db.execute(
        select(Character, User)
        .join(User, Character.player_id == User.id)
        .where(
            Character.home_troupe_id == troupe_id,
            Character.kind == "pc",
            Character.status == "active",
        )
    )
    return sorted(((c, u) for c, u in rows), key=lambda r: r[0].name.lower())


@router.get("")
def characters_to_award(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> AwardsOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.AWARD_XP)
    return AwardsOut(
        session_xp=troupe.session_xp,
        characters=[
            AwardableCharacter(character_id=c.id, character_name=c.name, player_name=u.display_name)
            for c, u in awardable(db, troupe_id)
        ],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def award_all(
    troupe_id: uuid.UUID, body: BulkAward, db: DbSession, user: CurrentUser
) -> BulkAwarded:
    """Each character an ordinary award entry, all together or none at all."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.AWARD_XP)
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a note for the award.")
    ids = [a.character_id for a in body.awards]
    if len(set(ids)) != len(ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A character is listed more than once."
        )
    characters = {c.id: c for c, _ in awardable(db, troupe_id)}
    strangers = [i for i in ids if i not in characters]
    if strangers:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Only active player characters whose home is this troupe can be awarded here.",
        )
    given = [a for a in body.awards if a.amount > 0]
    if not given:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nobody would get any XP.")
    for award in given:
        sheets.award_xp(db, user, characters[award.character_id], award.amount, reason)
    if body.game_xp:
        xp_range.add_game(db, user, troupe, body.game_xp, reason)
    db.commit()
    return BulkAwarded(characters=len(given), total=sum(a.amount for a in given))
