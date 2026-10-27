"""Others at the game, on the Play View's Status tab (issue #254): the status of
another character, as one of its sect knows it, and learning its details with
Leadership (MET: VTM p. 310).

**Who is at the game.** A Play View game has no troupe of its own: its troupe is
the character's home troupe (horatio.play_status.troupe_of), and Horatio does not
know who came on the night. So the others are that troupe's characters now: its
PCs, home or visiting, not retired, and its NPCs that hold a title there, the
public figures of the court. Untitled NPCs stay the storytellers' own.

**What a character sees of them.** Only an Accepted character looks (one whose sect
has status), and of another sect it sees only the name and the sect. Of its own
sect, every Accepted member knows the others' status (p. 310): the status each
carries into its game (horatio.play_status.entries), held, abiding and negative,
with what is spent at that game marked so, as a rival weighs status that will
return (p. 311). Suppressed status is not carried, so it is not shown.

**Its details:** a held status's patron, where it was earned and the story.
Negative status is public (p. 312), so its details always show. A fleeting
status's show only once learned: "Learn about this status" spends one of the
character's Leadership uses for the game, one a dot, as a tap on its Leadership
counter (PlayEvent.learned), so Undo takes it back and the use returns. What a
character has learned it knows from then on, in later games too, unless the tap is
undone. Abiding and innate status comes from titles, social age and merits, and
has no patron to learn.

**The one who gave a negative status** removes it early (p. 313): the patron's
player sees Remove on it (horatio.sect_status.remove allows them).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from horatio import play, play_status, sect_status
from horatio.models import Character, CharacterTitle, PlayEvent, PlayGame, TroupeMembership, User
from horatio.sheets import conflict, unprocessable

# Leadership's uses a game (rules data: `uses_per_game`), as a tap names them.
LEADERSHIP = "trait:skills/Leadership/"


@dataclass(frozen=True)
class Other:
    """Another character at the game: its sect, and, of the viewer's own sect, its
    titles in the troupe and the sect's name for Accepted."""

    character: Character
    sect: str | None
    same_sect: bool
    accepted: str | None
    titles: tuple[str, ...]


@dataclass(frozen=True)
class Seen:
    """One status another character carries into its game, as the viewer sees it.
    `known`: its details show (negative status, or fleeting status learned);
    `learned_by` is the viewer's tap that learned it, for Undo."""

    key: str
    name: str
    type: str
    spent: bool
    learnable: bool
    known: bool
    learned_by: uuid.UUID | None = None
    held_id: uuid.UUID | None = None
    patron: sect_status.Patron | None = None
    place: str = ""
    story: str = ""
    ending: sect_status.Ending | None = None
    # The patron is the viewer's player's own character: they may remove it early.
    removable: bool = False


@dataclass(frozen=True)
class Viewer:
    character: Character
    found: sect_status.Standing


def viewing(db: Session, character: Character) -> Viewer:
    """The character looking, which must be Accepted by a sect with status."""
    found = sect_status.standing(db, character)
    if found.sect_data is None:
        raise conflict(
            f"{character.name} is not Accepted by a sect with status, so sees no one's status."
        )
    return Viewer(character, found)


def others(db: Session, viewer: Viewer) -> list[Other]:
    """The others at the viewer's game: its troupe's PCs, home or visiting, and its
    titled NPCs, by name."""
    troupe = play_status.troupe_of(db, viewer.character)
    if troupe is None:
        return []
    titled: dict[uuid.UUID, list[str]] = defaultdict(list)
    for who, name in db.execute(
        select(CharacterTitle.character_id, CharacterTitle.name)
        .where(CharacterTitle.troupe_id == troupe.id)
        .order_by(CharacterTitle.name)
    ):
        titled[who].append(name)
    members = db.scalars(
        select(Character)
        .join(TroupeMembership, TroupeMembership.character_id == Character.id)
        .where(
            TroupeMembership.troupe_id == troupe.id,
            TroupeMembership.left_at.is_(None),
            Character.status == "active",
            Character.id != viewer.character.id,
        )
        .order_by(Character.name, Character.id)
    )
    found: list[Other] = []
    for c in members:
        if c.kind == "npc" and not (c.npc_form == "sheeted" and titled.get(c.id)):
            continue
        sect = sect_status.sect_of(db, c)
        same = sect == viewer.found.sect
        found.append(
            Other(
                character=c,
                sect=sect,
                same_sect=same,
                accepted=viewer.found.accepted if same else None,
                titles=tuple(titled.get(c.id, [])) if same else (),
            )
        )
    return found


def other(db: Session, viewer: Viewer, other_id: uuid.UUID) -> Other:
    """One of the others at the viewer's game, or 404, as for a character the
    viewer cannot see."""
    found = next((o for o in others(db, viewer) if o.character.id == other_id), None)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character at this game.")
    return found


