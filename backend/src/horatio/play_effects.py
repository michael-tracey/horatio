"""A power's effect that lasts until undone (issue #822), not until the game ends.

Most of what the Play View switches on lasts the game at most, and Reset turns it
all off (horatio.play). Some powers change a character until the change is undone:
Heart of Darkness takes the heart out until another use puts it back (MET: VtM core
p. 161), and Vicissitude reshapes a face or a body (pp. 168-169). Their switches are
`kept` (horatio.reference.Switch), and each use is a `PlayEffect`: a row on the
character, not on a game, so it holds through Reset until it is turned off.

A kept switch is still worked by the Play View's taps, so it works offline as the
rest does: a "power:<key>" +1 tap starts an effect (the tap's id is the effect's, so
a tap sent twice makes one), and -1 ends it. Using it again while it is on replaces
it, as a character carries one application at a time (core p. 168). Undoing the tap
that started an effect ends it and brings back the one it replaced; undoing the tap
that ended one brings it back. What is on is then read from the rows, not from the
taps: an effect staff ended, or one another character's power made (issue #823),
counts as the rows say.

A switch that is `normal_form_only` changes the character's normal form only: while
a form is on, what it does is paused, and it comes back when the form ends.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.models import Character, PlayEffect, PlayEvent, PlayGame, User

# Why an effect ended, as the log reads it.
ENDED = {
    "off": "turned off",
    "replaced": "used again",
    "undone": "undone",
    "staff": "ended by staff",
}


@dataclass(frozen=True)
class Kept:
    """An effect on a character as a game stands: on, and since when."""

    id: uuid.UUID
    key: str
    since: datetime
    source_character_id: uuid.UUID
    options: tuple[str, ...] = ()


def held(db: Session, character: Character, game: PlayGame | None = None) -> tuple[Kept, ...]:
    """The effects on the character as `game` stands, in the order they began: those
    on now for the game now (or a game not started), and for a game over, those on
    as it ended."""
    query = select(PlayEffect).where(PlayEffect.character_id == character.id)
    if game is None or game.ended_at is None:
        query = query.where(PlayEffect.state == "active")
    else:
        query = query.where(
            PlayEffect.state.in_(("active", "ended")),
            PlayEffect.ended_how != "undone",
            PlayEffect.started_at <= game.ended_at,
            or_(PlayEffect.ended_at.is_(None), PlayEffect.ended_at > game.ended_at),
        )
    return tuple(
        Kept(
            id=e.id,
            key=e.key,
            since=e.started_at,
            source_character_id=e.source_character_id,
            options=tuple(e.options),
        )
        for e in db.scalars(query.order_by(PlayEffect.started_at, PlayEffect.id))
    )


def active(db: Session, character_id: uuid.UUID, key: str) -> PlayEffect | None:
    return db.scalar(
        select(PlayEffect).where(
            PlayEffect.character_id == character_id,
            PlayEffect.key == key,
            PlayEffect.state == "active",
        )
    )


def end(
    db: Session,
    effect: PlayEffect,
    actor: User,
    how: str,
    name: str,
    *,
    event: PlayEvent | None = None,
) -> None:
    """End an effect: turned off, used again, undone, or ended by staff."""
    effect.state = "ended"
    effect.ended_at = datetime.now(UTC)
    effect.ended_by_id = actor.id
    effect.ended_how = how
    effect.ended_event_id = event.id if event is not None else None
    db.flush()
    if how != "replaced":
        audit.record(
            db,
            actor,
            "play.effect_ended",
            character_id=effect.character_id,
            power=name,
            how=ENDED.get(how, how),
        )


def start(
    db: Session, character: Character, actor: User, event: PlayEvent, key: str, name: str
) -> PlayEffect:
    """Start an effect on the character from its own tap, replacing the one on: a
    character carries one application of a power at a time (core p. 168)."""
    last = active(db, character.id, key)
    if last is not None:
        end(db, last, actor, "replaced", name, event=event)
    effect = PlayEffect(
        character_id=character.id,
        source_character_id=character.id,
        key=key,
        client_id=event.client_id,
        event_id=event.id,
        started_at=event.happened_at,
        started_by_id=actor.id,
        replaced_id=last.id if last is not None else None,
    )
    db.add(effect)
    db.flush()
    audit.record(
        db,
        actor,
        "play.effect_started",
        character_id=character.id,
        power=name,
        replaced=last is not None,
    )
    return effect


def on_tap(
    db: Session, character: Character, actor: User, event: PlayEvent, key: str, name: str
) -> None:
    """A tap on a kept switch: +1 starts an effect (or replaces the one on), -1 ends
    the one on, if any."""
    if event.amount > 0:
        start(db, character, actor, event, key, name)
        return
    found = active(db, character.id, key)
    if found is not None:
        end(db, found, actor, "off", name, event=event)


def bring_back(db: Session, effect: PlayEffect) -> None:
    """Make an ended effect active again, unless another of its power is on now."""
    if effect.state != "ended" or active(db, effect.character_id, effect.key) is not None:
        return
    effect.state = "active"
    effect.ended_at = None
    effect.ended_by_id = None
    effect.ended_how = ""
    effect.ended_event_id = None
    db.flush()


def on_undo(db: Session, actor: User, target: PlayEvent, name: str) -> None:
    """Undoing a tap on a kept switch: the effect it started ends, and the one it
    replaced comes back; the effect it ended comes back."""
    started = db.scalar(select(PlayEffect).where(PlayEffect.event_id == target.id))
    if started is not None and started.state == "active":
        end(db, started, actor, "undone", name)
        if started.replaced_id is not None:
            replaced = db.get(PlayEffect, started.replaced_id)
            if replaced is not None and replaced.ended_how == "replaced":
                bring_back(db, replaced)
        return
    ended = db.scalar(select(PlayEffect).where(PlayEffect.ended_event_id == target.id))
    if ended is not None and ended.ended_how in ("off", "replaced"):
        bring_back(db, ended)


def on_character(db: Session, character: Character) -> Sequence[PlayEffect]:
    """The effects on the character now, in the order they began."""
    return list(
        db.scalars(
            select(PlayEffect)
            .where(PlayEffect.character_id == character.id, PlayEffect.state == "active")
            .order_by(PlayEffect.started_at, PlayEffect.id)
        )
    )


def one(db: Session, character: Character, effect_id: uuid.UUID) -> PlayEffect:
    found = db.get(PlayEffect, effect_id)
    if found is None or found.character_id != character.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such effect.")
    return found
