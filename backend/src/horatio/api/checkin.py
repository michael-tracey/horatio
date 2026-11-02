"""Game-night check-in (issue #421, horatio.checkin): staff open a game's check-in
for the door, players check in and land in their Play View, staff see who came and
award the game's XP to everyone there in one go: the same to each, or by the
troupe's game XP chart, with absentee games (issue #438, horatio.game_xp)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from horatio import audit, checkin, game_xp, sheets, suspensions, xp_range
from horatio.api.games import member_troupe
from horatio.api.troupe_profiles import ProfilePerson, someone
from horatio.auth.deps import CurrentUser, DbSession
from horatio.game_xp import GameXpSettings
from horatio.models import (
    Character,
    GameAttendance,
    GameXpAward,
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
    # "attended", or "absentee": it missed the game, recorded as an absentee game.
    kind: game_xp.Kind = "attended"


class NotHere(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str
    # Its home is this troupe, so it can be marked absentee here.
    home: bool = True


class XpLine(BaseModel):
    """What one character would get for the game (horatio.game_xp): its attendance
    kind, its band and the chart's figure, and what the monthly cap leaves."""

    character_id: uuid.UUID
    character_name: str
    kind: game_xp.Kind
    # XP earned in all, which picks the band, and this calendar month.
    earned_xp: int
    month_xp: int
    # Its band on the chart and the chart's figure; None with no chart, when the
    # game's flat amount (or absentee amount) is its figure.
    band: str | None
    figure: int | None
    # How often each adjustment was ticked for it this month, by key.
    used: dict[str, int]


class GameXpGiven(BaseModel):
    """What one character got for the game, once awarded."""

    character_id: uuid.UUID
    character_name: str
    kind: game_xp.Kind
    band: str | None
    figure: int
    adjustments: list[str]
    capped: int
    override: int | None
    override_reason: str
    amount: int


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
    # Characters recorded as absentee for it (horatio.game_xp): never counted as here.
    absentees: list[Attendee] = []
    # The troupe's other active player characters, to check in by hand.
    others: list[NotHere]
    # The troupe's usual XP for a game, and the game's XP once awarded.
    session_xp: int
    xp: GameXp
    can_award: bool
    # The book's guidance (MET: VtM core, p. 108).
    game_xp_low: int
    game_xp_high: int
    # The monthly figure the troupe works to: the book's 10 unless it sets its own.
    monthly_xp: int
    # The troupe's game XP chart, adjustments, cap and absentee settings.
    game_xp: GameXpSettings = GameXpSettings()
    # Each character the award would go to, before it is made; what each got, after.
    xp_lines: list[XpLine] = []
    given: list[GameXpGiven] = []


