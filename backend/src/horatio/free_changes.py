"""Free changes for new characters (issue #439): a while after its home troupe accepts
a character, its player can still drop or lower traits for their full XP back, as
during creation, instead of under the troupe's normal rules once in play.

A troupe chooses one of three under Customise › Rules:

- **None** (the default): the character is locked on acceptance, as it always was.
  Only dots bought since come back; the accepted sheet is for storytellers to lower.
- **By date**: free changes for `free_changes_days` days from acceptance.
- **By games played**: free changes until the character has attended
  `free_changes_games` of the troupe's games, counted from check-in
  (horatio.checkin): attended only, never an absentee game.

While a character's free changes are open, lowering a trait below its accepted
rating, or removing it, refunds what the troupe's costs say its dots cost, and goes
to the home troupe's staff as any change that waits on them does: a lowered trait is
held for review (declining puts it back and takes the XP back), and a merit or flaw
is asked of them (horatio.merit_requests), refunding a merit in full and buying off
a flaw for what it gave rather than twice that. Every change is still judged by the
checks, as always: traits chosen only during creation stay as they are, free dots
stay, and nothing may break a rule. The traits a troupe excludes (AIT's Efficient
Learner and Arcane) are never refunded so; they follow the normal rules.

Only a character's first acceptance opens free changes, and only if its home troupe
gave them when it was accepted: a character moving home brings no new ones, and a
troupe turning them on gives none to characters it accepted before. Changing between
dates and games, or the number, applies to the characters whose free changes are open,
worked out from their acceptance and attendance as they stand.

`window` works out whether they are open afresh whenever asked, so a change is never
refunded late. Their ending is noticed, recorded on the character
(`free_changes_ended_at`) and told to its player once: on check-in, for games; by the
delivery worker, for dates (`close_due_now`); and when the troupe changes its setting.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, notifications
from horatio.models import (
    Character,
    GameAttendance,
    ScheduledGame,
    SheetVersion,
    Troupe,
    User,
)

Kind = Literal["none", "date", "games"]

# What a troupe plays without free changes, in words: the book's way.
LOCKED_TEXT = "None: a character is locked once its home troupe accepts it"

# The note on a lowered trait held for the home troupe's review.
REVIEW_NOTE = "A free change: lowered while the character's free changes are open."


@dataclass(frozen=True)
class Window:
    """A character's open free changes: until when, or how many games are left, and
    the traits they never refund, as (category, name)."""

    kind: Literal["date", "games"]
    ends_at: datetime | None
    games_left: int | None
    excluded: frozenset[tuple[str, str]]


def now() -> datetime:
    return datetime.now(UTC)


def excluded(troupe: Troupe) -> frozenset[tuple[str, str]]:
    return frozenset((e["category"], e["name"]) for e in troupe.free_changes_excluded)


def games(n: int) -> str:
    return "1 game" if n == 1 else f"{n} games"


def setting_text(troupe: Troupe) -> str:
    """The troupe's free changes, in words: "For 30 days from acceptance"."""
    if troupe.free_changes == "date":
        days = troupe.free_changes_days
        return f"For {days} {'day' if days == 1 else 'days'} after the troupe accepts a character"
    if troupe.free_changes == "games":
        return (
            f"Until a character has attended {games(troupe.free_changes_games)}"
            " after the troupe accepts it"
        )
    return LOCKED_TEXT


def accepted_at(db: Session, character: Character, troupe: Troupe) -> datetime | None:
    """When `troupe` accepted the character, if it gets free changes from that: it is
    a PC whose home troupe it is, that was its first acceptance, and the troupe gave
    free changes then."""
    if (
        character.kind != "pc"
        or character.home_troupe_id != troupe.id
        or troupe.free_changes_since is None
    ):
        return None
    first = db.scalar(
        select(SheetVersion)
        .where(SheetVersion.character_id == character.id)
        .order_by(SheetVersion.approved_at, SheetVersion.number)
        .limit(1)
    )
    if first is None or first.troupe_id != troupe.id:
        return None
    if first.approved_at < troupe.free_changes_since:
        return None
    return first.approved_at


def attended(db: Session, character_id: uuid.UUID, troupe_id: uuid.UUID, since: datetime) -> int:
    """The troupe's games the character has attended, checked in, that were not over
    before `since`. An absentee game is not one attended."""
    return (
        db.scalar(
            select(func.count())
            .select_from(GameAttendance)
            .join(ScheduledGame, GameAttendance.game_id == ScheduledGame.id)
            .where(
                GameAttendance.character_id == character_id,
                GameAttendance.kind == "attended",
                ScheduledGame.troupe_id == troupe_id,
                ScheduledGame.ends_at > since,
            )
        )
        or 0
    )


def terms(
    db: Session, character: Character, troupe: Troupe, accepted: datetime, at: datetime
) -> Window | None:
    """The character's free changes under the troupe's setting as it stands, if they
    are still open at `at`."""
    if troupe.free_changes == "date":
        ends = accepted + timedelta(days=troupe.free_changes_days)
        return Window("date", ends, None, excluded(troupe)) if at < ends else None
    if troupe.free_changes == "games":
        left = troupe.free_changes_games - attended(db, character.id, troupe.id, accepted)
        return Window("games", None, left, excluded(troupe)) if left > 0 else None
    return None


