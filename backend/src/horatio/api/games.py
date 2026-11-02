"""RSVPs to a troupe's scheduled games (issue #420): each member says whether they
mean to come, and staff see who, before they plan.

A member is anyone on the troupe's staff, or the player of an active character in
it (horatio.permissions.is_member). An RSVP is one per person, whichever of their
characters they bring: Coming, Maybe or Not coming, changed or taken back until
the game is over. Every member sees how many said each; only staff see who.

An RSVP is intent. Who actually came is recorded at the game, apart from this.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import checkin
from horatio.api.troupe_profiles import ProfilePerson, someone, upcoming
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Character,
    GameAttendance,
    GameRsvp,
    ScheduledGame,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.permissions import TroupeAction, allows, is_member, troupe_role

router = APIRouter(prefix="/troupes/{troupe_id}/games", tags=["games"])

Answer = Literal["coming", "maybe", "not_coming"]


class RsvpIn(BaseModel):
    answer: Answer


class RsvpOut(BaseModel):
    person: ProfilePerson
    answer: Answer
    # Their active characters in the troupe, by name: none for staff who play none.
    characters: list[str]


class GameRsvpsOut(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    # The caller's own answer, or None for none yet.
    my_answer: Answer | None
    coming: int
    maybe: int
    not_coming: int
    # Who said what, coming first, for the troupe's staff; None for anyone else.
    answers: list[RsvpOut] | None
    # Check-in at the door (horatio.checkin): whether it is open, how many characters
    # have checked in, and which of the caller's, by name.
    checkin_open: bool
    checked_in: int
    my_checked_in: list[str]


def member_troupe(db: Session, user: User, troupe_id: uuid.UUID) -> Troupe:
    """The troupe, if `user` is a member of it; 404 if there is no such troupe,
    403 if they are not a member."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    if not is_member(db, user, troupe):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the troupe's staff and players can do that."
        )
    return troupe


ORDER = {"coming": 0, "maybe": 1, "not_coming": 2}


def games_out(
    db: Session, user: User, troupe: Troupe, games: list[ScheduledGame]
) -> list[GameRsvpsOut]:
    """Each game with its answers, asked of the database a few times in all."""
    staff = allows(
        troupe_role(db, user, troupe), TroupeAction.VIEW_RSVPS, is_custodian=user.is_custodian
    )
    rsvps = list(db.scalars(select(GameRsvp).where(GameRsvp.game_id.in_([g.id for g in games]))))
    here = list(
        db.execute(
            select(GameAttendance.game_id, Character.name, Character.player_id)
            .join(Character, GameAttendance.character_id == Character.id)
            .where(GameAttendance.game_id.in_([g.id for g in games]), checkin.ATTENDED)
            .order_by(Character.name)
        )
    )
    people: dict[uuid.UUID, User] = {}
    characters: dict[uuid.UUID, list[str]] = {}
    if staff and rsvps:
        ids = {r.user_id for r in rsvps}
        people = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}
        for player_id, name in db.execute(
            select(Character.player_id, Character.name)
            .join(TroupeMembership, TroupeMembership.character_id == Character.id)
            .where(
                TroupeMembership.troupe_id == troupe.id,
                TroupeMembership.left_at.is_(None),
                Character.kind == "pc",
                Character.status == "active",
                Character.player_id.in_(ids),
            )
            .order_by(Character.name)
        ):
            characters.setdefault(player_id, []).append(name)

    out: list[GameRsvpsOut] = []
    for game in games:
        said = [r for r in rsvps if r.game_id == game.id]
        mine = next((r for r in said if r.user_id == user.id), None)
        came = [(name, player) for game_id, name, player in here if game_id == game.id]
        answers = None
        if staff:
            answers = [
                RsvpOut(
                    person=someone(people[r.user_id]),
                    answer=cast(Answer, r.answer),
                    characters=characters.get(r.user_id, []),
                )
                for r in sorted(
                    said,
                    key=lambda r: (ORDER[r.answer], people[r.user_id].display_name.lower()),
                )
            ]
        out.append(
            GameRsvpsOut(
                id=game.id,
                starts_at=game.starts_at,
                ends_at=game.ends_at,
                my_answer=cast(Answer, mine.answer) if mine else None,
                coming=sum(r.answer == "coming" for r in said),
                maybe=sum(r.answer == "maybe" for r in said),
                not_coming=sum(r.answer == "not_coming" for r in said),
                answers=answers,
                checkin_open=checkin.is_open(game),
                checked_in=len(came),
                my_checked_in=[name for name, player in came if player == user.id],
            )
        )
    return out


@router.get("")
def list_games(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[GameRsvpsOut]:
    """The troupe's games still to come (or under way), soonest first, with how
    many are coming: for its members."""
    troupe = member_troupe(db, user, troupe_id)
    return games_out(db, user, troupe, upcoming(db, troupe))


def open_game(db: Session, user: User, troupe_id: uuid.UUID, game_id: uuid.UUID) -> ScheduledGame:
    troupe = member_troupe(db, user, troupe_id)
    game = db.get(ScheduledGame, game_id)
    if game is None or game.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such game.")
    if game.ends_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That game is over.")
    return game


def one_out(db: Session, user: User, game: ScheduledGame) -> GameRsvpsOut:
    return games_out(db, user, db.get_one(Troupe, game.troupe_id), [game])[0]


@router.put("/{game_id}/rsvp")
def answer(
    troupe_id: uuid.UUID, game_id: uuid.UUID, body: RsvpIn, db: DbSession, user: CurrentUser
) -> GameRsvpsOut:
    """Say whether you are coming, in place of any answer before."""
    game = open_game(db, user, troupe_id, game_id)
    rsvp = db.scalar(
        select(GameRsvp).where(GameRsvp.game_id == game.id, GameRsvp.user_id == user.id)
    )
    if rsvp is None:
        db.add(GameRsvp(game_id=game.id, user_id=user.id, answer=body.answer))
    else:
        rsvp.answer = body.answer
    db.commit()
    return one_out(db, user, game)


@router.delete("/{game_id}/rsvp")
def take_back(
    troupe_id: uuid.UUID, game_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> GameRsvpsOut:
    """Take back your answer, saying nothing either way."""
    game = open_game(db, user, troupe_id, game_id)
    rsvp = db.scalar(
        select(GameRsvp).where(GameRsvp.game_id == game.id, GameRsvp.user_id == user.id)
    )
    if rsvp is not None:
        db.delete(rsvp)
        db.commit()
    return one_out(db, user, game)
