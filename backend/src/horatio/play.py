"""The Play View: what a character spends at a game, tap by tap.

Every tap is an event with the time it happened on the device, which may reach
the server late: a phone with no signal keeps its taps and sends them when it
can. So the trackers are never stored as the truth. They are worked out by
replaying the game's taps in the order they happened, from where the sheet
starts each tracker, and the result is kept on the game only as a summary.
Replaying from the sheet also means a change to the sheet (a new dot of
Willpower) shows at once.

A reset ends the game, keeping it and its log, and starts the next one, in
which every tracker is back where the sheet starts it: blood full (or the
home troupe's starting amount, a house rule, or half if the character fed
short last downtime: horatio.feeding), Willpower at its rating, health
clear, Morality at the sheet's, no Beast traits, and each limited use back.
Derangement traits are the exception: nothing in the rules clears them between
games, so each game starts them where the last one left them. So are temporary
derangements, which the player adds and removes themselves.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from horatio import audit, influence_effects, play_influence, sheets
from horatio.models import (
    Character,
    PlayCounter,
    PlayDerangement,
    PlayEvent,
    PlayGame,
    Troupe,
    User,
)
from horatio.rules.feeding import clan_family

# Most blood, and blood a turn, by Generation dots (MET: VTM pp. 100-101).
BLOOD_BY_GENERATION = ((10, 1), (10, 1), (12, 2), (15, 3), (20, 4), (30, 5))
# The example sheet's Beast trait track; at five a dot of Morality is lost (p. 290).
BEAST_TRAITS = 5
# Derangement traits: one marked each time a derangement's trigger is resisted,
# all cleared by a severe response, which the third makes the next trigger bring
# (MET: VtM core, pp. 266-267); never more than 3 (p. 94). Malkavians always
# have 1 (p. 57).
DERANGEMENT_TRAITS = 3
# A temporary derangement's taps: +1 adds it, -1 removes it.
TEMPORARY = "derangement:"
HEALTH_LEVELS = ("Healthy", "Injured", "Incapacitated")
TRACKERS = ("blood", "willpower", "health", "morality", "beast", "derangements")
DAMAGE = ("normal", "aggravated")
# A device whose clock runs ahead cannot put a tap in the future.
CLOCK_SLACK = timedelta(minutes=1)


@dataclass(frozen=True)
class Expendable:
    """Something the character can use a set number of times a game: a trait with
    `uses_per_game` in the rules, or a counter of the player's own."""

    key: str
    name: str
    detail: str
    group: str
    uses: int
    counter_id: uuid.UUID | None = None
    # Influences: the type, and the actions spent at earlier games that no
    # downtime cycle has taken off yet, which `uses` is already lowered by.
    influence: str | None = None
    owed: int = 0

    @property
    def label(self) -> str:
        return f"{self.name}: {self.detail}" if self.detail else self.name


@dataclass(frozen=True)
class Temporary:
    """A temporary derangement the player added on the Play View."""

    key: str
    name: str
    source: str

    @property
    def label(self) -> str:
        return f"{self.name}, from {self.source}" if self.source else self.name


