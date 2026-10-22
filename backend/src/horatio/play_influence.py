"""Influence spent at a game, on the Play View (#133).

Spending a use of Influences: The Elite or The Underworld is a tap like any
other (horatio.play), with the details of the action sent along with it: the
specialisation, the named action (horatio.influence) and a one-line purpose. A
tap of several uses is the same action taken that many times. Each spend:

- **is logged** in the influence log of the character's home troupe (an NPC's,
  the troupe that keeps it), sourced to the game, linked to the tap and dated
  when the tap was made. Spent without its details, it is marked as needing
  them, for the player to add before the game ends or for staff to finish;
- **is owed** to the next downtime cycle (MET: VtM core, p. 510: each dot is one
  action a month, at games and in downtimes alike). It becomes an owed action of
  that influence's action kind, which the next cycle to open takes off the
  character's allowance. Until then, each game's counter starts that much lower.

Undoing the tap takes the entry off the log and cancels what is owed, giving
the action back to a cycle that has already taken it.

A tap from a device that was offline arrives late and cannot be refused without
losing every tap after it, so details the server cannot take as they are (an
action the character cannot reach, a specialisation it does not hold) are kept
as far as they go, and the entry is marked as needing details.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from horatio import audit, influence, influence_log, preferences
from horatio.influence import InfluenceType
from horatio.models import (
    AllowanceAdjustment,
    AuditEvent,
    Character,
    InfluenceEntry,
    OwedAction,
    PlayEvent,
    PlayGame,
    Troupe,
    User,
)
from horatio.sheets import unprocessable

# Changes to an entry made in the troupe's log, rather than at the game.
STAFF_CHANGES = ("influence.changed", "influence.merged")


@dataclass(frozen=True)
class Details:
    """What an influence spend was, as the player gives it on the Play View."""

    action: str
    specialization: str = ""
    purpose: str = ""


def type_of_tracker(tracker: str) -> InfluenceType | None:
    """The influence type a Play View tracker spends, such as
    "trait:backgrounds/Influences: The Elite/", or None for any other."""
    parts = tracker.removeprefix("trait:").split("/") if tracker.startswith("trait:") else []
    if len(parts) != 3 or parts[0] != "backgrounds":
        return None
    return next((t for t, name in influence.TRAITS.items() if name == parts[1]), None)


def log_troupe(db: Session, character: Character) -> Troupe | None:
    """The troupe whose log a character's game spends go in: its home troupe, or
    the troupe that keeps an NPC. None for a character in no troupe."""
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    if troupe_id is None:
        return None
    troupe = db.get(Troupe, troupe_id)
    if troupe is None or not influence_log.in_troupe(db, troupe.id, character):
        return None
    return troupe


def owes(character: Character) -> bool:
    """Whether the character's game spends come off its downtimes: a player
    character with a home troupe. NPCs take no part in downtimes."""
    return character.kind == "pc" and character.home_troupe_id is not None


def owed(db: Session, character: Character, game: PlayGame | None) -> dict[InfluenceType, int]:
    """Influence spent at earlier games that no cycle has taken off yet, by type:
    the actions this module owes, linked to their taps. Those spent in `game` are
    left out, as its own taps count them. Other owed influence actions (an
    Attack's lost actions, a Boost's extra ones) reach the counters through the
    rating, so they are not counted again here."""
    if not owes(character):
        return {}
    query = select(OwedAction.action_kind, func.sum(OwedAction.amount)).where(
        OwedAction.character_id == character.id,
        OwedAction.troupe_id == character.home_troupe_id,
        OwedAction.participant_id.is_(None),
        OwedAction.action_kind.in_(influence.ACTION_KINDS.values()),
        OwedAction.play_event_id.is_not(None),
    )
    if game is not None:
        query = query.where(
            OwedAction.play_event_id.not_in(
                select(PlayEvent.id).where(PlayEvent.game_id == game.id)
            )
        )
    found: dict[InfluenceType, int] = {}
    for kind, amount in db.execute(query.group_by(OwedAction.action_kind)):
        influence_type = influence.type_of(kind)
        if influence_type is not None and amount:
            found[influence_type] = int(amount)
    return found


def standings(db: Session, character: Character) -> list[influence.Standing]:
    """What the character can do with each type it has, when its spends are
    logged: the Play View asks for details only then."""
    if log_troupe(db, character) is None:
        return []
    return [s for s in influence.standings(db, character).values() if s.rating > 0]


def fitted(
    standing: influence.Standing, details: Details | None
) -> tuple[str, str | None, str, bool]:
    """The specialisation, action key and purpose to log, and whether the entry
    still needs details: none were given, or they do not fit the character."""
    if details is None:
        return "", None, "", True
    specialization = details.specialization.strip()
    fits = not specialization or specialization in standing.held
    if not fits:
        specialization = ""
    action = influence.named_in(standing.actions, {"action": details.action})
    if action is None or not standing.reachable(action, specialization):
        fits = False
    return specialization, action.key if action else None, details.purpose.strip(), not fits


def game_day(db: Session, character: Character, game_id: uuid.UUID) -> str:
    """The game as an owed action's reason names it: "Spent at the 11 Jul game",
    on the day its first tap was made, in the player's time zone."""
    first = db.scalar(select(func.min(PlayEvent.happened_at)).where(PlayEvent.game_id == game_id))
    player = db.get(User, character.player_id) if character.player_id else None
    zone = (preferences.read(player).time_zone if player else None) or "UTC"
    day = (first or datetime.now(ZoneInfo(zone))).astimezone(ZoneInfo(zone))
    return f"Spent at the {day.day} {day:%b} game"