class PastGame(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    attended: int
    xp_awarded: int | None


class CharacterXpIn(BaseModel):
    """Staff's choice for one character: adjustments ticked, or its figure set by hand."""

    character_id: uuid.UUID
    ticks: list[str] = Field(default_factory=list, max_length=20)
    override: int | None = Field(default=None, ge=0, le=1000)
    override_reason: str = Field(default="", max_length=300)


class GameXpIn(BaseModel):
    # The XP for each character there, with no chart (horatio.game_xp: "Flat"). With a
    # chart, each character's band gives it, and this is not used.
    amount: int = Field(ge=1, le=1000)
    # With no chart, the XP for an absentee game.
    absentee_amount: int | None = Field(default=None, ge=0, le=1000)
    # The reason on each character's XP history, such as "Game, 18 October".
    reason: str = Field(min_length=1, max_length=500)
    # Add the game's XP to the troupe's XP floor and ceiling.
    to_range: bool = True
    characters: list[CharacterXpIn] = Field(default_factory=list)


class GameXpAwarded(BaseModel):
    characters: int
    total: int
    # Those it took past the monthly figure, by name, while the troupe warns.
    past_monthly: list[str]
    # Those the cap held some back from, by name, while the troupe caps.
    capped: list[str] = []


class MissedGame(BaseModel):
    """A game that has started, whose XP is still to award, and the caller's characters
    at home in the troupe: for a player to mark one absentee, where the troupe allows."""

    game_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    characters: list[CheckInCharacter]
    # Those of them marked absentee.
    absentee: list[uuid.UUID]


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
                checkin.ATTENDED,
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


def to_award(db: Session, troupe: Troupe, game: ScheduledGame) -> list[tuple[Character, str]]:
    """The characters the game's XP goes to, with their attendance kind: those checked
    in or absentee whose home is this troupe, active player characters."""
    return [
        (c, kind)
        for c, kind in db.execute(
            select(Character, GameAttendance.kind)
            .join(GameAttendance, GameAttendance.character_id == Character.id)
            .where(
                GameAttendance.game_id == game.id,
                Character.home_troupe_id == troupe.id,
                Character.kind == "pc",
                Character.status == "active",
            )
            .order_by(Character.name)
        )
    ]


def given_out(db: Session, game: ScheduledGame) -> list[GameXpGiven]:
    rows = db.execute(
        select(GameXpAward, Character.name)
        .join(Character, GameXpAward.character_id == Character.id)
        .where(GameXpAward.game_id == game.id)
        .order_by(Character.name)
    )
    return [
        GameXpGiven(
            character_id=a.character_id,
            character_name=name,
            kind="absentee" if a.kind == "absentee" else "attended",
            band=a.band,
            figure=a.figure,
            adjustments=[f"{t['name']} {game_xp.signed(int(t['amount']))}" for t in a.adjustments],
            capped=a.capped,
            override=a.override,
            override_reason=a.override_reason,
            amount=a.amount,
        )
        for a, name in rows
    ]


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
    found = game_xp.settings(troupe)
    lines = game_xp.lines(db, troupe, to_award(db, troupe, game)) if game.xp_awarded is None else []

    def attendee(a: GameAttendance, c: Character, u: User) -> Attendee:
        return Attendee(
            character_id=c.id,
            character_name=c.name,
            player=someone(u),
            home=c.home_troupe_id == troupe.id,
            checked_in_at=a.created_at,
            by_staff=a.by_staff,
            rested=a.rested,
            month_xp=month[c.id],
            kind="absentee" if a.kind == "absentee" else "attended",
        )

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
        attendees=[attendee(a, c, u) for a, c, u in rows if a.kind != "absentee"],
        absentees=[attendee(a, c, u) for a, c, u in rows if a.kind == "absentee"],
        others=[
            NotHere(
                character_id=c.id,
                character_name=c.name,
                player_name=u.display_name,
                home=c.home_troupe_id == troupe.id,
            )
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
        monthly_xp=game_xp.monthly_limit(found),
        game_xp=found,
        xp_lines=[
            XpLine(
                character_id=line.character.id,
                character_name=line.character.name,
                kind="absentee" if line.kind == "absentee" else "attended",
                earned_xp=line.earned,
                month_xp=line.month,
                band=line.band,
                figure=line.figure,
                used=line.used,
            )
            for line in lines
        ],
        given=given_out(db, game) if game.xp_awarded is not None else [],
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
        select(GameAttendance.game_id).where(
            GameAttendance.game_id.in_([g.id for g in games]), checkin.ATTENDED
        )
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
    present = to_award(db, troupe, game)
    if not present:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Nobody checked in calls this troupe home, so there is nobody to award here.",
        )
    found = game_xp.settings(troupe)
    choices = {c.character_id: c for c in body.characters}
    if len(choices) != len(body.characters):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A character is listed more than once."
        )
    if set(choices) - {c.id for c, _ in present}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Only characters at the game whose home is this troupe can be awarded here.",
        )
    given = [
        game_xp.work_out(
            found,
            line,
            game_xp.Choice(
                ticks=choice.ticks,
                override=choice.override,
                override_reason=choice.override_reason,
            )
            if (choice := choices.get(line.character.id))
            else game_xp.Choice(),
            flat=body.amount,
            flat_absentee=body.absentee_amount,
            reason=reason,
        )
        for line in game_xp.lines(db, troupe, present)
    ]
    game_xp.give(db, user, game, given)
    figure = game_xp.range_figure(db, troupe, body.amount)
    if body.to_range:
        xp_range.add_game(db, user, troupe, figure, reason)
    # Awarding the XP ends check-in: everyone there has had it.
    checkin.close_checkin(db, user, game)
    game.xp_awarded = figure
    game.xp_awarded_at = checkin.now()
    game.xp_awarded_by = user.id
    total = sum(g.amount for g in given)
    if all(g.amount == body.amount for g in given):
        audit.record(
            db,
            user,
            "xp.game_award",
            troupe_id=troupe.id,
            amount=body.amount,
            characters=len(given),
            game=checkin.when(game),
        )
    else:
        audit.record(
            db,
            user,
            "xp.game_award_chart",
            troupe_id=troupe.id,
            total=total,
            characters=len([g for g in given if g.amount > 0]),
            game=checkin.when(game),
        )
    db.commit()
    limit = game_xp.monthly_limit(found)
    return GameXpAwarded(
        characters=len([g for g in given if g.amount > 0]),
        total=total,
        past_monthly=[
            g.line.character.name for g in given if g.line.month + g.amount > limit and g.amount
        ]
        if found.cap == "warn"
        else [],
        capped=[g.line.character.name for g in given if g.capped],
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
        .where(GameAttendance.character_id == character.id, checkin.ATTENDED)
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


class AbsenteeMarked(BaseModel):
    character_id: uuid.UUID
    character_name: str
    absentee: bool


def absentee_character(
    db: Session, user: User, troupe: Troupe, game: ScheduledGame, character_id: uuid.UUID
) -> tuple[Character, bool]:
    """The character to mark absentee for the game, or take it back, and whether the
    caller is running staff: its player may too, where the troupe allows."""
    found = game_xp.settings(troupe)
    if not found.absentee:
        raise HTTPException(status.HTTP_409_CONFLICT, "This troupe doesn't record absentee games.")
    character = db.scalar(
        in_troupe(troupe).where(Character.id == character_id, Character.home_troupe_id == troupe.id)
    )
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character at home in this troupe.")
    staff = runs_checkin(db, user, troupe)
    if not staff:
        if character.player_id != user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only its player or the storytellers can mark it absentee.",
            )
        if not found.absentee_by_players:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "In this troupe, only the storytellers mark a character absentee.",
            )
        member_troupe(db, user, troupe.id)
    if checkin.now() < game.starts_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A character is marked absentee once the game has started.",
        )
    if game.xp_awarded is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This game's XP has been awarded already, so who came is settled. Award an"
            " absentee game late from Award XP.",
        )
    return character, staff