@dataclass(frozen=True)
class Limits:
    """What the sheet allows each tracker, and where a game starts it."""

    generation: int
    blood: int
    blood_per_turn: int
    starting_blood: int
    willpower: int
    health: tuple[tuple[str, int], ...]
    morality: int
    morality_name: str | None
    expendables: tuple[Expendable, ...] = ()
    # Blood starts at half, rounded up: the character fed short last downtime.
    half_blood: bool = False
    # Beast traits the game starts with: a diablerie added them (horatio.diablerie).
    beast_start: int = 0
    # Names for counters since removed, so old logs still read.
    removed: Mapping[str, str] = field(default_factory=dict[str, str])
    # Derangement traits where the game starts (where the last one ended), and
    # the fewest the character can have: 1 for a Malkavian.
    derangements: int = 0
    derangements_least: int = 0
    # The Derangement flaws on the sheet, by their detail ("Phobia: water").
    flaws: tuple[str, ...] = ()
    # Temporary derangements ever added, and those held as the game starts.
    temporary: tuple[Temporary, ...] = ()
    held: Mapping[str, int] = field(default_factory=dict[str, int])

    @property
    def health_boxes(self) -> int:
        return sum(boxes for _, boxes in self.health)

    def most(self, tracker: str) -> int | None:
        """The highest a tracker goes, or None for one the sheet does not have."""
        fixed = {
            "blood": self.blood,
            "willpower": self.willpower,
            "health": self.health_boxes,
            "morality": self.morality,
            "beast": BEAST_TRAITS,
            "derangements": DERANGEMENT_TRAITS,
        }
        if tracker in fixed:
            return fixed[tracker]
        if tracker.startswith(TEMPORARY):
            return 1 if any(t.key == tracker for t in self.temporary) else None
        return next((e.uses for e in self.expendables if e.key == tracker), None)

    def least(self, tracker: str) -> int:
        return self.derangements_least if tracker == "derangements" else 0

    def start(self) -> dict[str, Any]:
        return {
            "blood": self.starting_blood,
            "willpower": self.willpower,
            "health": [],
            "morality": self.morality,
            "beast": self.beast_start,
            "derangements": self.derangements,
            "held": {t.key: self.held.get(t.key, 0) for t in self.temporary},
            "uses": {e.key: e.uses for e in self.expendables},
        }

    def name(self, tracker: str) -> str:
        names = {
            "blood": "Blood",
            "willpower": "Willpower",
            "health": "Health",
            "morality": self.morality_name or "Morality",
            "beast": "Beast traits",
            "derangements": "Derangement traits",
        }
        if tracker in names:
            return names[tracker]
        found = next((e.label for e in self.expendables if e.key == tracker), None)
        found = found or next((t.label for t in self.temporary if t.key == tracker), None)
        if found:
            return found
        if tracker in self.removed:
            return self.removed[tracker]
        # A trait no longer on the sheet: "trait:backgrounds/Herd/" reads "Herd".
        parts = tracker.removeprefix("trait:").split("/")
        return ": ".join(p for p in parts[1:] if p) if len(parts) == 3 else tracker


def trait_key(category: str, name: str, detail: str) -> str:
    return f"trait:{category}/{name}/{detail}"


def counter_key(counter_id: uuid.UUID) -> str:
    return f"counter:{counter_id}"


def temporary_key(derangement_id: uuid.UUID) -> str:
    return f"{TEMPORARY}{derangement_id}"


def temporary_id(tracker: str) -> uuid.UUID | None:
    """The temporary derangement a tracker names, or None for another tracker."""
    if not tracker.startswith(TEMPORARY):
        return None
    try:
        return uuid.UUID(tracker.removeprefix(TEMPORARY))
    except ValueError:
        return None


def carries(tracker: str) -> bool:
    """A tracker kept from game to game, through Reset."""
    return tracker == "derangements" or tracker.startswith(TEMPORARY)


def known_tracker(tracker: str) -> bool:
    return (
        tracker in TRACKERS
        or tracker.startswith(("trait:", "counter:"))
        or temporary_id(tracker) is not None
    )


def uses_per_game(spec: Any, rating: int | None, ratings: Mapping[tuple[str, str], int]) -> int:
    """A trait's uses a game from its `uses_per_game`: a number, "rating" (one a
    dot), or {category, name} (one a dot of another trait, such as Occult)."""
    if isinstance(spec, bool):
        return 0
    if isinstance(spec, int):
        return spec
    if spec == "rating":
        return rating or 0
    if isinstance(spec, Mapping):
        return ratings.get((str(spec.get("category")), str(spec.get("name"))), 0)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    return 0


