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

Forms and powers in use (issue #200) are taps too: "power:<key>" +1 switches one
on and -1 off (horatio.reference.Switch). Only one form is on at a time (MET: VtM
core, p. 114), so turning one on turns the last off. A form's extra wound levels
follow the sheet's own in each category, and when it ends they go with the damage
marked in them, as Vol. 2 has it for levels that are lost (p. 55); damage in the
sheet's own levels stays, since injuries carry between forms (core p. 114). Blood
over the usual most goes when Blood of Potency ends (core p. 188). Each game
starts with everything off.

A Stock NPC (issue #215) has only two trackers, from its stat block
(horatio.rules.stock): its kind's resource in Blood's place (Rage for a werewolf)
and its health levels, as one track. It has no Willpower, Morality or Beast
traits (MET: VTM p. 490), so taps on those change nothing.

A splat's Blood and panels follow its properties (horatio.rules.splats.Splat).
A ghoul's Blood is part vitae and part human (core p. 297): "blood" is its vitae,
at most 5, spent 1 a turn; the rest of its 10 is human Blood, which no tap can
spend. Vitae refills only by drinking: a "drank" tap adds vitae, turning human
Blood to vitae when the pool is full, and is when the ghoul last drank. So vitae
is not refilled by a reset, but carries from game to game as Derangement traits
do, and each game starts the rest of the pool as human Blood, as spent vitae
comes back as human Blood at 1 a day. A splat without the Beast has no Beast
traits to tap, and a ghoul's clan weakness is roleplay only, so a Malkavian
domitor's ghoul has no Derangement trait from it.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from horatio import (
    audit,
    influence_effects,
    npcs,
    play_influence,
    reference,
    retainers,
    sect_status,
    sheets,
)
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
from horatio.rules.splats import SPLATS, Panels, Vitae, both

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
# A form's or power's taps: +1 switches it on, -1 off.
SWITCH = "power:"
# A Retainer's health and Blood: "retainer:Bocephus/health" (horatio.retainers).
RETAINER = "retainer:"
HEALTH_LEVELS = ("Healthy", "Injured", "Incapacitated")
TRACKERS = ("blood", "willpower", "health", "morality", "beast", "derangements")
# Drinking vitae, for a ghoul: +n adds that much vitae to "blood" (core p. 297).
DRANK = "drank"
DAMAGE = ("normal", "aggravated")
# A Stock NPC's trackers: its kind's resource, kept as "blood", and its health
# levels, one track of them (MET: VTM p. 490).
STOCK_TRACKERS = frozenset({"blood", "health"})
STOCK_HEALTH = "Health levels"
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
class RetainerTrack:
    """One Retainer's health levels and (a ghoul's) Blood at a game (core p. 105):
    taps on "<key>/health" and "<key>/blood", each counting down from full."""

    key: str
    name: str
    health: int
    blood: int

    def trackers(self) -> dict[str, int]:
        found = {f"{self.key}/health": self.health}
        if self.blood:
            found[f"{self.key}/blood"] = self.blood
        return found


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
    # The forms and powers the sheet has that can be switched on.
    switches: tuple[reference.Switch, ...] = ()
    # Each Retainer's health and Blood.
    retainers: tuple[RetainerTrack, ...] = ()
    # What the "blood" tracker is: a Stock NPC's kind's resource, such as Rage.
    blood_name: str = "Blood"
    # The fixed trackers the character has; a Stock NPC has no Willpower and so on.
    trackers: frozenset[str] = frozenset(TRACKERS)
    # The Play View's panels for this character (horatio.rules.splats.Panels).
    panels: Panels = Panels()
    # A ghoul's Blood, part vitae ("blood") and part human; None for a vampire's.
    vitae: Vitae | None = None

    def retainer_trackers(self) -> dict[str, int]:
        return {k: most for r in self.retainers for k, most in r.trackers().items()}

    @property
    def health_boxes(self) -> int:
        return sum(boxes for _, boxes in self.health)

    def switch(self, key: str) -> reference.Switch | None:
        return next((s for s in self.switches if s.key == key), None)

    def on(self, keys: Sequence[str]) -> list[reference.Switch]:
        """The switches on, in the order they were switched on."""
        return [s for key in keys if (s := self.switch(key)) is not None]

    def boxes(self, on: Sequence[str] = ()) -> list[str | None]:
        """Every wound box, in the order damage fills them: in each category the
        sheet's own (None), then those of the forms on, by their keys."""
        found: list[str | None] = []
        for level, count in self.health:
            found += [None] * count
            for switch in self.on(on):
                found += [switch.key] * sum(h.boxes for h in switch.health if h.level == level)
        return found

    def blood_most(self, on: Sequence[str] = ()) -> int:
        """The most Blood, half again with Blood of Potency on (rounded up)."""
        return self.blood + sum(-(-self.blood // 2) for s in self.on(on) if s.blood_half)

    def blood_per_turn_now(self, on: Sequence[str] = ()) -> int:
        return self.blood_per_turn + sum(s.blood_per_turn for s in self.on(on))

    def most(self, tracker: str, on: Sequence[str] = ()) -> int | None:
        """The highest a tracker goes with the switches `on`, or None for one the
        sheet does not have."""
        if tracker.startswith(SWITCH):
            return 1 if self.switch(tracker.removeprefix(SWITCH)) else None
        fixed = {
            "blood": self.blood_most(on),
            "willpower": self.willpower,
            "health": len(self.boxes(on)),
            "morality": self.morality,
            "beast": BEAST_TRAITS,
            "derangements": DERANGEMENT_TRAITS,
        }
        if tracker == DRANK:
            return self.vitae.most if self.vitae else None
        if tracker in fixed:
            return fixed[tracker] if tracker in self.trackers else None
        if tracker.startswith(TEMPORARY):
            return 1 if any(t.key == tracker for t in self.temporary) else None
        if tracker.startswith(RETAINER):
            return self.retainer_trackers().get(tracker)
        return next((e.uses for e in self.expendables if e.key == tracker), None)

    def least(self, tracker: str) -> int:
        return self.derangements_least if tracker == "derangements" else 0

    def human_start(self) -> int:
        """A ghoul's human Blood as a game starts: the rest of its pool."""
        return self.vitae.pool - self.starting_blood if self.vitae else 0

    def start(self) -> dict[str, Any]:
        return {
            "blood": self.starting_blood,
            "human": self.human_start(),
            "willpower": self.willpower,
            "health": [],
            "morality": self.morality,
            "beast": self.beast_start,
            "derangements": self.derangements,
            "held": {t.key: self.held.get(t.key, 0) for t in self.temporary},
            "uses": {e.key: e.uses for e in self.expendables} | self.retainer_trackers(),
            # Forms and powers switched on: none, as a game starts.
            "on": [],
        }

    def name(self, tracker: str) -> str:
        names = {
            "blood": self.blood_name,
            DRANK: "Drank vitae",
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
        if tracker.startswith(SWITCH):
            switch = self.switch(tracker.removeprefix(SWITCH))
            return switch.name if switch else tracker.removeprefix(SWITCH)
        if tracker.startswith(RETAINER):
            key, _, what = tracker.rpartition("/")
            found = next((r.name for r in self.retainers if r.key == key), None)
            name = found if found is not None else key.removeprefix(RETAINER)
            return f"{name or 'Retainer'}: {'Blood' if what == 'blood' else 'health'}"
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


def carries(tracker: str, vitae: bool = False) -> bool:
    """A tracker kept from game to game, through Reset: Derangement traits, and a
    ghoul's vitae, which only drinking refills."""
    return (
        tracker == "derangements"
        or tracker.startswith(TEMPORARY)
        or (vitae and tracker in ("blood", DRANK))
    )


def trackers_for(panels: Panels) -> frozenset[str]:
    """The fixed trackers a character with these panels has: none for Morality or
    Beast traits where the kind has no such panel."""
    gone = {"morality": not panels.morality, "beast": not panels.beast}
    return frozenset(t for t in TRACKERS if not gone.get(t))


def known_tracker(tracker: str) -> bool:
    return (
        tracker in TRACKERS
        or tracker == DRANK
        or tracker.startswith(("trait:", "counter:", RETAINER))
        or (tracker.startswith(SWITCH) and len(tracker) > len(SWITCH))
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
    value = least
    held: dict[str, int] = {}
    for tracker, amount in earlier_taps(db, character, game, ("derangements",), TEMPORARY):
        if tracker == "derangements":
            value = max(least, min(value + amount, DERANGEMENT_TRAITS))
        else:
            held[tracker] = max(0, min(held.get(tracker, 0) + amount, 1))
    return value, held


def earlier_taps(
    db: Session,
    character: Character,
    game: PlayGame | None,
    trackers: Sequence[str],
    prefix: str | None = None,
) -> list[tuple[str, int]]:
    """Every change tap not undone on `trackers` (or on those starting `prefix`) in
    the character's games before `game` (or before the next game, for None), in
    the order they happened."""
    undo = aliased(PlayEvent)
    which = PlayEvent.tracker.in_(trackers)
    if prefix is not None:
        which = which | PlayEvent.tracker.startswith(prefix)
    query = (
        select(PlayEvent.tracker, PlayEvent.amount)
        .join(PlayGame, PlayEvent.game_id == PlayGame.id)
        .where(
            PlayGame.character_id == character.id,
            PlayEvent.kind == "change",
            which,
            ~select(undo.id).where(undo.undoes_id == PlayEvent.id).exists(),
        )
        .order_by(PlayGame.number, PlayEvent.happened_at, PlayEvent.id)
    )
    if game is not None:
        query = query.where(PlayGame.number < game.number)
    return [(tracker, amount) for tracker, amount in db.execute(query)]


def carried_vitae(db: Session, character: Character, game: PlayGame | None, vitae: Vitae) -> int:
    """A ghoul's vitae as `game` starts: full before its first game, then where the
    games before left it, as only drinking refills it."""
    value = vitae.most
    for _, amount in earlier_taps(db, character, game, ("blood", DRANK)):
        value = max(0, min(value + amount, vitae.most))
    return value


def last_drank(db: Session, character: Character) -> datetime | None:
    """When the character last drank vitae, by its taps: a drink not undone."""
    undo = aliased(PlayEvent)
    return db.scalar(
        select(func.max(PlayEvent.happened_at))
        .join(PlayGame, PlayEvent.game_id == PlayGame.id)
        .where(
            PlayGame.character_id == character.id,
            PlayEvent.kind == "change",
            PlayEvent.tracker == DRANK,
            PlayEvent.amount > 0,
            ~select(undo.id).where(undo.undoes_id == PlayEvent.id).exists(),
        )
    )


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
    if character.npc_form == "stock":
        return stock_limits(db, character)
    kind = npcs.kind_of(character) if character.npc_form == "sheeted" else None
    rows = sheets.sheet_rows(db, character)
    rule_set = sheets.rules_for(db, character).rule_set
    splat = SPLATS[character.splat]
    ratings: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row.category.key, row.definition.name)
        ratings[key] = max(ratings.get(key, 0), row.trait.rating or 0)

    generation = ratings.get(("backgrounds", "Generation"), 0)
    blood, per_turn = BLOOD_BY_GENERATION[min(max(generation, 0), 5)]
    troupe = home_troupe(db, character)
    house = troupe.starting_blood if troupe is not None else None
    # What its kind and splat leave off: a ghoul has no Beast, Humanity,
    # Generation or Feed, whatever its kind (horatio.rules.splats.Splat.panels).
    panels = both(kind.panels, splat.panels) if kind is not None else splat.panels
    blood_name = "Blood"
    if kind is not None and not kind.vampiric:
        # Its kind's resource stands in for Blood (MET: VTM ch. 12), from the kind
        # rather than from Generation, which it has none of; and it has no Morality
        # or Beast traits.
        resource = kind.resource
        generation, blood, per_turn, house = 0, resource.size, resource.per_turn, None
        blood_name = resource.name
    # A ghoul's spendable Blood is its vitae, which carries from game to game.
    vitae = splat.vitae
    if vitae is not None:
        blood, per_turn, house, blood_name = vitae.most, vitae.per_turn, None, "Vitae"
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
    half, beast = half and panels.feed, beast if panels.beast else 0
    usual = blood if house is None else min(house, blood)
    starting = -(-blood // 2) if half else usual
    if vitae is not None:
        half, starting = False, carried_vitae(db, character, game, vitae)
    # A Malkavian's Derangement trait is its clan weakness, which a ghoul plays
    # for roleplay only.
    least = 1 if splat.weakness and malkavian(rows) else 0
    traits, held = carried(db, character, game, least)
    return Limits(
        generation=generation,
        blood=blood,
        blood_per_turn=per_turn,
        starting_blood=starting,
        half_blood=half,
        beast_start=min(beast, BEAST_TRAITS),
        willpower=ratings.get(("willpower_sources", "Willpower"), 0),
        health=tuple((level, ratings.get(("health_levels", level), 0)) for level in HEALTH_LEVELS),
        morality=(path.trait.rating or 0) if path and panels.morality else 0,
        morality_name=path.definition.name if path and panels.morality else None,
        expendables=tuple(expendables),
        removed={counter_key(c.id): c.name for c in counters if c.removed_at is not None},
        derangements=traits,
        derangements_least=least,
        flaws=derangement_flaws(rows),
        temporary=temporary_derangements(db, character),
        held=held,
        switches=tuple(reference.switches(rows, rule_set)),
        blood_name=blood_name,
        trackers=trackers_for(panels),
        panels=panels,
        retainers=tuple(
            RetainerTrack(
                key=retainers.tracker(r),
                name=r.name,
                health=r.dots,
                blood=retainers.GHOUL_BLOOD if r.row and r.row.ghoul else 0,
            )
            for r in retainers.read(db, character)
        ),
        vitae=vitae,
    )


def stock_limits(db: Session, character: Character) -> Limits:
    """A Stock NPC's trackers, from its stat block (MET: VTM p. 490): its kind's
    resource, full at each game and spent as the kind says, and its health levels
    (twice its rating for a werewolf or a Blood Brother)."""
    _, block = npcs.stat_block(db, character)
    resource = block.resource
    return Limits(
        generation=0,
        blood=resource.size,
        blood_per_turn=resource.per_turn,
        starting_blood=resource.size,
        willpower=0,
        health=((STOCK_HEALTH, block.health),),
        morality=0,
        morality_name=None,
        blood_name=resource.name,
        trackers=STOCK_TRACKERS,
    )


def switch_off(
    state: dict[str, Any], limits: Limits, key: str, said: list[str] | None = None
) -> None:
    """Switch a form or power off: the damage in its wound levels goes with them,
    and Blood over the usual most."""
    on: list[str] = state["on"]
    if key not in on:
        return
    marks: list[str] = state["health"]
    lost = [i for i, owner in enumerate(limits.boxes(on)) if owner == key and i < len(marks)]
    for i in reversed(lost):
        del marks[i]
    on.remove(key)
    state["blood"] = min(state["blood"], limits.blood_most(on))
    if said is not None and lost:
        said.append(f"{len(lost)} damage in its levels gone")


def switch(
    state: dict[str, Any], limits: Limits, key: str, amount: int, said: list[str] | None = None
) -> tuple[int, int]:
    """Switch a form or power on (amount > 0) or off. A form turns off any other
    form it does not combine with (core p. 114; Vol. 2 p. 82)."""
    on: list[str] = state.setdefault("on", [])
    before = int(key in on)
    found = limits.switch(key)
    if amount > 0 and not before and found is not None:
        if found.form:
            for other in limits.on(list(on)):
                if other.form and other.key not in found.combines and key not in other.combines:
                    if said is not None:
                        said.append(f"out of {other.name}")
                    switch_off(state, limits, other.key, said)
        on.append(key)
    elif amount < 0 and before:
        switch_off(state, limits, key, said)
    return before, int(key in on)


def apply(
    state: dict[str, Any], limits: Limits, event: PlayEvent, said: list[str] | None = None
) -> tuple[int, int] | None:
    """Apply one change to `state`, and say what the tracker was before and after
    (for health, boxes marked). None for a note, or a tracker the sheet lacks.
    What switching a form or power did besides goes in `said`."""
    if event.kind != "change":
        return None
    most = limits.most(event.tracker, state.get("on", []))
    if most is None:
        return None
    if event.tracker.startswith(SWITCH):
        return switch(state, limits, event.tracker.removeprefix(SWITCH), event.amount, said)
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
    if limits.vitae is not None and event.tracker in ("blood", DRANK):
        return change_vitae(state, limits.vitae, event.amount)
    if event.tracker in TRACKERS:
        before = state[event.tracker]
        state[event.tracker] = max(limits.least(event.tracker), min(before + event.amount, most))
        return before, state[event.tracker]
    before = state["uses"].get(event.tracker, most)
    state["uses"][event.tracker] = max(0, min(before + event.amount, most))
    return before, state["uses"][event.tracker]


def change_vitae(state: dict[str, Any], vitae: Vitae, amount: int) -> tuple[int, int]:
    """Spend or drink a ghoul's vitae (core p. 297): never more than its most, and
    drunk into a full pool it takes the place of human Blood. Human Blood is never
    spent."""
    before = state["blood"]
    state["blood"] = max(0, min(before + amount, vitae.most))
    human = state.setdefault("human", vitae.pool - before)
    state["human"] = max(0, min(human, vitae.pool - state["blood"]))
    return before, state["blood"]


def in_order(events: Iterable[PlayEvent]) -> list[PlayEvent]:
    """The order taps happened in on their devices; ties in the order they arrived."""
    return sorted(events, key=lambda e: (e.happened_at, e.id))


@dataclass
class Replay:
    state: dict[str, Any]
    # Each change's tracker before and after, by event id.
    changes: dict[uuid.UUID, tuple[int, int] | None]
    undone: set[uuid.UUID]
    # What switching a form or power also did, for the log, by event id.
    said: dict[uuid.UUID, list[str]] = field(default_factory=dict[uuid.UUID, list[str]])


def replay(limits: Limits, events: Sequence[PlayEvent]) -> Replay:
    """The game's trackers after its taps, skipping those undone. An undone tap
    keeps what it changed when it was made, for the log."""
    undone = {e.undoes_id for e in events if e.kind == "undo" and e.undoes_id is not None}
    state = limits.start()
    changes: dict[uuid.UUID, tuple[int, int] | None] = {}
    said: dict[uuid.UUID, list[str]] = {}
    for event in in_order(events):
        if event.kind == "undo" or event.id in undone:
            continue
        said[event.id] = []
        changes[event.id] = apply(state, limits, event, said[event.id])
    return Replay(state, changes, undone, {k: v for k, v in said.items() if v})


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


def describe(
    event: PlayEvent,
    limits: Limits,
    target: PlayEvent | None = None,
    said: Sequence[str] = (),
) -> str:
    """The tap as the log reads it: "Blood 7 → 6", "Turned into fight form"."""
    if event.kind == "note":
        return "Note"
    if event.kind == "undo":
        return f"Undid: {describe(target, limits)}" if target is not None else "Undid a tap"
    name = limits.name(event.tracker)
    if event.tracker.startswith(SWITCH):
        found = limits.switch(event.tracker.removeprefix(SWITCH))
        if found is not None and found.form:
            text = f"Turned into {name}" if event.amount > 0 else f"Out of {name}"
        else:
            text = f"{name} on" if event.amount > 0 else f"{name} off"
        return f"{text}: {', '.join(said)}" if said else text
    if event.tracker.startswith(TEMPORARY):
        return f"Temporary derangement {'added' if event.amount > 0 else 'removed'}: {name}"
    if event.tracker == DRANK:
        text = f"Drank {event.amount} vitae"
        if event.before is not None and event.after is not None:
            text += f": Vitae {event.before} → {event.after}"
        return text
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
    # A game ending can end negative status.
    sect_status.expire(db, character, actor)
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
    vitae = SPLATS[character.splat].vitae is not None
    # The earliest game whose Derangement traits (or a ghoul's vitae) these taps change.
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
        if carries((target or event).tracker, vitae):
            carried = game.number if carried is None else min(carried, game.number)
    for game in touched.values():
        refresh(db, game, limits(db, character, game))
    # Derangement traits and a ghoul's vitae carry from game to game, so a late tap
    # in a game already over moves where each game after it started them.
    if carried is not None:
        for game in games.values():
            if game.number > carried and game.id not in touched:
                refresh(db, game, limits(db, character, game))
    db.flush()