def window(db: Session, character: Character, at: datetime | None = None) -> Window | None:
    """The character's free changes, if they are open: what is left of them, from its
    home troupe's setting. None if it has none, or they have ended."""
    if character.free_changes_ended_at is not None or character.home_troupe_id is None:
        return None
    troupe = db.get(Troupe, character.home_troupe_id)
    if troupe is None or troupe.archived_at is not None or troupe.free_changes == "none":
        return None
    accepted = accepted_at(db, character, troupe)
    if accepted is None:
        return None
    return terms(db, character, troupe, accepted, at or now())


def refunds(db: Session, character: Character, category: str, name: str) -> bool:
    """Whether lowering or removing this trait now is a free change: the character's
    free changes are open, and its troupe does not exclude the trait."""
    found = window(db, character)
    return found is not None and (category, name) not in found.excluded


def end(db: Session, character: Character, why: str) -> None:
    """Record that the character's free changes have ended, and tell its player."""
    character.free_changes_ended_at = now()
    audit.record(
        db,
        None,
        "character.free_changes_ended",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        why=why,
    )
    notifications.notify(
        db,
        [character.player_id],
        "character.free_changes_ended",
        f"{character.name}'s free changes have ended ({why}): the troupe's normal rules"
        " for lowering and removing traits apply now",
        f"/characters/{character.id}",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
    )
    db.flush()


def passed(troupe: Troupe) -> str:
    """Why free changes under the troupe's setting have run out, in words."""
    if troupe.free_changes == "date":
        days = troupe.free_changes_days
        return f"{days} {'day' if days == 1 else 'days'} after acceptance"
    return f"{games(troupe.free_changes_games)} attended"


def notice(db: Session, character: Character, at: datetime | None = None) -> bool:
    """End the character's free changes if they have run out, telling its player.
    Whether they ended now."""
    if character.free_changes_ended_at is not None or character.home_troupe_id is None:
        return False
    troupe = db.get(Troupe, character.home_troupe_id)
    if troupe is None or troupe.free_changes == "none":
        return False
    accepted = accepted_at(db, character, troupe)
    if accepted is None or terms(db, character, troupe, accepted, at or now()) is not None:
        return False
    end(db, character, passed(troupe))
    return True


def playing_here(db: Session, troupe: Troupe) -> list[Character]:
    """The troupe's active PCs whose free changes have not been seen to end."""
    return list(
        db.scalars(
            select(Character).where(
                Character.home_troupe_id == troupe.id,
                Character.kind == "pc",
                Character.status != "retired",
                Character.free_changes_ended_at.is_(None),
            )
        )
    )


def change_setting(
    db: Session,
    staff: User,
    troupe: Troupe,
    kind: Kind,
    days: int,
    games_played: int,
    excluding: Sequence[tuple[str, str]],
) -> None:
    """Set the troupe's free changes. Those that had run out under the old setting
    end first; then the new one applies to the characters whose free changes are
    still open, and ends those it leaves none. Turning them on gives them only to
    characters accepted from now on."""
    characters = playing_here(db, troupe)
    for character in characters:
        notice(db, character)
    still_open = [c for c in characters if window(db, c) is not None]
    if troupe.free_changes == "none" and kind != "none":
        # The database's clock, as acceptance is stamped by it.
        troupe.free_changes_since = db.scalar(select(func.now()))
    troupe.free_changes = kind
    troupe.free_changes_days = days
    troupe.free_changes_games = games_played
    troupe.free_changes_excluded = [
        {"category": category, "name": name} for category, name in dict.fromkeys(excluding)
    ]
    db.flush()
    why = "the troupe no longer gives them" if kind == "none" else "the troupe changed them"
    for character in still_open:
        if window(db, character) is None:
            end(db, character, why)
    audit.record(
        db,
        staff,
        "house.free_changes",
        troupe_id=troupe.id,
        setting=setting_text(troupe),
        excluded=", ".join(name for _, name in dict.fromkeys(excluding)) or "none",
    )


def close_due(db: Session, at: datetime | None = None) -> int:
    """End the free changes by date that have run out, in every troupe, telling each
    player. Games end on check-in instead. Returns how many ended."""
    at = at or now()
    first = (
        select(func.min(SheetVersion.approved_at))
        .where(SheetVersion.character_id == Character.id)
        .scalar_subquery()
    )
    due = list(
        db.scalars(
            select(Character)
            .join(Troupe, Character.home_troupe_id == Troupe.id)
            .where(
                Troupe.free_changes == "date",
                Troupe.archived_at.is_(None),
                Character.kind == "pc",
                Character.status != "retired",
                Character.free_changes_ended_at.is_(None),
                first >= Troupe.free_changes_since,
                first + func.make_interval(0, 0, 0, Troupe.free_changes_days) <= at,
            )
            .with_for_update(of=Character, skip_locked=True)
        )
    )
    return sum(notice(db, character, at) for character in due)


def close_due_now() -> int:
    """`close_due` in a session of its own, for the delivery worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        ended = close_due(db)
        db.commit()
        return ended