def carried(
    db: Session, character: Character, game: PlayGame | None, least: int
) -> tuple[int, dict[str, int]]:
    """Derangement traits, and the temporary derangements held, as `game` starts
    (or the next game, for None): where the game before it left them, which is
    every earlier game's taps on them, in order, as nothing clears them between
    games."""
    undo = aliased(PlayEvent)
    query = (
        select(PlayEvent.tracker, PlayEvent.amount)
        .join(PlayGame, PlayEvent.game_id == PlayGame.id)
        .where(
            PlayGame.character_id == character.id,
            PlayEvent.kind == "change",
            (PlayEvent.tracker == "derangements") | PlayEvent.tracker.startswith(TEMPORARY),
            ~select(undo.id).where(undo.undoes_id == PlayEvent.id).exists(),
        )
        .order_by(PlayGame.number, PlayEvent.happened_at, PlayEvent.id)
    )
    if game is not None:
        query = query.where(PlayGame.number < game.number)
    value = least
    held: dict[str, int] = {}
    for tracker, amount in db.execute(query):
        if tracker == "derangements":
            value = max(least, min(value + amount, DERANGEMENT_TRAITS))
        else:
            held[tracker] = max(0, min(held.get(tracker, 0) + amount, 1))
    return value, held


def derangement_flaws(rows: Sequence[sheets.SheetRow]) -> tuple[str, ...]:
    """The Derangement flaws on the sheet, each by its detail. Only these show the
    Derangement traits tracker of themselves; a clan weakness or Dementation's
    derangement is added on the Play View as a temporary one."""
    return tuple(
        r.trait.detail or r.definition.name
        for r in rows
        if r.category.key == "flaws" and r.definition.name == "Derangement"
    )


def malkavian(rows: Sequence[sheets.SheetRow]) -> bool:
    """Malkavians always have 1 Derangement trait (MET: VtM core, p. 57)."""
    return any(
        r.category.key == "clan" and clan_family(r.definition.name) == "Malkavian" for r in rows
    )


def temporary_derangements(db: Session, character: Character) -> tuple[Temporary, ...]:
    return tuple(
        Temporary(key=temporary_key(d.id), name=d.name, source=d.source)
        for d in db.scalars(
            select(PlayDerangement)
            .where(PlayDerangement.character_id == character.id)
            .order_by(PlayDerangement.created_at, PlayDerangement.name, PlayDerangement.id)
        )
    )


def home_troupe(db: Session, character: Character) -> Troupe | None:
    troupe_id = character.home_troupe_id or character.owner_troupe_id
    return db.get(Troupe, troupe_id) if troupe_id else None