@router.put("/troupes/{troupe_id}/games/{game_id}/absentee/{character_id}")
def mark_absentee(
    troupe_id: uuid.UUID,
    game_id: uuid.UUID,
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> AbsenteeMarked:
    """Record a character as absentee for a game it missed (horatio.game_xp): the
    troupe's running staff, or its player where the troupe allows. Payments aren't
    tracked here: marking it is the record."""
    troupe, game = troupe_game(db, troupe_id, game_id)
    character, staff = absentee_character(db, user, troupe, game, character_id)
    suspensions.refuse_character(db, character)
    checkin.mark_absentee(db, user, game, character, by_staff=staff)
    db.commit()
    return AbsenteeMarked(character_id=character.id, character_name=character.name, absentee=True)


@router.delete("/troupes/{troupe_id}/games/{game_id}/absentee/{character_id}")
def unmark_absentee(
    troupe_id: uuid.UUID,
    game_id: uuid.UUID,
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> AbsenteeMarked:
    """Take back a character's absentee game. One checked in is left as it is."""
    troupe, game = troupe_game(db, troupe_id, game_id)
    character, _ = absentee_character(db, user, troupe, game, character_id)
    found = checkin.attendance_of(db, game, character)
    if found is not None and found.kind == "absentee":
        checkin.check_out(db, user, game, character)
        db.commit()
    return AbsenteeMarked(character_id=character.id, character_name=character.name, absentee=False)


@router.get("/troupes/{troupe_id}/games/missed")
def missed_games(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[MissedGame]:
    """The troupe's games that have started and whose XP is still to award, newest
    first, with the caller's characters at home here that didn't check in: for a player
    to mark one absentee, where the troupe lets players. Empty where it doesn't."""
    troupe = member_troupe(db, user, troupe_id)
    found = game_xp.settings(troupe)
    if not (found.absentee and found.absentee_by_players):
        return []
    mine = list(
        db.scalars(
            in_troupe(troupe)
            .where(Character.player_id == user.id, Character.home_troupe_id == troupe.id)
            .order_by(Character.name)
        )
    )
    if not mine:
        return []
    games = list(
        db.scalars(
            select(ScheduledGame)
            .where(
                ScheduledGame.troupe_id == troupe.id,
                ScheduledGame.starts_at <= checkin.now(),
                ScheduledGame.xp_awarded.is_(None),
            )
            .order_by(ScheduledGame.starts_at.desc())
            .limit(PAST_GAMES)
        )
    )
    kinds: dict[tuple[uuid.UUID, uuid.UUID], str] = {
        (game_id, character_id): kind
        for game_id, character_id, kind in db.execute(
            select(GameAttendance.game_id, GameAttendance.character_id, GameAttendance.kind).where(
                GameAttendance.game_id.in_([g.id for g in games]),
                GameAttendance.character_id.in_([c.id for c in mine]),
            )
        )
    }
    out: list[MissedGame] = []
    for g in games:
        away = [c for c in mine if kinds.get((g.id, c.id)) != "attended"]
        if not away:
            continue
        out.append(
            MissedGame(
                game_id=g.id,
                starts_at=g.starts_at,
                ends_at=g.ends_at,
                characters=[CheckInCharacter(id=c.id, name=c.name, checked_in=False) for c in away],
                absentee=[c.id for c in away if kinds.get((g.id, c.id)) == "absentee"],
            )
        )
    return out
