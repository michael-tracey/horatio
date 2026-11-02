"""Game-night check-in (issue #421): who came to each of a troupe's scheduled games,
and the start of their night on the Play View.

Staff open a game's check-in, which gives the door a short code, and a QR code of a
link to it. A player scans or types the code, or taps Check in on the game, picks
the character they are playing tonight, and lands in its Play View. Staff can check
a character in or out by hand too. Check-in opens from OPENS_BEFORE the game starts
and works until it ends. A new code stops the old one working, and so does closing
check-in.

Checking in starts or joins the character's night as the Play View does
(horatio.play): its game now, if that has no taps yet or only tonight's; otherwise
a reset ends the last game, kept with its log, and starts the next. Blood starts as
the Play View has it: the troupe's "Blood at the start of a game", or half if the
character fed short and the troupe tracks feeding. Willpower starts full after a
complete day's rest (MET: VtM core, p. 288). The player says whether the character
had one; if not, it starts where the last game left it.

Attendance is fact, apart from the RSVP (intent), and is what staff award a game's
XP from (horatio.api.checkin). The book suggests 3 to 5 XP a game, and no more than
8 to 10 a month (core, p. 108, "XP for Playing"), so an award that takes a character
past MONTHLY_XP earned in the calendar month is warned of, never refused. A troupe
may chart its game XP instead, cap it monthly, and record absentee games
(horatio.game_xp). An absentee game is its own kind of attendance, never counted as
having been there: ATTENDED picks out the characters who came.
"""

import secrets
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, play
from horatio.models import Character, GameAttendance, PlayGame, ScheduledGame, User, XpEntry
from horatio.sheets import conflict, unprocessable

# Check-in can open this long before a game starts, and taps made on the Play View
# since then are tonight's.
OPENS_BEFORE = timedelta(hours=12)
# No 0 or O, 1 or I, to read off a sign in a dim room.
CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
NOT_OPEN_YET = (
    f"Check-in opens {int(OPENS_BEFORE.total_seconds() // 3600)} hours before the game starts."
)
# The book's guidance (MET: VtM core, p. 108): 3 to 5 XP a game, and no more than
# 8 to 10 a month. Passing the higher figure is warned of.
GAME_XP = (3, 5)
MONTHLY_XP = 10
# Awards that are not XP earned in play: a new character's starting XP
# (horatio.sheets.start_character), and the top-up and extra a troupe gives on
# joining (horatio.xp_range.top_up, give_extra). Matched by how their reasons start.
NOT_EARNED = ("Starting experience", "Top-up to ", "Extra XP on joining ")
# Attendance that was being there: not an absentee game (horatio.game_xp).
ATTENDED = GameAttendance.kind == "attended"


def now() -> datetime:
    return datetime.now(UTC)


def opens_at(game: ScheduledGame) -> datetime:
    return game.starts_at - OPENS_BEFORE


def can_open(game: ScheduledGame, at: datetime | None = None) -> bool:
    """Whether check-in can be open now: from OPENS_BEFORE the game starts until it ends."""
    at = at or now()
    return opens_at(game) <= at < game.ends_at


def is_open(game: ScheduledGame, at: datetime | None = None) -> bool:
    """Staff have opened check-in, and the game has not ended."""
    return game.checkin_code is not None and (at or now()) < game.ends_at


def tidy_code(raw: str) -> str:
    """A code as typed, in capitals, without the spaces or dashes a sign might show."""
    return "".join(c for c in raw.upper() if c.isalnum())


def game_for_code(db: Session, raw: str) -> ScheduledGame | None:
    """The game whose check-in is open with this code, if any."""
    code = tidy_code(raw)
    if len(code) != CODE_LENGTH:
        return None
    game = db.scalar(select(ScheduledGame).where(ScheduledGame.checkin_code == code))
    return game if game is not None and is_open(game) else None


def when(game: ScheduledGame) -> str:
    """The game's day, for the log: "9 March 2030"."""
    return f"{game.starts_at.astimezone(UTC):%-d %B %Y}"


def open_checkin(db: Session, actor: User, game: ScheduledGame) -> None:
    """Open check-in with a new code, which stops any old one working."""
    if not can_open(game):
        if now() >= game.ends_at:
            raise unprocessable("That game is over.")
        raise unprocessable(NOT_OPEN_YET)
    while True:
        code = "".join(secrets.choice(CODE_LETTERS) for _ in range(CODE_LENGTH))
        if db.scalar(select(ScheduledGame.id).where(ScheduledGame.checkin_code == code)) is None:
            break
    game.checkin_code = code
    audit.record(db, actor, "play.checkin_opened", troupe_id=game.troupe_id, game=when(game))
    db.flush()


def close_checkin(db: Session, actor: User, game: ScheduledGame) -> None:
    if game.checkin_code is None:
        return
    game.checkin_code = None
    audit.record(db, actor, "play.checkin_closed", troupe_id=game.troupe_id, game=when(game))
    db.flush()