def limits(db: Session, character: Character, game: PlayGame | None = None) -> Limits:
    """The sheet's limits for `game` (or a game not yet started). Influence is one
    pool a month, shared with downtimes (MET: VtM core, p. 510), so its counters
    start lower by what earlier games spent that no cycle has taken off yet."""
    rows = sheets.sheet_rows(db, character)
    rule_set = sheets.rules_for(db, character).rule_set
    ratings: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row.category.key, row.definition.name)
        ratings[key] = max(ratings.get(key, 0), row.trait.rating or 0)

    generation = ratings.get(("backgrounds", "Generation"), 0)
    blood, per_turn = BLOOD_BY_GENERATION[min(max(generation, 0), 5)]
    troupe = home_troupe(db, character)
    house = troupe.starting_blood if troupe is not None else None
    path = next((r for r in rows if r.category.key == "paths"), None)

    expendables: list[Expendable] = []
    owed: dict[str, int] | None = None
    for row in rows:
        spec = rule_set.trait_properties(row.category.key, row.definition.name).get("uses_per_game")
        uses = uses_per_game(spec, row.trait.rating, ratings) if spec is not None else 0
        if uses > 0:
            key = trait_key(row.category.key, row.definition.name, row.trait.detail)
            influence_type = play_influence.type_of_tracker(key)
            if influence_type is not None and owed is None:
                owed = {str(k): v for k, v in play_influence.owed(db, character, game).items()}
            spent = min(uses, owed.get(influence_type, 0)) if influence_type and owed else 0
            expendables.append(
                Expendable(
                    key=key,
                    name=row.definition.name,
                    detail=row.trait.detail,
                    group=row.category.name,
                    uses=uses - spent,
                    influence=influence_type,
                    owed=spent,
                )
            )
    counters = list(
        db.scalars(
            select(PlayCounter)
            .where(PlayCounter.character_id == character.id)
            .order_by(PlayCounter.created_at, PlayCounter.id)
        )
    )
    expendables += [
        Expendable(
            key=counter_key(c.id),
            name=c.name,
            detail="",
            group="Counters",
            uses=c.uses,
            counter_id=c.id,
        )
        for c in counters
        if c.removed_at is None
    ]
    # Attacks and Boosts holding on the character move its Influences counters.
    expendables = influence_effects.play_uses(db, character, expendables)
    # A game not started yet starts at half if the last downtime said so.
    half = game.half_blood if game is not None else character.half_blood_next_game
    beast = game.beast_start if game is not None else character.beast_next_game
    usual = blood if house is None else min(house, blood)
    least = 1 if malkavian(rows) else 0
    traits, held = carried(db, character, game, least)
    return Limits(
        generation=generation,
        blood=blood,
        blood_per_turn=per_turn,
        starting_blood=-(-blood // 2) if half else usual,
        half_blood=half,
        beast_start=min(beast, BEAST_TRAITS),
        willpower=ratings.get(("willpower_sources", "Willpower"), 0),
        health=tuple((level, ratings.get(("health_levels", level), 0)) for level in HEALTH_LEVELS),
        morality=(path.trait.rating or 0) if path else 0,
        morality_name=path.definition.name if path else None,
        expendables=tuple(expendables),
        removed={counter_key(c.id): c.name for c in counters if c.removed_at is not None},
        derangements=traits,
        derangements_least=least,
        flaws=derangement_flaws(rows),
        temporary=temporary_derangements(db, character),
        held=held,
    )


def apply(state: dict[str, Any], limits: Limits, event: PlayEvent) -> tuple[int, int] | None:
    """Apply one change to `state`, and say what the tracker was before and after
    (for health, boxes marked). None for a note, or a tracker the sheet lacks."""
    if event.kind != "change":
        return None
    most = limits.most(event.tracker)
    if most is None:
        return None
    if event.tracker == "health":
        marks: list[str] = state["health"]
        before = len(marks)
        damage = event.damage or "normal"
        if event.amount > 0:
            marks.extend([damage] * max(0, min(event.amount, most - len(marks))))
        else:
            for _ in range(-event.amount):
                if damage not in marks:
                    break
                del marks[len(marks) - 1 - marks[::-1].index(damage)]
        return before, len(marks)
    if event.tracker.startswith(TEMPORARY):
        before = state["held"].get(event.tracker, 0)
        state["held"][event.tracker] = max(0, min(before + event.amount, most))
        return before, state["held"][event.tracker]
    if event.tracker in TRACKERS:
        before = state[event.tracker]
        state[event.tracker] = max(limits.least(event.tracker), min(before + event.amount, most))
        return before, state[event.tracker]
    before = state["uses"].get(event.tracker, most)
    state["uses"][event.tracker] = max(0, min(before + event.amount, most))
    return before, state["uses"][event.tracker]


def in_order(events: Iterable[PlayEvent]) -> list[PlayEvent]:
    """The order taps happened in on their devices; ties in the order they arrived."""
    return sorted(events, key=lambda e: (e.happened_at, e.id))


@dataclass
class Replay:
    state: dict[str, Any]
    # Each change's tracker before and after, by event id.
    changes: dict[uuid.UUID, tuple[int, int] | None]
    undone: set[uuid.UUID]


def replay(limits: Limits, events: Sequence[PlayEvent]) -> Replay:
    """The game's trackers after its taps, skipping those undone. An undone tap
    keeps what it changed when it was made, for the log."""
    undone = {e.undoes_id for e in events if e.kind == "undo" and e.undoes_id is not None}
    state = limits.start()
    changes: dict[uuid.UUID, tuple[int, int] | None] = {}
    for event in in_order(events):
        if event.kind == "undo" or event.id in undone:
            continue
        changes[event.id] = apply(state, limits, event)
    return Replay(state, changes, undone)


def game_events(db: Session, game: PlayGame) -> list[PlayEvent]:
    return list(db.scalars(select(PlayEvent).where(PlayEvent.game_id == game.id)))


def refresh(db: Session, game: PlayGame, limits: Limits) -> Replay:
    """Replay a game after taps arrive, keeping each change and the state."""
    events = game_events(db, game)
    result = replay(limits, events)
    for event in events:
        if event.id in result.changes:
            event.before, event.after = result.changes[event.id] or (None, None)
    game.state = result.state
    return result


def describe(event: PlayEvent, limits: Limits, target: PlayEvent | None = None) -> str:
    """The tap as the log reads it: "Blood 7 → 6"."""
    if event.kind == "note":
        return "Note"
    if event.kind == "undo":
        return f"Undid: {describe(target, limits)}" if target is not None else "Undid a tap"
    name = limits.name(event.tracker)
    if event.tracker.startswith(TEMPORARY):
        return f"Temporary derangement {'added' if event.amount > 0 else 'removed'}: {name}"
    if event.tracker == "health":
        verb = "took" if event.amount > 0 else "healed"
        text = f"Health: {verb} {abs(event.amount)} {event.damage or 'normal'}"
        if event.before is not None and event.after is not None:
            text += f" ({event.before} → {event.after} marked)"
        return text
    if event.before is not None and event.after is not None:
        return f"{name} {event.before} → {event.after}"
    sign = "+" if event.amount > 0 else "−"
    return f"{name} {sign}{abs(event.amount)} (not on the sheet now)"


# --- Games -------------------------------------------------------------------


def current_game(db: Session, character: Character) -> PlayGame | None:
    return db.scalar(
        select(PlayGame).where(PlayGame.character_id == character.id, PlayGame.ended_at.is_(None))
    )


def start_game(db: Session, character: Character) -> PlayGame:
    """The character's game now, starting their first if they have none."""
    found = current_game(db, character)
    if found is not None:
        return found
    last = db.scalar(select(func.max(PlayGame.number)).where(PlayGame.character_id == character.id))
    game = PlayGame(
        character_id=character.id,
        number=(last or 0) + 1,
        state={},
        half_blood=character.half_blood_next_game,
        beast_start=character.beast_next_game,
    )
    character.half_blood_next_game = False
    character.beast_next_game = 0
    db.add(game)
    db.flush()
    return game


def add_beast(db: Session, character: Character, amount: int) -> None:
    """Add Beast traits to the character's next game (a diablerie does, p. 306): to the
    game it is in if that has had no taps yet, as it is not really started, else to the
    one the next reset starts."""
    game = current_game(db, character)
    if game is not None and not game_events(db, game):
        game.beast_start += amount
    else:
        character.beast_next_game += amount
    db.flush()


def reset(db: Session, character: Character, actor: User, *, troupe_id: uuid.UUID | None) -> bool:
    """End the character's game, keeping it, and start the next. A game with no
    taps is already as a new one would be, so it is left as it is. Says whether
    there was a game to end. The caller holds the character's lock."""
    game = current_game(db, character)
    if game is None or not game_events(db, game):
        return False
    refresh(db, game, limits(db, character, game))
    game.ended_at = datetime.now(UTC)
    game.ended_by_id = actor.id
    db.flush()
    start_game(db, character)
    audit.record(
        db, actor, "play.reset", troupe_id=troupe_id, character_id=character.id, game=game.number
    )
    return True


@dataclass(frozen=True)
class Tap:
    """A tap as a device sends it (see horatio.api.play.TapIn)."""

    id: uuid.UUID
    happened_at: datetime
    kind: str
    game_id: uuid.UUID | None = None
    tracker: str = ""
    amount: int = 0
    damage: str | None = None
    note: str = ""
    undoes: uuid.UUID | None = None
    # An influence spend's details; None when the player skipped them.
    influence: play_influence.Details | None = None
    # Adding a temporary derangement: its name and where it came from.
    derangement: tuple[str, str] | None = None


def name_temporary(db: Session, character: Character, actor: User, tap: Tap) -> None:
    """Keep the name of a temporary derangement a tap adds for the first time. A
    tap on one that was never added, or on another character's, is refused."""
    derangement_id = temporary_id(tap.tracker)
    if derangement_id is None:
        return
    found = db.get(PlayDerangement, derangement_id)
    if found is not None:
        if found.character_id != character.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "That derangement is another character's."
            )
        return
    if tap.amount < 0 or tap.derangement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such derangement.")
    name, source = tap.derangement
    db.add(
        PlayDerangement(
            id=derangement_id,
            character_id=character.id,
            name=name.strip(),
            source=source.strip(),
            created_by_id=actor.id,
        )
    )
    db.flush()


