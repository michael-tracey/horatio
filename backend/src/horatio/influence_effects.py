"""What targeted influence actions do to influence (MET: VtM core, pp. 510-512).

Staff log an Attack, Boost or Block in the influence log with its target
(horatio.influence_targets). Resolving it records an **effect**:

- **Attack:** the target loses levels of one type, and as many of its unspent
  actions. Within a type each level costs the attacker 2 actions, across types 3.
  The target's Defends of that type, logged earlier in the attack's month, take a
  level off each (p. 511), against every attack that month. The levels come back
  after two games or one month, whichever is later; the actions do not;
- **Boost:** raises another character's level of the same type by 1, for as many
  actions as their level, up to 10, to the end of the month. They get the boosted
  level's actions for that month;
- **Block:** adds its strength to the cost of an activity in one type, such as
  "acquiring firearms". A level-5 location action (No Party Crashers, Lockdown)
  puts a level-5 block on trouble at its site for 24 hours.

While an effect lasts, the target's rating counts lower (or higher) for what it
can reach (horatio.influence.standings) and for the Play View's counters, and the
actions lost or gained come off (or are added to) its next downtime allowance, as
owed actions. Effects end by themselves: whether one lasts is worked out from its
dates and the target's games whenever it is read. Months are calendar months in UTC.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from horatio import audit, downtimes, influence, influence_log
from horatio.influence import InfluenceType
from horatio.models import (
    Character,
    InfluenceEffect,
    InfluenceEntry,
    OwedAction,
    PlayEvent,
    PlayGame,
    ScheduledGame,
    Troupe,
    User,
)
from horatio.renames import add_months
from horatio.sheets import conflict, unprocessable

if TYPE_CHECKING:
    from horatio.play import Expendable

ATTACK = "attack"
BOOST = "boost"
BLOCK = "block"
# The level-5 actions that secure a site: trouble there faces a level-5 block (pp. 513-514).
LOCATION_ACTIONS = frozenset({"no_party_crashers", "lockdown"})
LOCATION_STRENGTH = 5
LOCATION_LASTS = timedelta(hours=24)
# An attack's levels come back after two games or a month, whichever is later.
ATTACK_GAMES = 2
# Boosts go no higher.
HIGHEST = 10


def now() -> datetime:
    """The current time; tests replace this."""
    return datetime.now(UTC)


def month_start(at: datetime) -> datetime:
    return at.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month(at: datetime) -> datetime:
    """The start of the month after `at`'s: when a Boost ends."""
    start = month_start(at)
    return datetime.combine(add_months(start.date(), 1), start.timetz())


def a_month_on(at: datetime) -> datetime:
    """The same moment a calendar month later."""
    at = at.astimezone(UTC)
    return datetime.combine(add_months(at.date(), 1), at.timetz())


def attack_cost(spent: InfluenceType, aimed: InfluenceType) -> int:
    """Actions an attack spends on each level: 2 within a type, 3 across (p. 510)."""
    return 2 if spent == aimed else 3


def boost_cost(rating: int, levels: int) -> int:
    """Actions raising a rating by `levels` costs: the level each step starts from (p. 511)."""
    return sum(max(level, 1) for level in range(rating, rating + levels))


def boost_levels(rating: int, spent: int) -> int:
    """The most levels `spent` actions raise a rating by, up to 10."""
    levels = 0
    while rating + levels < HIGHEST and boost_cost(rating, levels + 1) <= spent:
        levels += 1
    return levels


# --- how long effects last --------------------------------------------------------------


