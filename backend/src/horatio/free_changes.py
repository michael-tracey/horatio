"""Free changes for new characters (issue #439): a while after its home troupe accepts
a character, its player can still drop or lower traits for their full XP back, as
during creation, instead of under the troupe's normal rules once in play.

A troupe chooses one of three in the Settings at the top of Characters › Approvals:

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
stay, and nothing may break a rule. The traits a troupe excludes (such as Efficient
Learner and Arcane) are never refunded so; they follow the normal rules.

Only a character's first acceptance opens free changes, and only if its home troupe
gave them when it was accepted: a character moving home brings no new ones, and a
troupe turning them on gives none to characters it accepted before. Leaving the home
troupe ends them (horatio.reconciliation.end_membership), so being accepted again,
by the same troupe or another, does not bring them back. Changing between
dates and games, or the number, applies to the characters whose free changes are open,
worked out from their acceptance and attendance as they stand.

`window` works out whether they are open afresh whenever asked, so a change is never
refunded late. Their ending is noticed, recorded on the character
(`free_changes_ended_at`) and told to its player once: on check-in, for games; by the
delivery worker, for dates (`close_due_now`); and when the troupe changes its setting.
"""

import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
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
from horatio.rules.store import read_troupe_rules

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


def acceptances(
    db: Session, characters: Sequence[Character], troupes: Mapping[uuid.UUID, Troupe]
) -> dict[uuid.UUID, datetime]:
    """When each character's home troupe, one of `troupes`, accepted it, if it gets
    free changes from that: it is a PC whose home troupe it is, that was its first
    acceptance, and the troupe gave free changes then. In one query for all of them."""
    asked = [
        (c, troupes[c.home_troupe_id])
        for c in characters
        if c.kind == "pc" and c.home_troupe_id is not None and c.home_troupe_id in troupes
    ]
    asked = [(c, t) for c, t in asked if t.free_changes_since is not None]
    if not asked:
        return {}
    first = {
        character_id: (troupe_id, approved_at)
        for character_id, troupe_id, approved_at in db.execute(
            select(SheetVersion.character_id, SheetVersion.troupe_id, SheetVersion.approved_at)
            .where(SheetVersion.character_id.in_([c.id for c, _ in asked]))
            .order_by(SheetVersion.character_id, SheetVersion.approved_at, SheetVersion.number)
            .ext(distinct_on(SheetVersion.character_id))
        )
    }
    found: dict[uuid.UUID, datetime] = {}
    for character, troupe in asked:
        troupe_id, approved_at = first.get(character.id, (None, None))
        since = troupe.free_changes_since
        if troupe_id == troupe.id and approved_at and since and approved_at >= since:
            found[character.id] = approved_at
    return found


def attendance(
    db: Session, since: Mapping[uuid.UUID, tuple[uuid.UUID, datetime]]
) -> dict[uuid.UUID, int]:
    """For each character, `{character: (troupe, since)}`, the troupe's games it has
    attended, checked in, that were not over before `since`. An absentee game is not
    one attended. In one query for all of them."""
    if not since:
        return {}
    counts: dict[uuid.UUID, int] = defaultdict(int)
    for character_id, troupe_id, ends_at in db.execute(
        select(GameAttendance.character_id, ScheduledGame.troupe_id, ScheduledGame.ends_at)
        .join(ScheduledGame, GameAttendance.game_id == ScheduledGame.id)
        .where(
            GameAttendance.character_id.in_(list(since)),
            GameAttendance.kind == "attended",
            ScheduledGame.troupe_id.in_({troupe_id for troupe_id, _ in since.values()}),
        )
    ):
        troupe, after = since[character_id]
        if troupe_id == troupe and ends_at > after:
            counts[character_id] += 1
    return counts


def terms(troupe: Troupe, accepted: datetime, at: datetime, attended: int) -> Window | None:
    """Free changes under the troupe's setting as it stands, for a character it
    accepted at `accepted` that has since attended `attended` of its games, if they
    are still open at `at`."""
    if troupe.free_changes == "date":
        ends = accepted + timedelta(days=troupe.free_changes_days)
        return Window("date", ends, None, excluded(troupe)) if at < ends else None
    if troupe.free_changes == "games":
        left = troupe.free_changes_games - attended
        return Window("games", None, left, excluded(troupe)) if left > 0 else None
    return None


def windows(
    db: Session, characters: Sequence[Character], at: datetime | None = None
) -> dict[uuid.UUID, Window]:
    """The characters' free changes that are open, as `window` gives each, in a few
    queries for all of them (for "Next for this character", horatio.next_steps). A
    character whose free changes are not open is left out."""
    asked = [c for c in characters if c.free_changes_ended_at is None and c.home_troupe_id]
    homes = (db.get(Troupe, troupe_id) for troupe_id in {c.home_troupe_id for c in asked})
    troupes = {
        t.id: t
        for t in homes
        if t is not None and t.archived_at is None and t.free_changes != "none"
    }
    accepted = acceptances(db, asked, troupes)
    home = {c.id: troupes[c.home_troupe_id] for c in asked if c.id in accepted and c.home_troupe_id}
    played = attendance(
        db,
        {
            character_id: (troupe.id, accepted[character_id])
            for character_id, troupe in home.items()
            if troupe.free_changes == "games"
        },
    )
    found: dict[uuid.UUID, Window] = {}
    for character_id, troupe in home.items():
        open_now = terms(troupe, accepted[character_id], at or now(), played.get(character_id, 0))
        if open_now is not None:
            found[character_id] = open_now
    return found


def window(db: Session, character: Character, at: datetime | None = None) -> Window | None:
    """The character's free changes, if they are open: what is left of them, from its
    home troupe's setting. None if it has none, or they have ended."""
    return windows(db, [character], at).get(character.id)


def refunds(db: Session, character: Character, category: str, name: str) -> bool:
    """Whether lowering or removing this trait now is a free change: the character's
    free changes are open, and its troupe does not exclude the trait."""
    found = window(db, character)
    return found is not None and (category, name) not in found.excluded


def end(db: Session, character: Character, why: str, *, tell: bool = True) -> None:
    """Record that the character's free changes have ended, and tell its player
    unless they ended them themselves (`tell`)."""
    character.free_changes_ended_at = now()
    audit.record(
        db,
        None,
        "character.free_changes_ended",
        troupe_id=character.home_troupe_id,
        character_id=character.id,
        why=why,
    )
    if tell:
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
    accepted = acceptances(db, [character], {troupe.id: troupe}).get(character.id)
    if accepted is None:
        return False
    played = (
        attendance(db, {character.id: (troupe.id, accepted)}).get(character.id, 0)
        if troupe.free_changes == "games"
        else 0
    )
    if terms(troupe, accepted, at or now(), played) is not None:
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


def check_excluded(db: Session, troupe: Troupe, excluding: Sequence[tuple[str, str]]) -> None:
    """Refuse a trait to leave out of free changes that none of the troupe's splats has."""
    known = {
        key
        for splat in troupe.allowed_splats
        for key in read_troupe_rules(db, splat, troupe.id).rule_set.traits
    }
    for category, name in excluding:
        if (category, name) not in known:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"There is no trait {name} to exclude."
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