def undone_already(db: Session, event: PlayEvent) -> bool:
    return db.scalar(select(PlayEvent.id).where(PlayEvent.undoes_id == event.id)) is not None


def record(db: Session, character: Character, actor: User, taps: Sequence[Tap]) -> None:
    """Record taps from a device, in the games they were made in, and replay
    those games. A tap already recorded (sent again after a lost reply) is
    skipped, as is an undo of something already undone. The caller holds the
    character's lock. Influence spent, and undone, is logged and owed as it
    arrives (horatio.play_influence)."""
    ids = [t.id for t in taps] + [t.undoes for t in taps if t.undoes is not None]
    existing = {
        e.client_id: (e, character_id)
        for e, character_id in db.execute(
            select(PlayEvent, PlayGame.character_id)
            .join(PlayGame, PlayEvent.game_id == PlayGame.id)
            .where(PlayEvent.client_id.in_(ids))
        )
    }
    if any(character_id != character.id for _, character_id in existing.values()):
        raise HTTPException(status.HTTP_409_CONFLICT, "That tap belongs to another character.")
    games = {
        g.id: g for g in db.scalars(select(PlayGame).where(PlayGame.character_id == character.id))
    }
    touched: dict[uuid.UUID, PlayGame] = {}
    # The earliest game whose Derangement traits these taps change.
    carried: int | None = None
    latest = datetime.now(UTC) + CLOCK_SLACK
    for tap in taps:
        if tap.id in existing:
            continue
        happened_at = (
            tap.happened_at if tap.happened_at.tzinfo else tap.happened_at.replace(tzinfo=UTC)
        )
        target: PlayEvent | None = None
        if tap.kind == "undo":
            found = existing.get(tap.undoes) if tap.undoes else None
            target = found[0] if found else None
            if target is None or target.kind == "undo" or undone_already(db, target):
                continue
            game = games[target.game_id]
        elif tap.game_id is not None:
            if tap.game_id not in games:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "No such game.")
            game = games[tap.game_id]
        else:
            game = start_game(db, character)
            games[game.id] = game
        if tap.kind == "change":
            name_temporary(db, character, actor, tap)
        event = PlayEvent(
            game_id=game.id,
            client_id=tap.id,
            actor_id=actor.id,
            happened_at=min(happened_at, latest),
            kind=tap.kind,
            tracker=tap.tracker if tap.kind == "change" else "",
            amount=tap.amount if tap.kind == "change" else 0,
            damage=tap.damage if tap.tracker == "health" and tap.kind == "change" else None,
            note=tap.note.strip(),
            undoes_id=target.id if target is not None else None,
        )
        db.add(event)
        db.flush()
        if target is not None:
            play_influence.cancel(db, actor, target)
        elif event.kind == "change":
            play_influence.spend(db, character, actor, event, tap.influence)
        existing[tap.id] = (event, character.id)
        touched[game.id] = game
        if carries((target or event).tracker):
            carried = game.number if carried is None else min(carried, game.number)
    for game in touched.values():
        refresh(db, game, limits(db, character, game))
    # Derangement traits carry from game to game, so a late tap in a game already
    # over moves where each game after it started them.
    if carried is not None:
        for game in games.values():
            if game.number > carried and game.id not in touched:
                refresh(db, game, limits(db, character, game))
    db.flush()