def games_played(db: Session, effect: InfluenceEffect, at: datetime) -> int:
    """The games the target has played since the effect began: Play View games with a
    tap since then that have ended by `at`, or the troupe's scheduled games over by
    then, whichever counts more (for a character whose player keeps no Play View)."""
    if effect.character_id is None:
        return effect.games  # the character is gone: only the dates count
    played = (
        db.scalar(
            select(func.count(PlayGame.id)).where(
                PlayGame.character_id == effect.character_id,
                PlayGame.ended_at.is_not(None),
                PlayGame.ended_at <= at,
                exists().where(
                    PlayEvent.game_id == PlayGame.id, PlayEvent.happened_at >= effect.starts_at
                ),
            )
        )
        or 0
    )
    scheduled = (
        db.scalar(
            select(func.count(ScheduledGame.id)).where(
                ScheduledGame.troupe_id == effect.troupe_id,
                ScheduledGame.starts_at >= effect.starts_at,
                ScheduledGame.ends_at <= at,
            )
        )
        or 0
    )
    return max(played, scheduled)


@dataclass(frozen=True)
class Lasting:
    """Whether an effect holds at a moment, and what it still waits for."""

    active: bool
    # Games still to play before it can end; 0 once played, or for one that needs none.
    games_left: int
    # Its dates have not begun yet.
    upcoming: bool = False


def lasting(db: Session, effect: InfluenceEffect, at: datetime | None = None) -> Lasting:
    at = at or now()
    if at < effect.starts_at:
        return Lasting(active=False, games_left=effect.games, upcoming=True)
    left = max(0, effect.games - games_played(db, effect, at)) if effect.games else 0
    return Lasting(active=at < effect.ends_at or left > 0, games_left=left)


def on_character(
    db: Session, character_id: uuid.UUID, at: datetime | None = None
) -> list[tuple[InfluenceEffect, Lasting]]:
    """The Attacks and Boosts holding on a character now, oldest first."""
    at = at or now()
    found = db.scalars(
        select(InfluenceEffect)
        .where(
            InfluenceEffect.character_id == character_id,
            InfluenceEffect.kind.in_((ATTACK, BOOST)),
            InfluenceEffect.levels > 0,
            InfluenceEffect.starts_at <= at,
            or_(InfluenceEffect.ends_at > at, InfluenceEffect.games > 0),
        )
        .order_by(InfluenceEffect.starts_at)
    )
    held = [(e, lasting(db, e, at)) for e in found]
    return [(e, h) for e, h in held if h.active]


def changes(db: Session, character_id: uuid.UUID) -> dict[InfluenceType, int]:
    """How far the effects holding now move each type's rating: down for Attacks,
    up for Boosts."""
    moved: dict[InfluenceType, int] = dict.fromkeys(influence.TYPES, 0)
    for effect, _ in on_character(db, character_id):
        if effect.type in moved:
            sign = -1 if effect.kind == ATTACK else 1
            moved[effect.type] += sign * effect.levels  # type: ignore[index]  # checked by the database
    return moved


def rating_with(rating: int, change: int) -> int:
    """A rating moved by its effects: never below 0, nor boosted past 10."""
    if change < 0:
        return max(0, rating + change)
    return min(max(rating, HIGHEST), rating + change)


def play_uses(
    db: Session, character: Character, expendables: Sequence["Expendable"]
) -> list["Expendable"]:
    """The Play View's Influences counters, at the ratings the effects leave."""
    moved = changes(db, character.id)
    by_trait = {influence.TRAITS[t]: c for t, c in moved.items() if c}
    if not by_trait:
        return list(expendables)
    return [
        replace(e, uses=rating_with(e.uses, by_trait[e.name]))
        if e.counter_id is None and e.name in by_trait
        else e
        for e in expendables
    ]


# --- owed actions -----------------------------------------------------------------------


def owe(
    db: Session,
    actor: User,
    character: Character,
    influence_type: InfluenceType,
    amount: int,
    reason: str,
) -> OwedAction | None:
    """Take actions off (or, negative, add them to) the character's next allowance of
    the type in its home troupe: its current cycle's, if it has not submitted yet."""
    home = character.home_troupe_id
    if amount == 0 or home is None or character.kind != "pc":
        return None
    debt = OwedAction(
        character_id=character.id,
        troupe_id=home,
        action_kind=influence.ACTION_KINDS[influence_type],
        amount=amount,
        reason=reason,
        owed_by=actor.id,
    )
    db.add(debt)
    db.flush()
    current = downtimes.current_participation(db, character)
    if current is not None and current[0].troupe_id == home:
        downtimes.settle_owed_actions(db, current[1], current[0])
    return debt


