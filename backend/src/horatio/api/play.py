"""The Play View: a living sheet for a game, where blood, Willpower, health and
limited uses are spent tap by tap (horatio.play). The character's player and
the staff who can see the sheet use it alike; each tap says who made it."""

import uuid
from datetime import UTC, datetime
from typing import Literal, Self

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, play, sheets
from horatio.api.downtimes import staff_troupe
from horatio.api.roster import roster
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, PlayCounter, PlayEvent, PlayGame, User
from horatio.permissions import TroupeAction, visible_character

router = APIRouter(tags=["play"])

# Shown in the rest of the sheet; identity is at the top, health and Willpower
# are trackers, and specialties go in brackets after their trait.
NOT_LISTED = frozenset({"clan", "health_levels", "willpower_sources"})
ATTACK_SKILLS = ("Brawl", "Melee", "Firearms")


class Tracker(BaseModel):
    value: int
    most: int
    # Where a game starts it.
    start: int


class HealthLevel(BaseModel):
    name: str
    boxes: int


class Health(BaseModel):
    levels: list[HealthLevel]
    # Boxes marked, in the order they were: "normal" or "aggravated".
    marks: list[str]
    # A Stamina focus spares a character the Incapacitated penalty (p. 285).
    stamina_focus: bool


class Morality(BaseModel):
    name: str
    value: int
    rating: int


class ExpendableOut(BaseModel):
    key: str
    name: str
    detail: str
    # The sheet's category ("Backgrounds", "Merits"), or "Counters" for the player's own.
    group: str
    uses: int
    left: int
    counter_id: uuid.UUID | None


class LogEntryOut(BaseModel):
    # The id the device gave the tap.
    id: uuid.UUID
    kind: str
    tracker: str
    amount: int
    damage: str | None
    before: int | None
    after: int | None
    text: str
    note: str
    happened_at: datetime
    actor_name: str
    # Made by someone other than the character's player.
    by_staff: bool
    undone: bool
    # For an undo, the tap it undid.
    undoes: uuid.UUID | None


class GameOut(BaseModel):
    id: uuid.UUID
    number: int
    started_at: datetime
    ended_at: datetime | None
    ended_by: str | None
    taps: int
    notes: int


class PlayTrait(BaseModel):
    category: str
    category_name: str
    group: str
    name: str
    detail: str
    rating: int | None
    # Its specialties, from the categories that specialise it.
    specialties: list[str]


class Pool(BaseModel):
    name: str
    # How it is made up: "Physical + Brawl".
    detail: str
    pool: int