def learned(db: Session, viewer: Character, other_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """What the viewer has learned about the other's status, by its key: each tap
    that spent a Leadership use on it, in any game, not undone, by its device id."""
    undo = aliased(PlayEvent)
    found: dict[str, uuid.UUID] = {}
    for event in db.scalars(
        select(PlayEvent)
        .join(PlayGame, PlayEvent.game_id == PlayGame.id)
        .where(
            PlayGame.character_id == viewer.id,
            PlayEvent.kind == "change",
            PlayEvent.learned["character_id"].astext == str(other_id),
            ~select(undo.id).where(undo.undoes_id == PlayEvent.id).exists(),
        )
        .order_by(PlayGame.number, PlayEvent.happened_at, PlayEvent.id)
    ):
        # A tap that found no use left learned nothing.
        spent = event.before is not None and event.after is not None and event.after < event.before
        if spent and event.learned is not None:
            found[event.learned["key"]] = event.client_id
    return found


def seen(db: Session, user: User, viewer: Viewer, found: Other) -> list[Seen]:
    """The other's status as the viewer sees it; none of another sect's."""
    if not found.same_sect:
        return []
    character = found.character
    game = play.current_game(db, character)
    events = play.game_events(db, game) if game else []
    at = play_status.at_game(db, character, game)
    records = play_status.spends(events)
    known_keys = learned(db, viewer.character, character.id)
    patrons = {
        c.id: c
        for c in db.scalars(
            select(Character).where(
                Character.id.in_({h.patron.id for h in at.found.held if h.patron.id})
            )
        )
    }
    out: list[Seen] = []
    for e in play_status.entries(at, events):
        if e.suppressed:
            continue
        held = e.held
        patron: sect_status.Patron | None = held.patron if held else None
        place, story = (held.place, held.story) if held else ("", "")
        record = records.get(e.key)
        if held is None and record is not None and record.held_status is not None:
            # Spent for good at this game: the tap keeps its record.
            kept: dict[str, Any] = record.held_status
            patron = sect_status.Patron(
                uuid.UUID(kept["patron_id"]) if kept.get("patron_id") else None,
                kept.get("patron_name", ""),
                kept.get("patron_title", ""),
                kept.get("patron_text", ""),
            )
            place, story = kept.get("place", ""), kept.get("story", "")
        negative = e.type == "Negative"
        learnable = e.type == "Fleeting" and patron is not None
        known = (negative and held is not None) or (learnable and e.key in known_keys)
        giver = patrons.get(held.patron.id) if held and held.patron.id else None
        out.append(
            Seen(
                # A negative status by its record, as one can be held twice.
                key=play_status.held_key(held.id) if held else e.key,
                name=e.name,
                type=e.type,
                spent=e.spent,
                learnable=learnable,
                known=known,
                learned_by=known_keys.get(e.key) if learnable else None,
                held_id=held.id if held else play_status.held_id(e.key),
                patron=patron if known else None,
                place=place if known else "",
                story=story if known else "",
                ending=held.ending if known and held else None,
                removable=negative and giver is not None and sect_status.is_player(user, giver),
            )
        )
    return out


def leadership_left(db: Session, character: Character, game: PlayGame) -> tuple[str, int] | None:
    """The character's Leadership counter at `game`, and its uses left; None without
    Leadership."""
    limits = play.limits(db, character, game)
    found = next((e for e in limits.expendables if e.key.startswith(LEADERSHIP)), None)
    if found is None:
        return None
    state = play.replay(limits, play.game_events(db, game)).state
    return found.key, state["uses"].get(found.key, found.uses)


def learn(
    db: Session, user: User, viewer: Viewer, found: Other, key: str, tap_id: uuid.UUID
) -> None:
    """Spend one of the viewer's Leadership uses for its game to learn about one of
    the other's fleeting status: its patron, where it was earned, and the story
    (p. 310). `tap_id` is the device's id for it, so one sent twice spends once."""
    character = viewer.character
    sent = db.scalar(select(PlayEvent.id).where(PlayEvent.client_id == tap_id))
    if sent is not None:
        return
    entry = next((s for s in seen(db, user, viewer, found) if s.key == key), None)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such status.")
    if entry.type == "Negative":
        raise conflict("Negative status is public: its details show already (p. 312).")
    if not entry.learnable:
        raise unprocessable(
            f"{entry.name} is {entry.type.lower()} status: only held status has a patron, a"
            " place and a story to learn."
        )
    if entry.known:
        raise conflict(f"{character.name} knows about {found.character.name}'s {entry.name}.")
    game = play.start_game(db, character)
    left = leadership_left(db, character, game)
    if left is None:
        raise conflict(
            f"Learning about another's status takes Leadership: one use a game for each dot"
            f" (MET: VTM p. 310), and {character.name} has none."
        )
    tracker, uses = left
    if uses <= 0:
        raise conflict(f"{character.name}'s Leadership is used up for this game.")
    play.record(
        db,
        character,
        user,
        [
            play.Tap(
                id=tap_id,
                happened_at=datetime.now(UTC),
                kind="change",
                game_id=game.id,
                tracker=tracker,
                amount=-1,
                learned={
                    "character_id": str(found.character.id),
                    "name": found.character.name,
                    "key": key,
                    "status": entry.name,
                },
            )
        ],
    )


def remove(db: Session, user: User, viewer: Viewer, found: Other, held_id: uuid.UUID) -> None:
    """The one who gave the other a negative status removes it early (p. 313)."""
    entry = next((s for s in seen(db, user, viewer, found) if s.held_id == held_id), None)
    if entry is None or not entry.removable:
        raise conflict("Only the one who gave a negative status removes it early, or staff.")
    sect_status.remove(
        db, user, found.character, play_status.troupe_of(db, found.character), held_id
    )