def left_willpower(db: Session, character: Character, night: PlayGame) -> int | None:
    """Willpower as the game before `night` ended; None, for full, before a first game."""
    before = db.scalar(
        select(PlayGame)
        .where(
            PlayGame.character_id == character.id,
            PlayGame.number < night.number,
            PlayGame.ended_at.is_not(None),
        )
        .order_by(PlayGame.number.desc())
        .limit(1)
    )
    value = before.state.get("willpower") if before is not None else None
    return value if isinstance(value, int) else None


def start_night(
    db: Session, character: Character, actor: User, game: ScheduledGame, *, rested: bool
) -> PlayGame:
    """Start or join the character's night on the Play View: its game now, unless that
    has taps from before tonight, when a reset ends it and starts the next. The caller
    holds the character's lock."""
    current = play.current_game(db, character)
    if current is not None and any(
        tap.happened_at < opens_at(game) for tap in play.game_events(db, current)
    ):
        play.reset(db, character, actor, troupe_id=game.troupe_id)
    night = play.start_game(db, character)
    night.willpower_start = None if rested else left_willpower(db, character, night)
    db.flush()
    return night


def attendance_of(db: Session, game: ScheduledGame, character: Character) -> GameAttendance | None:
    return db.scalar(
        select(GameAttendance).where(
            GameAttendance.game_id == game.id, GameAttendance.character_id == character.id
        )
    )


def check_in(
    db: Session,
    actor: User,
    game: ScheduledGame,
    character: Character,
    *,
    by_staff: bool,
    rested: bool,
) -> tuple[GameAttendance, bool]:
    """Record the character at the game and, while the game is not over, start its
    night. Says whether it is new: checking in twice changes nothing. The caller holds
    the character's lock."""
    found = attendance_of(db, game, character)
    if found is not None and found.kind == "absentee":
        # It came after all: staff put right an absentee game.
        db.delete(found)
        db.flush()
    elif found is not None:
        return found, False
    night = start_night(db, character, actor, game, rested=rested) if now() < game.ends_at else None
    attendance = GameAttendance(
        game_id=game.id,
        character_id=character.id,
        checked_in_by=actor.id,
        by_staff=by_staff,
        play_game_id=night.id if night else None,
        rested=rested if night else None,
    )
    db.add(attendance)
    audit.record(
        db,
        actor,
        "play.checked_in",
        troupe_id=game.troupe_id,
        character_id=character.id,
        game=when(game),
    )
    db.flush()
    return attendance, True


def mark_absentee(
    db: Session, actor: User, game: ScheduledGame, character: Character, *, by_staff: bool
) -> GameAttendance:
    """Record the character as absentee for the game (horatio.game_xp). Marking it
    twice changes nothing; a character who checked in came, and is not absentee."""
    found = attendance_of(db, game, character)
    if found is not None:
        if found.kind != "absentee":
            raise conflict(f"{character.name} checked in to this game, so it came.")
        return found
    attendance = GameAttendance(
        game_id=game.id,
        character_id=character.id,
        checked_in_by=actor.id,
        by_staff=by_staff,
        kind="absentee",
    )
    db.add(attendance)
    audit.record(
        db,
        actor,
        "play.absentee_marked",
        troupe_id=game.troupe_id,
        character_id=character.id,
        game=when(game),
    )
    db.flush()
    return attendance


def check_out(db: Session, actor: User, game: ScheduledGame, character: Character) -> None:
    """Take the character off the game's attendance, checked in or absentee. Its Play
    View is left as it is."""
    found = attendance_of(db, game, character)
    if found is None:
        return
    db.delete(found)
    audit.record(
        db,
        actor,
        "play.absentee_unmarked" if found.kind == "absentee" else "play.checked_out",
        troupe_id=game.troupe_id,
        character_id=character.id,
        game=when(game),
    )
    db.flush()


def month_start(today: date) -> date:
    return today.replace(day=1)


def earned(
    db: Session, character_ids: Iterable[uuid.UUID], since: date | None = None
) -> dict[uuid.UUID, int]:
    """XP each character has been awarded, since a day or in all, corrections included.
    Starting XP and what joining a troupe gave are left out, as they were not earned in
    play. A game XP chart's bands count it in all (horatio.game_xp)."""
    ids = list(character_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(XpEntry.character_id, func.sum(XpEntry.amount))
        .where(
            XpEntry.character_id.in_(ids),
            XpEntry.kind.in_(("award", "correction")),
            *([XpEntry.entered_on >= since] if since is not None else []),
            *(~XpEntry.reason.startswith(start, autoescape=True) for start in NOT_EARNED),
        )
        .group_by(XpEntry.character_id)
    )
    found = {character_id: int(total or 0) for character_id, total in rows}
    return {i: found.get(i, 0) for i in ids}


def earned_this_month(
    db: Session, character_ids: Iterable[uuid.UUID], today: date | None = None
) -> dict[uuid.UUID, int]:
    """XP each character has earned in the calendar month so far: what the book's
    monthly guidance counts."""
    return earned(db, character_ids, month_start(today or now().date()))