# --- resolving an entry -----------------------------------------------------------------


@dataclass
class Plan:
    """What resolving an entry would record, for staff to check first."""

    kind: str  # attack | boost | block
    entry: InfluenceEntry
    # The influence it changes.
    influence_type: InfluenceType
    # An Attack's or Boost's target, and its name.
    character: Character | None = None
    name: str = ""
    # Actions the entry spent: its times taken.
    spent: int = 0
    # Levels asked for (an Attack's or Boost's), or a Block's strength.
    levels: int = 0
    # The actions those levels cost.
    cost: int = 0
    # An Attack's actions a level: 2 within a type, 3 across.
    per_level: int = 0
    # The target's rating now, with any effects already on it.
    rating: int = 0
    # The target's Defends that count against an Attack, and the levels they take off.
    defends: list[InfluenceEntry] = field(default_factory=list[InfluenceEntry])
    defended: int = 0
    # Levels it changes in the end, or a Block's strength.
    result: int = 0
    activity: str = ""
    starts_at: datetime = field(default_factory=now)
    ends_at: datetime = field(default_factory=now)
    games: int = 0
    # Things staff should know: an Attack costing more than was spent, say.
    notes: list[str] = field(default_factory=list[str])


def kind_of(entry: InfluenceEntry) -> str | None:
    """The effect resolving the entry would record, or None for one that makes none."""
    if entry.action_key in (influence.ATTACK, influence.BOOST, influence.BLOCK):
        return entry.action_key
    if entry.action_key in LOCATION_ACTIONS:
        return BLOCK
    return None


def effect_of(db: Session, entry_id: uuid.UUID) -> InfluenceEffect | None:
    return db.scalar(select(InfluenceEffect).where(InfluenceEffect.entry_id == entry_id))


def target_of(db: Session, entry: InfluenceEntry) -> tuple[Character | None, str]:
    """An Attack's or Boost's target: the character it names, or whoever took the
    entry it targets. With the name to show."""
    if entry.target_character_id is not None:
        character = db.get(Character, entry.target_character_id)
        return character, entry.target_name or (character.name if character else "")
    target = db.get(InfluenceEntry, entry.target_entry_id) if entry.target_entry_id else None
    if target is None:
        return None, ""
    character = db.get(Character, target.character_id) if target.character_id else None
    return character, target.name


def defends_before(
    db: Session, entry: InfluenceEntry, character_id: uuid.UUID, aimed: InfluenceType
) -> list[InfluenceEntry]:
    """The target's Defends of the type logged before the attack, in its month (p. 511)."""
    defender = func.coalesce(InfluenceEntry.target_character_id, InfluenceEntry.character_id)
    return list(
        db.scalars(
            select(InfluenceEntry)
            .where(
                InfluenceEntry.troupe_id == entry.troupe_id,
                InfluenceEntry.action_key == influence.DEFEND,
                InfluenceEntry.type == aimed,
                defender == character_id,
                InfluenceEntry.happened_at >= month_start(entry.happened_at),
                InfluenceEntry.happened_at < entry.happened_at,
            )
            .order_by(InfluenceEntry.happened_at)
        )
    )


def current_rating(db: Session, character: Character, influence_type: InfluenceType) -> int:
    return influence.standings(db, character)[influence_type].rating


