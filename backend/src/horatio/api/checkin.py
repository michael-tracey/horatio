"""Game-night check-in (issue #421, horatio.checkin): staff open a game's check-in
for the door, players check in and land in their Play View, staff see who came and
award the game's XP to everyone there in one go."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from horatio import audit, checkin, sheets, suspensions, xp_range
from horatio.api.games import member_troupe
from horatio.api.troupe_profiles import ProfilePerson, someone
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import (
    Character,
    GameAttendance,
    PlayGame,
    ScheduledGame,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.permissions import (
    TroupeAction,
    allows,
    require_troupe_action,
    troupe_role,
    visible_character,
)

router = APIRouter(tags=["check-in"])

# How many past games staff see, to reach one whose XP is still to award.
PAST_GAMES = 5


class CheckInCharacter(BaseModel):
    id: uuid.UUID
    name: str
    checked_in: bool


class CheckInOffer(BaseModel):
    """A game whose check-in is open, and the caller's characters who can check in."""

    troupe_id: uuid.UUID
    troupe_name: str
    game_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    # The caller's active player characters in the troupe, home or visiting.
    characters: list[CheckInCharacter]


class CheckInIn(BaseModel):
    character_id: uuid.UUID
    # A full day's rest since the last game: Willpower starts full (MET: VtM core,
    # p. 288). Without one, it starts where the last game left it.
    rested: bool = True


class CheckedIn(BaseModel):
    character_id: uuid.UUID
    character_name: str
    # Checked in already: nothing changed.
    already: bool
    # The night started on the Play View; not for a game already over.
    play_started: bool


class CheckInState(BaseModel):
    open: bool
    # The door's code while check-in is open.
    code: str | None
    # Whether check-in can be opened now, and from when.
    can_open: bool
    opens_at: datetime