class PlayView(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str
    kind: str
    clan: str | None
    sect: str | None
    generation: int
    blood_per_turn: int
    blood: Tracker
    willpower: Tracker
    health: Health
    morality: Morality | None
    beast: Tracker
    expendables: list[ExpendableOut]
    # The game now; None before the character's first tap.
    game: GameOut | None
    # The game's log, newest first.
    log: list[LogEntryOut]
    traits: list[PlayTrait]
    pools: list[Pool]


class TapIn(BaseModel):
    """One tap, as the device made it."""

    # Made on the device, so a tap sent twice is recorded once.
    id: uuid.UUID
    happened_at: datetime
    # The game it was made in; by default the game now.
    game_id: uuid.UUID | None = None
    kind: Literal["change", "note", "undo"]
    tracker: str = Field(default="", max_length=200)
    amount: int = Field(default=0, ge=-50, le=50)
    damage: Literal["normal", "aggravated"] | None = None
    note: str = Field(default="", max_length=300)
    undoes: uuid.UUID | None = None

    @model_validator(mode="after")
    def complete(self) -> Self:
        if self.kind == "change":
            if not play.known_tracker(self.tracker) or self.amount == 0:
                raise ValueError("A change names what changed and by how much.")
            if self.tracker == "health" and self.damage is None:
                raise ValueError("Health changes say whether the damage is normal or aggravated.")
        if self.kind == "note" and not self.note.strip():
            raise ValueError("A note needs some words.")
        if self.kind == "undo" and self.undoes is None:
            raise ValueError("An undo names the tap it undoes.")
        return self


class Taps(BaseModel):
    taps: list[TapIn] = Field(max_length=500)


class ResetIn(BaseModel):
    # The game the person meant to end. If someone has already reset it, nothing
    # is reset twice.
    game_id: uuid.UUID | None = None


class CounterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    uses: int = Field(ge=1, le=99)


class TroupePlayEntry(BaseModel):
    character_id: uuid.UUID
    character_name: str
    player_name: str
    kind: str
    home: bool
    game_number: int | None
    taps: int
    last_tap_at: datetime | None
    blood: Tracker
    willpower: Tracker
    health_marked: int
    health_boxes: int


class TroupeReset(BaseModel):
    # Characters whose game was ended; those with no taps had nothing to reset.
    reset: int


def names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return {user_id: name for user_id, name in rows}


def game_out(db: Session, game: PlayGame, events: list[PlayEvent]) -> GameOut:
    return GameOut(
        id=game.id,
        number=game.number,
        started_at=game.started_at,
        ended_at=game.ended_at,
        ended_by=names(db, {game.ended_by_id}).get(game.ended_by_id) if game.ended_by_id else None,
        taps=sum(1 for e in events if e.kind == "change"),
        notes=sum(1 for e in events if e.note),
    )


def log_out(
    db: Session, character: Character, limits: play.Limits, events: list[PlayEvent]
) -> list[LogEntryOut]:
    """The taps newest first, each as it changed things when it was made."""
    by_id = {e.id: e for e in events}
    undone = {e.undoes_id for e in events if e.kind == "undo"}
    actors = names(db, {e.actor_id for e in events})

    def target(event: PlayEvent) -> PlayEvent | None:
        return by_id.get(event.undoes_id) if event.undoes_id else None

    return [
        LogEntryOut(
            id=event.client_id,
            kind=event.kind,
            tracker=event.tracker,
            amount=event.amount,
            damage=event.damage,
            before=event.before,
            after=event.after,
            text=play.describe(
                event, limits, by_id.get(event.undoes_id) if event.undoes_id else None
            ),
            note=event.note,
            happened_at=event.happened_at,
            actor_name=actors.get(event.actor_id, "Someone"),
            by_staff=not (character.kind == "pc" and event.actor_id == character.player_id),
            undone=event.id in undone,
            undoes=undid.client_id if (undid := target(event)) else None,
        )
        for event in reversed(play.in_order(events))
    ]


def sheet_traits(db: Session, character: Character) -> list[PlayTrait]:
    rule_set = sheets.rules_for(db, character).rule_set
    rows = sheets.sheet_rows(db, character)
    specialties: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        parent = rule_set.categories.get(row.category.key)
        if parent is not None and parent.specializes:
            key = (parent.specializes["category"], parent.specializes["name"])
            specialties.setdefault(key, []).append(row.trait.detail or row.definition.name)
    return [
        PlayTrait(
            category=row.category.key,
            category_name=row.category.name,
            group=rule_set.categories[row.category.key].group,
            name=row.definition.name,
            detail=row.trait.detail,
            rating=row.trait.rating,
            specialties=specialties.get((row.category.key, row.definition.name), []),
        )
        for row in rows
        if row.category.key in rule_set.categories
        and row.category.key not in NOT_LISTED
        and not rule_set.categories[row.category.key].specializes
    ]


def pools(traits: list[PlayTrait]) -> list[Pool]:
    """Initiative and the attack pools, worked out as the sheet stands (pp. 271, 285)."""

    def rating(category: str, name: str) -> int:
        return max(
            (t.rating or 0 for t in traits if (t.category, t.name) == (category, name)), default=0
        )

    physical, mental = rating("attributes", "Physical"), rating("attributes", "Mental")
    found = [
        Pool(
            name="Initiative",
            detail="Mental" if mental > physical else "Physical",
            pool=max(physical, mental),
        )
    ]
    attacks = sorted(
        ((physical + rating("skills", s), s) for s in ATTACK_SKILLS if rating("skills", s)),
        key=lambda a: -a[0],
    ) or [(physical, "Brawl")]
    for i, (pool, skill) in enumerate(attacks):
        found.append(
            Pool(
                name="Primary attack" if i == 0 else f"{skill} attack",
                detail=f"Physical + {skill}",
                pool=pool,
            )
        )
    found.append(
        Pool(name="Dodge", detail="Physical + Dodge", pool=physical + rating("skills", "Dodge"))
    )
    return found


def play_view(db: Session, character: Character) -> PlayView:
    limits = play.limits(db, character)
    game = play.current_game(db, character)
    events = play.game_events(db, game) if game else []
    state = play.replay(limits, events).state
    traits = sheet_traits(db, character)
    rows = sheets.sheet_rows(db, character)

    def one(category: str) -> str | None:
        return next((r.definition.name for r in rows if r.category.key == category), None)

    return PlayView(
        character_id=character.id,
        character_name=character.name,
        player_name=(
            db.get_one(User, character.player_id).display_name if character.kind == "pc" else "NPC"
        ),
        kind=character.kind,
        clan=one("clan"),
        sect=one("sect"),
        generation=limits.generation,
        blood_per_turn=limits.blood_per_turn,
        blood=Tracker(value=state["blood"], most=limits.blood, start=limits.starting_blood),
        willpower=Tracker(value=state["willpower"], most=limits.willpower, start=limits.willpower),
        health=Health(
            levels=[HealthLevel(name=n, boxes=b) for n, b in limits.health],
            marks=state["health"],
            stamina_focus=any(
                r.category.key == "focus_physicals" and r.definition.name == "Stamina" for r in rows
            ),
        ),
        morality=Morality(
            name=limits.morality_name, value=state["morality"], rating=limits.morality
        )
        if limits.morality_name
        else None,
        beast=Tracker(value=state["beast"], most=play.BEAST_TRAITS, start=0),
        expendables=[
            ExpendableOut(
                key=e.key,
                name=e.name,
                detail=e.detail,
                group=e.group,
                uses=e.uses,
                left=state["uses"].get(e.key, e.uses),
                counter_id=e.counter_id,
            )
            for e in limits.expendables
        ],
        game=game_out(db, game, events) if game else None,
        log=log_out(db, character, limits, events),
        traits=traits,
        pools=pools(traits),
    )


@router.get("/characters/{character_id}/play")
def read_play(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> PlayView:
    """The character's trackers and limited uses at the game now, and its log."""
    return play_view(db, visible_character(db, user, character_id))


@router.post("/characters/{character_id}/play/taps")
def record_taps(character_id: uuid.UUID, body: Taps, db: DbSession, user: CurrentUser) -> PlayView:
    """Record taps, perhaps made offline a while ago, in the order they happened."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    play.record(
        db,
        character,
        user,
        [
            play.Tap(
                id=t.id,
                happened_at=t.happened_at,
                kind=t.kind,
                game_id=t.game_id,
                tracker=t.tracker,
                amount=t.amount,
                damage=t.damage,
                note=t.note,
                undoes=t.undoes,
            )
            for t in body.taps
        ],
    )
    db.commit()
    return play_view(db, character)


@router.post("/characters/{character_id}/play/reset")
def reset_play(
    character_id: uuid.UUID, body: ResetIn, db: DbSession, user: CurrentUser
) -> PlayView:
    """Reset for the next game: the game ends, kept with its log, and every tracker
    goes back where the sheet starts it."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    game = play.current_game(db, character)
    if game is not None and (body.game_id is None or body.game_id == game.id):
        play.reset(db, character, user, troupe_id=None)
        db.commit()
    return play_view(db, character)


@router.get("/characters/{character_id}/play/games")
def list_games(character_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[GameOut]:
    """Games already over, newest first."""
    character = visible_character(db, user, character_id)
    games = db.scalars(
        select(PlayGame)
        .where(PlayGame.character_id == character.id, PlayGame.ended_at.is_not(None))
        .order_by(PlayGame.number.desc())
    )
    return [game_out(db, g, play.game_events(db, g)) for g in games]


class GameLog(BaseModel):
    game: GameOut
    log: list[LogEntryOut]


@router.get("/characters/{character_id}/play/games/{game_id}")
def read_game(
    character_id: uuid.UUID, game_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> GameLog:
    """One game's log, newest first, such as a past game's for the next downtime."""
    character = visible_character(db, user, character_id)
    game = db.get(PlayGame, game_id)
    if game is None or game.character_id != character.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such game.")
    events = play.game_events(db, game)
    return GameLog(
        game=game_out(db, game, events),
        log=log_out(db, character, play.limits(db, character), events),
    )


@router.post("/characters/{character_id}/play/counters")
def add_counter(
    character_id: uuid.UUID, body: CounterIn, db: DbSession, user: CurrentUser
) -> PlayView:
    """A counter of the player's own, such as "Fetish charges: 3"."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    db.add(
        PlayCounter(
            character_id=character.id, name=body.name.strip(), uses=body.uses, created_by_id=user.id
        )
    )
    audit.record(
        db, user, "play.counter_added", character_id=character.id, name=body.name, uses=body.uses
    )
    db.commit()
    return play_view(db, character)


@router.delete("/characters/{character_id}/play/counters/{counter_id}")
def remove_counter(
    character_id: uuid.UUID, counter_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> PlayView:
    """Take a counter off the Play View; old logs still name it."""
    character = sheets.lock_character(db, visible_character(db, user, character_id).id)
    counter = db.get(PlayCounter, counter_id)
    if counter is None or counter.character_id != character.id or counter.removed_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such counter.")
    counter.removed_at = datetime.now(UTC)
    counter.removed_by_id = user.id
    audit.record(db, user, "play.counter_removed", character_id=character.id, name=counter.name)
    db.commit()
    return play_view(db, character)


@router.get("/troupes/{troupe_id}/play")
def troupe_play(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[TroupePlayEntry]:
    """Every character in the troupe at the game now, in the roster's order."""
    staff_troupe(db, user, troupe_id, TroupeAction.VIEW_MEMBER_CHARACTERS)
    found: list[TroupePlayEntry] = []
    for entry in roster(troupe_id, db, user):
        character = db.get_one(Character, entry.character_id)
        limits = play.limits(db, character)
        game = play.current_game(db, character)
        events = play.game_events(db, game) if game else []
        state = play.replay(limits, events).state
        found.append(
            TroupePlayEntry(
                character_id=character.id,
                character_name=character.name,
                player_name=entry.player_name,
                kind=character.kind,
                home=entry.home,
                game_number=game.number if game else None,
                taps=sum(1 for e in events if e.kind == "change"),
                last_tap_at=max((e.happened_at for e in events), default=None),
                blood=Tracker(value=state["blood"], most=limits.blood, start=limits.starting_blood),
                willpower=Tracker(
                    value=state["willpower"], most=limits.willpower, start=limits.willpower
                ),
                health_marked=len(state["health"]),
                health_boxes=limits.health_boxes,
            )
        )
    return found


@router.post("/troupes/{troupe_id}/play/reset")
def reset_troupe(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> TroupeReset:
    """Reset every character in the troupe for the next game, after one."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RESET_GAMES)
    count = 0
    for entry in roster(troupe_id, db, user):
        character = sheets.lock_character(db, entry.character_id)
        count += play.reset(db, character, user, troupe_id=troupe.id)
    audit.record(db, user, "play.troupe_reset", troupe_id=troupe.id, count=count)
    db.commit()
    return TroupeReset(reset=count)