def plan(
    db: Session,
    entry: InfluenceEntry,
    *,
    levels: int | None = None,
    influence_type: InfluenceType | None = None,
    activity: str | None = None,
    ends_at: datetime | None = None,
) -> Plan:
    """What resolving the entry would do. `levels` overrides the levels its actions
    pay for (or a Block's strength); the cost is shown either way."""
    short = influence_log.short_id(entry)
    if effect_of(db, entry.id) is not None:
        raise conflict(f"{short} is resolved already.")
    kind = kind_of(entry)
    if kind is None:
        raise unprocessable(
            "Only an Attack, Boost or Block, or a level-5 location action, changes influence."
        )
    if entry.needs_details:
        raise unprocessable(f"Finish {short}'s details first.")
    if levels is not None and levels < 0:
        raise unprocessable("Levels are 0 or more.")
    if kind == ATTACK:
        return plan_attack(db, entry, short, levels)
    if kind == BOOST:
        return plan_boost(db, entry, short, levels)
    return plan_block(db, entry, levels, influence_type, activity, ends_at)


def plan_attack(db: Session, entry: InfluenceEntry, short: str, levels: int | None) -> Plan:
    spent_type: InfluenceType = entry.type  # type: ignore[assignment]  # checked by the database
    aimed: InfluenceType = entry.target_type or spent_type  # type: ignore[assignment]
    character, name = target_of(db, entry)
    if character is None:
        if entry.target_entry_id is not None and name:
            raise unprocessable(
                f"{name}, who took that entry, is not in Horatio: there is no rating to lower."
            )
        raise unprocessable(f"Choose who {short} attacks first.")
    per_level = attack_cost(spent_type, aimed)
    asked = entry.times // per_level if levels is None else levels
    rating = current_rating(db, character, aimed)
    defends = defends_before(db, entry, character.id, aimed)
    defended = min(asked, sum(d.times for d in defends))
    result = min(asked - defended, rating)
    found = Plan(
        kind=ATTACK,
        entry=entry,
        influence_type=aimed,
        character=character,
        name=name,
        spent=entry.times,
        levels=asked,
        cost=asked * per_level,
        per_level=per_level,
        rating=rating,
        defends=defends,
        defended=defended,
        result=result,
        starts_at=entry.happened_at,
        ends_at=a_month_on(entry.happened_at),
        games=ATTACK_GAMES,
    )
    if found.cost > found.spent:
        found.notes.append(
            f"{asked} {plural(asked, 'level')} cost {found.cost} actions; "
            f"{short} spent {found.spent}."
        )
    if asked - defended > rating:
        found.notes.append(f"{name} has only {rating} to lose.")
    return found


def plan_boost(db: Session, entry: InfluenceEntry, short: str, levels: int | None) -> Plan:
    boosted: InfluenceType = entry.type  # type: ignore[assignment]  # checked by the database
    character, name = target_of(db, entry)
    if character is None:
        raise unprocessable(f"Choose who {short} boosts first.")
    if character.id == entry.character_id:
        raise unprocessable("A Boost is for someone else: boosting yourself does nothing.")
    rating = current_rating(db, character, boosted)
    asked = boost_levels(rating, entry.times) if levels is None else levels
    if rating + asked > HIGHEST:
        raise unprocessable(f"Boosts go up to {HIGHEST}; {name} is at {rating}.")
    found = Plan(
        kind=BOOST,
        entry=entry,
        influence_type=boosted,
        character=character,
        name=name,
        spent=entry.times,
        levels=asked,
        cost=boost_cost(rating, asked),
        rating=rating,
        result=asked,
        starts_at=entry.happened_at,
        ends_at=next_month(entry.happened_at),
    )
    if found.cost > found.spent:
        found.notes.append(
            f"Raising {name} from {rating} to {rating + asked} costs {found.cost} actions; "
            f"{short} spent {found.spent}."
        )
    return found