class Attendee(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player: ProfilePerson
    # Its home is this troupe, which awards its XP; a visitor's home troupe awards it.
    home: bool
    checked_in_at: datetime
    by_staff: bool
    # Whether its player said it had a full day's rest; None when no night started.
    rested: bool | None
    # XP earned in the calendar month so far (horatio.checkin.earned_this_month).
    month_xp: int


class Absentee(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str


class GameXp(BaseModel):
    amount: int | None
    awarded_at: datetime | None
    awarded_by: ProfilePerson | None


class GameNight(BaseModel):
    id: uuid.UUID
    troupe_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    checkin: CheckInState
    attendees: list[Attendee]
    # The troupe's other active player characters, to check in by hand.
    others: list[Absentee]
    # The troupe's usual XP for a game, and the game's XP once awarded.
    session_xp: int
    xp: GameXp
    can_award: bool
    # The book's guidance (MET: VtM core, p. 108).
    game_xp_low: int
    game_xp_high: int
    monthly_xp: int


class PastGame(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    attended: int
    xp_awarded: int | None


class GameXpIn(BaseModel):
    amount: int = Field(ge=1, le=1000)
    # The reason on each character's XP history, such as "Game, 18 October".
    reason: str = Field(min_length=1, max_length=500)
    # Add the amount to the troupe's XP floor and ceiling, as a game's XP.
    to_range: bool = True


class GameXpAwarded(BaseModel):
    characters: int
    total: int
    # Those it took past the book's monthly guidance, by name.
    past_monthly: list[str]


class AttendedGame(BaseModel):
    game_id: uuid.UUID
    troupe_id: uuid.UUID
    troupe_name: str
    starts_at: datetime
    ends_at: datetime
    # Its game on the Play View, by number; None when it was checked in afterwards.
    play_game_number: int | None


def troupe_game(
    db: Session, troupe_id: uuid.UUID, game_id: uuid.UUID
) -> tuple[Troupe, ScheduledGame]:
    troupe = db.get(Troupe, troupe_id)
    game = db.get(ScheduledGame, game_id)
    if troupe is None or game is None or game.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such game.")
    return troupe, game


def staff_game(
    db: Session,
    user: User,
    troupe_id: uuid.UUID,
    game_id: uuid.UUID,
    action: TroupeAction = TroupeAction.RUN_CHECKIN,
) -> tuple[Troupe, ScheduledGame]:
    troupe, game = troupe_game(db, troupe_id, game_id)
    require_troupe_action(db, user, troupe, action)
    return troupe, game


def runs_checkin(db: Session, user: User, troupe: Troupe) -> bool:
    return (troupe.archived_at is None or user.is_custodian) and allows(
        troupe_role(db, user, troupe), TroupeAction.RUN_CHECKIN, is_custodian=user.is_custodian
    )


def in_troupe(troupe: Troupe) -> Select[Character]:
    """Active player characters in the troupe now, home or visiting."""
    return (
        select(Character)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
            Character.kind == "pc",
            Character.status == "active",
        )
    )


def offer(db: Session, user: User, troupe: Troupe, game: ScheduledGame) -> CheckInOffer:
    mine = list(
        db.scalars(in_troupe(troupe).where(Character.player_id == user.id).order_by(Character.name))
    )
    here = set(
        db.scalars(
            select(GameAttendance.character_id).where(
                GameAttendance.game_id == game.id,
                GameAttendance.character_id.in_([c.id for c in mine]),
            )
        )
    )
    return CheckInOffer(
        troupe_id=troupe.id,
        troupe_name=troupe.name,
        game_id=game.id,
        starts_at=game.starts_at,
        ends_at=game.ends_at,
        characters=[CheckInCharacter(id=c.id, name=c.name, checked_in=c.id in here) for c in mine],
    )


def night_out(db: Session, user: User, troupe: Troupe, game: ScheduledGame) -> GameNight:
    rows = list(
        db.execute(
            select(GameAttendance, Character, User)
            .join(Character, GameAttendance.character_id == Character.id)
            .join(User, Character.player_id == User.id)
            .where(GameAttendance.game_id == game.id)
        )
    )
    rows.sort(key=lambda r: r[1].name.lower())
    month = checkin.earned_this_month(db, [c.id for _, c, _ in rows])
    here = {c.id for _, c, _ in rows}
    others = [
        (c, u)
        for c, u in db.execute(
            in_troupe(troupe).add_columns(User).join(User, Character.player_id == User.id)
        )
        if c.id not in here
    ]
    others.sort(key=lambda r: r[0].name.lower())
    awarded_by = db.get(User, game.xp_awarded_by) if game.xp_awarded_by else None
    return GameNight(
        id=game.id,
        troupe_id=troupe.id,
        starts_at=game.starts_at,
        ends_at=game.ends_at,
        checkin=CheckInState(
            open=checkin.is_open(game),
            code=game.checkin_code if checkin.is_open(game) else None,
            can_open=checkin.can_open(game),
            opens_at=checkin.opens_at(game),
        ),
        attendees=[
            Attendee(
                character_id=c.id,
                character_name=c.name,
                player=someone(u),
                home=c.home_troupe_id == troupe.id,
                checked_in_at=a.created_at,
                by_staff=a.by_staff,
                rested=a.rested,
                month_xp=month[c.id],
            )
            for a, c, u in rows
        ],
        others=[
            Absentee(character_id=c.id, character_name=c.name, player_name=u.display_name)
            for c, u in others
        ],
        session_xp=troupe.session_xp,
        xp=GameXp(
            amount=game.xp_awarded,
            awarded_at=game.xp_awarded_at,
            awarded_by=someone(awarded_by) if awarded_by else None,
        ),
        can_award=allows(
            troupe_role(db, user, troupe), TroupeAction.AWARD_XP, is_custodian=user.is_custodian
        ),
        game_xp_low=checkin.GAME_XP[0],
        game_xp_high=checkin.GAME_XP[1],
        monthly_xp=checkin.MONTHLY_XP,
    )


@router.get("/troupes/{troupe_id}/games/past")
def past_games(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[PastGame]:
    """The troupe's latest games already over, newest first, with how many came: for
    its staff, to see who came and award the XP."""
    troupe = db.get(Troupe, troupe_id)
    if troupe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such troupe.")
    require_troupe_action(db, user, troupe, TroupeAction.RUN_CHECKIN)
    games = list(
        db.scalars(
            select(ScheduledGame)
            .where(ScheduledGame.troupe_id == troupe.id, ScheduledGame.ends_at <= checkin.now())
            .order_by(ScheduledGame.starts_at.desc())
            .limit(PAST_GAMES)
        )
    )
    counts: dict[uuid.UUID, int] = {}
    for game_id in db.scalars(
        select(GameAttendance.game_id).where(GameAttendance.game_id.in_([g.id for g in games]))
    ):
        counts[game_id] = counts.get(game_id, 0) + 1
    return [
        PastGame(
            id=g.id,
            starts_at=g.starts_at,
            ends_at=g.ends_at,
            attended=counts.get(g.id, 0),
            xp_awarded=g.xp_awarded,
        )
        for g in games
    ]


@router.get("/troupes/{troupe_id}/games/{game_id}/night")
def read_night(
    troupe_id: uuid.UUID, game_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> GameNight:
    """The game's check-in, who came, and its XP: for the troupe's running staff."""
    troupe, game = staff_game(db, user, troupe_id, game_id)
    return night_out(db, user, troupe, game)


@router.put("/troupes/{troupe_id}/games/{game_id}/checkin")
def open_checkin(
    troupe_id: uuid.UUID, game_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> GameNight:
    """Open check-in with a new code for the door; any code before stops working."""
    troupe, game = staff_game(db, user, troupe_id, game_id)
    checkin.open_checkin(db, user, game)
    db.commit()
    return night_out(db, user, troupe, game)


@router.delete("/troupes/{troupe_id}/games/{game_id}/checkin")
def close_checkin(
    troupe_id: uuid.UUID, game_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> GameNight:
    """Close check-in: the code stops working. Staff can still check people in by hand."""
    troupe, game = staff_game(db, user, troupe_id, game_id)
    checkin.close_checkin(db, user, game)
    db.commit()
    return night_out(db, user, troupe, game)


@router.get("/checkin/{code}")
def read_code(code: str, db: DbSession, user: CurrentUser) -> CheckInOffer:
    """The game a door's code is for, while its check-in is open, with the caller's
    characters there."""
    game = checkin.game_for_code(db, code)
    if game is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "That code isn't open for check-in. Check it, or ask the storytellers for a new one.",
        )
    troupe = member_troupe(db, user, game.troupe_id)
    return offer(db, user, troupe, game)


@router.get("/troupes/{troupe_id}/games/{game_id}/checkin")
def read_checkin(
    troupe_id: uuid.UUID, game_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CheckInOffer:
    """The game, while its check-in is open, with the caller's characters there."""
    member_troupe(db, user, troupe_id)
    troupe, game = troupe_game(db, troupe_id, game_id)
    if not checkin.is_open(game):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Check-in for this game isn't open."
        )
    return offer(db, user, troupe, game)


@router.post("/troupes/{troupe_id}/games/{game_id}/attendance")
def check_in(
    troupe_id: uuid.UUID, game_id: uuid.UUID, body: CheckInIn, db: DbSession, user: CurrentUser
) -> CheckedIn:
    """Check a character in: its player, while check-in is open, or the troupe's
    running staff by hand. It starts the character's night on the Play View."""
    troupe, game = troupe_game(db, troupe_id, game_id)
    character = db.scalar(in_troupe(troupe).where(Character.id == body.character_id))
    staff = runs_checkin(db, user, troupe)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character in this troupe.")
    mine = character.player_id == user.id
    if not staff:
        if not mine:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only its player or the storytellers can check it in."
            )
        member_troupe(db, user, troupe.id)
        if not checkin.is_open(game):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Check-in for this game isn't open."
            )
    elif checkin.now() < checkin.opens_at(game):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, checkin.NOT_OPEN_YET)
    if game.xp_awarded is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This game's XP has been awarded, so check-in has closed. Award a late arrival"
            " from Award XP.",
        )
    suspensions.refuse_character(db, character)
    character = sheets.lock_character(db, character.id)
    attendance, new = checkin.check_in(
        db, user, game, character, by_staff=not mine, rested=body.rested
    )
    db.commit()
    return CheckedIn(
        character_id=character.id,
        character_name=character.name,
        already=not new,
        play_started=attendance.play_game_id is not None,
    )


@router.delete("/troupes/{troupe_id}/games/{game_id}/attendance/{character_id}")
def check_out(
    troupe_id: uuid.UUID,
    game_id: uuid.UUID,
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> GameNight:
    """Take a character off the game's attendance, by hand. Its Play View stays as it is."""
    troupe, game = staff_game(db, user, troupe_id, game_id)
    if game.xp_awarded is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This game's XP has been awarded already. Correct a character's award from its"
            " Experience tab.",
        )
    character = db.get(Character, character_id)
    if character is not None:
        checkin.check_out(db, user, game, character)
        db.commit()
    return night_out(db, user, troupe, game)


@router.post("/troupes/{troupe_id}/games/{game_id}/xp")
def award_game_xp(
    troupe_id: uuid.UUID, game_id: uuid.UUID, body: GameXpIn, db: DbSession, user: CurrentUser
) -> GameXpAwarded:
    """The game's XP to every character checked in whose home is this troupe, all at
    once, and once a game. Visitors are awarded by their own home troupes."""
    troupe, game = staff_game(db, user, troupe_id, game_id, TroupeAction.AWARD_XP)
    game = db.get_one(ScheduledGame, game.id, with_for_update=True)
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a note for the award.")
    if game.xp_awarded is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This game's XP has been awarded already.")
    if checkin.now() < game.starts_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A game's XP is awarded once it has started."
        )
    present = list(
        db.scalars(
            select(Character)
            .join(GameAttendance, GameAttendance.character_id == Character.id)
            .where(
                GameAttendance.game_id == game.id,
                Character.home_troupe_id == troupe.id,
                Character.kind == "pc",
                Character.status == "active",
            )
            .order_by(Character.name)
        )
    )
    if not present:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Nobody checked in calls this troupe home, so there is nobody to award here.",
        )
    before = checkin.earned_this_month(db, [c.id for c in present])
    for character in present:
        sheets.award_xp(db, user, character, body.amount, reason)
    if body.to_range:
        xp_range.add_game(db, user, troupe, body.amount, reason)
    # Awarding the XP ends check-in: everyone there has had it.
    checkin.close_checkin(db, user, game)
    game.xp_awarded = body.amount
    game.xp_awarded_at = checkin.now()
    game.xp_awarded_by = user.id
    audit.record(
        db,
        user,
        "xp.game_award",
        troupe_id=troupe.id,
        amount=body.amount,
        characters=len(present),
        game=checkin.when(game),
    )
    db.commit()
    return GameXpAwarded(
        characters=len(present),
        total=body.amount * len(present),
        past_monthly=[c.name for c in present if before[c.id] + body.amount > checkin.MONTHLY_XP],
    )


@router.get("/characters/{character_id}/attendance")
def attended(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[AttendedGame]:
    """The games the character came to, newest first."""
    character = visible_character(db, user, character_id)
    rows = db.execute(
        select(ScheduledGame, Troupe.name, PlayGame.number)
        .join(GameAttendance, GameAttendance.game_id == ScheduledGame.id)
        .join(Troupe, ScheduledGame.troupe_id == Troupe.id)
        .outerjoin(PlayGame, GameAttendance.play_game_id == PlayGame.id)
        .where(GameAttendance.character_id == character.id)
        .order_by(ScheduledGame.starts_at.desc())
    )
    return [
        AttendedGame(
            game_id=g.id,
            troupe_id=g.troupe_id,
            troupe_name=name,
            starts_at=g.starts_at,
            ends_at=g.ends_at,
            play_game_number=number,
        )
        for g, name, number in rows
    ]
