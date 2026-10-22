"""A character's influence history (#135): its own entries in the influence logs
of every troupe it has acted in, for its player and its home troupe's staff.

Only the character's own entries are ever here. An entry that merely mentions it
in its purpose is someone else's, and stays out. Entries outlive membership
(horatio.influence_log), so a troupe the character has left still shows what it
did there.

Blocks are shown only where the character placed them: a block on someone's
entry says who is protecting what, so others' blocks never show.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import influence, influence_log
from horatio.influence import InfluenceType
from horatio.models import (
    Character,
    InfluenceEntry,
    OwedAction,
    PlayEvent,
    PlayGame,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction, allows, troupe_role
from horatio.sheets import unprocessable

# The rules' "within the last 3 months" (MET: VtM core, p. 512).
DEFAULT_LOOKBACK_DAYS = 90


def lookback_days(db: Session, troupe_id: uuid.UUID) -> int:
    """How many days back a Gossip or Word on the Street in the troupe can find an
    action. #130 makes this a troupe setting; until it is, every troupe has the
    rules' 90 days."""
    del db, troupe_id
    return DEFAULT_LOOKBACK_DAYS


def findable(
    entry: InfluenceEntry, action: influence.InfluenceAction | None, now: datetime, lookback: int
) -> bool:
    """Whether a lookup now could still turn the entry up: within the lookback, to
    the minute, and not a conflict action, which lookups leave out (#130)."""
    within = entry.happened_at >= now - timedelta(days=lookback)
    return within and not (action is not None and action.conflict)


def blocks_placed(
    db: Session, character: Character, entries: Sequence[InfluenceEntry]
) -> dict[uuid.UUID, int]:
    """The discovery blocks the character put on each entry. The log keeps only a
    count on each entry, with no one's name on it, until #131 records who placed
    each block; until then none are shown, since some could be others'."""
    del db, character, entries
    return {}


def home_troupe(db: Session, character: Character) -> Troupe | None:
    """The troupe whose staff see the character's history: its home troupe, or for
    an NPC the troupe that keeps it."""
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    return db.get(Troupe, troupe_id) if troupe_id else None


def keeps_log(db: Session, user: User, troupe: Troupe | None) -> bool:
    """Whether `user` keeps the troupe's influence log."""
    if troupe is None or (troupe.archived_at is not None and not user.is_custodian):
        return False
    return allows(
        troupe_role(db, user, troupe),
        TroupeAction.MANAGE_INFLUENCE_LOG,
        is_custodian=user.is_custodian,
    )


def plays(user: User, character: Character) -> bool:
    return character.kind == "pc" and character.player_id == user.id


def can_see(db: Session, user: User, character: Character) -> bool:
    """A PC's player, and the storytellers and assistant storytellers of its home
    troupe. An NPC's history is for its troupe's staff only."""
    return plays(user, character) or keeps_log(db, user, home_troupe(db, character))


@dataclass
class Game:
    number: int
    started_at: datetime
    # Still going: the player can finish an entry that needs details until it ends.
    open: bool


def games(db: Session, entries: Sequence[InfluenceEntry]) -> dict[uuid.UUID, Game]:
    """The Play View game each game entry was spent in, by entry."""
    ids = {e.play_event_id for e in entries} - {None}
    if not ids:
        return {}
    rows = db.execute(
        select(PlayEvent.id, PlayGame.number, PlayGame.started_at, PlayGame.ended_at)
        .join(PlayGame, PlayGame.id == PlayEvent.game_id)
        .where(PlayEvent.id.in_(ids))
    )
    by_event = {r[0]: Game(r[1], r[2], r[3] is None) for r in rows}
    return {
        e.id: by_event[e.play_event_id]
        for e in entries
        if e.play_event_id is not None and e.play_event_id in by_event
    }


def can_finish(
    db: Session, user: User, character: Character, entry: InfluenceEntry, game: Game | None
) -> bool:
    """A game entry that needs details is the player's to finish until the game
    ends, as on the Play View (#133). The troupe's staff can finish it too; after
    the game, only they can, on the log page."""
    if not (entry.needs_details and entry.source == "game" and game is not None and game.open):
        return False
    return plays(user, character) or keeps_log(db, user, db.get(Troupe, entry.troupe_id))


def finish(
    db: Session,
    user: User,
    character: Character,
    entry: InfluenceEntry,
    *,
    specialization: str,
    action_key: str,
    purpose: str,
) -> InfluenceEntry:
    """Fill in a game entry's specialisation, action and purpose. The action must
    be one the character can reach, as on the downtime form."""
    game = games(db, [entry]).get(entry.id)
    if not can_finish(db, user, character, entry, game):
        raise unprocessable("Only an entry from a game still going can be finished here.")
    influence_type: InfluenceType = entry.type  # type: ignore[assignment]  # checked by the database
    standing = influence.standings(db, character)[influence_type]
    specialization = specialization.strip()
    action = next((a for a in standing.actions if a.key == action_key), None)
    type_name = influence.TYPE_NAMES[influence_type]
    if action is None:
        raise unprocessable(f"Choose one of the {type_name} actions.")
    if not standing.reachable(action, specialization):
        raise unprocessable(
            f"{action.label} needs {type_name} {action.level}, or "
            f"{(action.level or 1) - 1} with one of your {type_name} specialisations."
        )
    details = influence_log.Details(
        influence_type=influence_type,
        happened_at=entry.happened_at,
        character_id=entry.character_id,
        name=entry.name,
        specialization=entry.specialization,
        action_key=entry.action_key,
        purpose=entry.purpose,
        times=entry.times,
        blocks=entry.blocks,
        needs_details=entry.needs_details,
        cycle_id=entry.cycle_id,
    )
    influence_log.change_entry(
        db,
        user,
        entry,
        replace(
            details,
            specialization=specialization,
            action_key=action.key,
            purpose=purpose,
            needs_details=False,
        ),
    )
    return entry


def owed(db: Session, character: Character) -> dict[InfluenceType, int]:
    """Influence actions of each type spent between downtimes and still owed to the
    character's next cycle (#133)."""
    kinds: dict[str, InfluenceType] = {kind: t for t, kind in influence.ACTION_KINDS.items()}
    found: dict[InfluenceType, int] = dict.fromkeys(influence.TYPES, 0)
    rows = db.execute(
        select(OwedAction.action_kind, func.sum(OwedAction.amount))
        .where(
            OwedAction.character_id == character.id,
            OwedAction.action_kind.in_(kinds),
            OwedAction.participant_id.is_(None),
        )
        .group_by(OwedAction.action_kind)
    )
    for kind, amount in rows:
        found[kinds[kind]] += int(amount or 0)
    return found