def spend(
    db: Session, character: Character, actor: User, event: PlayEvent, details: Details | None
) -> None:
    """Log an influence spend and owe it to the next cycle. `event` is the tap,
    already recorded."""
    influence_type = type_of_tracker(event.tracker)
    troupe = log_troupe(db, character)
    if influence_type is None or event.kind != "change" or event.amount >= 0 or troupe is None:
        return
    times = -event.amount
    standing = influence.standings(db, character)[influence_type]
    specialization, action_key, purpose, needs_details = fitted(standing, details)
    influence_log.add_entry(
        db,
        actor,
        troupe,
        influence_log.Details(
            influence_type=influence_type,
            happened_at=event.happened_at,
            character_id=character.id,
            specialization=specialization,
            action_key=action_key,
            purpose=purpose,
            times=times,
            needs_details=needs_details,
        ),
        source="game",
        play_event_id=event.id,
    )
    if owes(character):
        assert character.home_troupe_id is not None
        db.add(
            OwedAction(
                character_id=character.id,
                troupe_id=character.home_troupe_id,
                action_kind=influence.ACTION_KINDS[influence_type],
                amount=times,
                reason=game_day(db, character, event.game_id),
                owed_by=actor.id,
                play_event_id=event.id,
            )
        )
    db.flush()


def cancel(db: Session, actor: User, event: PlayEvent) -> None:
    """Undo a spend: its entry comes off the log, and what it owed is cancelled,
    given back to a cycle that has already taken it off."""
    for debt in db.scalars(select(OwedAction).where(OwedAction.play_event_id == event.id)):
        for adjustment in db.scalars(
            select(AllowanceAdjustment).where(AllowanceAdjustment.owed_action_id == debt.id)
        ):
            db.delete(adjustment)
        db.delete(debt)
    entry = db.scalar(select(InfluenceEntry).where(InfluenceEntry.play_event_id == event.id))
    if entry is not None:
        influence_log.delete_entry(db, actor, entry)
    db.flush()


# --- reading and changing them from the game's log --------------------------------------


def entries(db: Session, event_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, InfluenceEntry]:
    """The log entries spends made, by their taps' ids."""
    ids = list(event_ids)
    if not ids:
        return {}
    found = db.scalars(select(InfluenceEntry).where(InfluenceEntry.play_event_id.in_(ids)))
    return {e.play_event_id: e for e in found if e.play_event_id is not None}


def changed_by_staff(db: Session, found: Iterable[InfluenceEntry]) -> set[uuid.UUID]:
    """The entries staff have changed in the troupe's log since they were spent."""
    ids = [str(e.id) for e in found]
    if not ids:
        return set()
    rows = db.scalars(
        select(AuditEvent.data["entry_id"].astext).where(
            AuditEvent.action.in_(STAFF_CHANGES), AuditEvent.data["entry_id"].astext.in_(ids)
        )
    )
    return {uuid.UUID(r) for r in rows if r}


def text(entry: InfluenceEntry, action: str | None) -> str:
    """The spend as the game's log reads it:
    "Elite: 5: No Party Crashers (News Media), To secure the Weather"."""
    name = influence.TYPE_NAMES[entry.type]  # type: ignore[index]  # checked by the database
    if entry.times > 1:
        name += f" ×{entry.times}"
    if action is None:
        return f"{name}: details to come"
    said = action + (f" ({entry.specialization})" if entry.specialization else "")
    return f"{name}: {said}, {entry.purpose}" if entry.purpose else f"{name}: {said}"


def give_details(
    db: Session, actor: User, character: Character, entry: InfluenceEntry, details: Details
) -> None:
    """Add or change a spend's details from the game's log. Unlike a spend sent
    from the device, these are checked and refused when they do not fit."""
    standing = influence.standings(db, character)[entry.type]  # type: ignore[index]
    type_name = influence.TYPE_NAMES[standing.influence_type]
    specialization = details.specialization.strip()
    if specialization and specialization not in standing.held:
        raise unprocessable(f"Choose one of your own {type_name} specialisations.")
    action = influence.named_in(standing.actions, {"action": details.action})
    if action is None:
        raise unprocessable(f"Choose one of the {type_name} actions.")
    if not standing.reachable(action, specialization):
        raise unprocessable(
            f"{action.label} needs {type_name} {action.level}, or "
            f"{(action.level or 1) - 1} with one of your {type_name} specialisations."
        )
    entry.specialization = specialization
    entry.action_key = action.key
    entry.purpose = details.purpose.strip()
    entry.needs_details = False
    db.flush()
    audit.record(
        db,
        actor,
        "influence.detailed_at_game",
        troupe_id=entry.troupe_id,
        **influence_log.describe(influence_log.troupe_rules(db, entry.troupe_id), entry),
    )