def plan_block(
    db: Session,
    entry: InfluenceEntry,
    levels: int | None,
    influence_type: InfluenceType | None,
    activity: str | None,
    ends_at: datetime | None,
) -> Plan:
    location = entry.action_key in LOCATION_ACTIONS
    blocked: InfluenceType = influence_type or entry.target_type or entry.type  # type: ignore[assignment]
    strength = levels if levels is not None else LOCATION_STRENGTH if location else entry.times
    default_activity = (
        f"Trouble at the site: {entry.purpose}" if location and entry.purpose else entry.purpose
    )
    return Plan(
        kind=BLOCK,
        entry=entry,
        influence_type=blocked,
        spent=entry.times,
        levels=strength,
        cost=0 if location else strength,
        result=strength,
        activity=" ".join((activity or entry.target_activity or default_activity).split()),
        starts_at=entry.happened_at,
        ends_at=ends_at
        or (entry.happened_at + LOCATION_LASTS if location else next_month(entry.happened_at)),
    )


def plural(n: int, word: str) -> str:
    return word if n == 1 else f"{word}s"


def describe(effect: InfluenceEffect) -> str:
    """ "Elite 2 lower", "Underworld 1 higher", "Block 2 on acquiring firearms (Underworld)"."""
    type_name = influence.TYPE_NAMES.get(effect.type, effect.type)  # type: ignore[call-overload]
    if effect.kind == BLOCK:
        return f"Block {effect.levels} on {effect.activity} ({type_name})"
    if effect.kind == ATTACK and effect.levels == 0:
        return f"{type_name} attack, fully defended"
    return f"{type_name} {effect.levels} {'lower' if effect.kind == ATTACK else 'higher'}"


def record(db: Session, actor: User, troupe: Troupe, found: Plan) -> InfluenceEffect:
    """Record what the plan says: the effect, and the actions owed or gained."""
    entry = found.entry
    short = influence_log.short_id(entry)
    if found.kind == BLOCK:
        check_block(found.levels, found.activity, found.starts_at, found.ends_at)
    elif found.levels < 1:
        raise unprocessable("Choose at least one level.")
    effect = InfluenceEffect(
        troupe_id=troupe.id,
        kind=found.kind,
        type=found.influence_type,
        character_id=found.character.id if found.character else None,
        name=found.name,
        entry_id=entry.id,
        levels=found.result,
        defended=found.defended,
        activity=found.activity,
        starts_at=found.starts_at,
        ends_at=found.ends_at,
        games=found.games,
        recorded_by=actor.id,
    )
    db.add(effect)
    db.flush()
    if found.character is not None and found.result > 0:
        type_name = influence.TYPE_NAMES[found.influence_type]
        if found.kind == ATTACK:
            reason = f"Lost to an attack ({short})"
            debt = owe(db, actor, found.character, found.influence_type, found.result, reason)
        else:
            debt = owe(
                db,
                actor,
                found.character,
                found.influence_type,
                -found.result,
                f"Boosted to {type_name} {found.rating + found.result} ({short})",
            )
        effect.owed_action_id = debt.id if debt else None
        db.flush()
    audit.record(
        db,
        actor,
        "influence.resolved",
        troupe_id=troupe.id,
        entry=short,
        entry_id=str(entry.id),
        who=found.name or "an activity",
        what=describe(effect),
    )
    return effect


def check_block(strength: int, activity: str, starts_at: datetime, ends_at: datetime) -> None:
    if strength < 1:
        raise unprocessable("A Block's strength is at least 1.")
    if not activity:
        raise unprocessable("Say what the Block is on, such as acquiring firearms.")
    if ends_at <= starts_at:
        raise unprocessable("A Block ends after it starts.")


def record_block(
    db: Session,
    actor: User,
    troupe: Troupe,
    *,
    influence_type: InfluenceType,
    activity: str,
    strength: int,
    starts_at: datetime,
    ends_at: datetime | None,
) -> InfluenceEffect:
    """A Block staff record on their own, such as an NPC's, with no log entry."""
    activity = " ".join(activity.split())
    ends_at = ends_at or next_month(starts_at)
    check_block(strength, activity, starts_at, ends_at)
    effect = InfluenceEffect(
        troupe_id=troupe.id,
        kind=BLOCK,
        type=influence_type,
        levels=strength,
        activity=activity,
        starts_at=starts_at,
        ends_at=ends_at,
        recorded_by=actor.id,
    )
    db.add(effect)
    db.flush()
    audit.record(db, actor, "influence.block_recorded", troupe_id=troupe.id, what=describe(effect))
    return effect


def remove(db: Session, actor: User, effect: InfluenceEffect) -> str | None:
    """Take an effect back, as if it had not been resolved. Its owed actions go too,
    unless a cycle has taken them already: then says so, for staff to adjust."""
    note = None
    debt = db.get(OwedAction, effect.owed_action_id) if effect.owed_action_id else None
    if debt is not None and debt.participant_id is None:
        db.delete(debt)
    elif debt is not None:
        how = "came off" if debt.amount > 0 else "were added to"
        note = (
            f"The {abs(debt.amount)} {plural(abs(debt.amount), 'action')} {how} a downtime "
            "allowance already; adjust it there if need be."
        )
    entry = db.get(InfluenceEntry, effect.entry_id) if effect.entry_id else None
    what = describe(effect)
    db.delete(effect)
    db.flush()
    audit.record(
        db,
        actor,
        "influence.effect_removed",
        troupe_id=effect.troupe_id,
        entry=influence_log.short_id(entry) if entry else "",
        what=what,
    )
    return note


# --- reading ----------------------------------------------------------------------------


def troupe_effects(
    db: Session, troupe_id: uuid.UUID, *, ended: bool = False
) -> list[tuple[InfluenceEffect, Lasting]]:
    """The troupe's effects, newest first: those holding now or still to begin, or
    with `ended` every one."""
    found = db.scalars(
        select(InfluenceEffect)
        .where(InfluenceEffect.troupe_id == troupe_id)
        .order_by(InfluenceEffect.starts_at.desc(), InfluenceEffect.id.desc())
    )
    held = [(e, lasting(db, e)) for e in found]
    return held if ended else [(e, h) for e, h in held if h.active or h.upcoming]


# --- blocks against an answer -----------------------------------------------------------

WORD = re.compile(r"[a-z]+")
# Words that say nothing about which activity is meant.
COMMON = frozenset(
    {
        *("about", "after", "against", "also", "area", "before", "being", "could", "each"),
        *("elite", "from", "have", "influence", "into", "just", "make", "more", "most"),
        *("other", "over", "site", "some", "than", "that", "their", "them", "then", "there"),
        *("they", "this", "through", "trouble", "under", "underworld", "using", "want"),
        *("what", "when", "where", "which", "while", "will", "with", "would"),
    }
)


def words(text: str) -> set[str]:
    """The words of `text` that name things, roughly stemmed: "firearms" is "firearm"."""
    found: set[str] = set()
    for word in WORD.findall(text.lower()):
        if len(word) < 4 or word in COMMON:
            continue
        for ending in ("ing", "ed", "es", "s"):
            if word.endswith(ending) and len(word) - len(ending) >= 4:
                word = word[: -len(ending)]
                break
        found.add(word)
    return found


def blocks_against(
    db: Session,
    troupe_id: uuid.UUID,
    influence_type: InfluenceType,
    text: str,
    since: datetime,
) -> list[InfluenceEffect]:
    """Blocks of the type, holding at some time from `since` to now, whose activity
    shares a word with `text`: what an answer may be up against. The cost is still
    for staff to judge."""
    said = words(text)
    if not said:
        return []
    found = db.scalars(
        select(InfluenceEffect)
        .where(
            InfluenceEffect.troupe_id == troupe_id,
            InfluenceEffect.kind == BLOCK,
            InfluenceEffect.type == influence_type,
            InfluenceEffect.starts_at <= now(),
            InfluenceEffect.ends_at > since,
        )
        .order_by(InfluenceEffect.levels.desc())
    )
    return [b for b in found if words(b.activity) & said]
