"""Location quests, and what a location gives its controller (issue #326; MET: VTM
Vol. II Issue 1, pp. 118-129). It joins quests (horatio.quests) and locations
(horatio.locations).

**Requests.** Besides a custom quest, a player asks to acquire a location (by its
name, address and map link), to add a quality to one of their character's own,
to undermine one (with a negative quality, or an infiltration with its victory
condition), to repair one of their own, or to learn with a dot of Contacts which
locations another character controls (p. 126). Each counts toward the troupe's
requests per cycle. Players never see location records, so a place to acquire or
undermine is typed in; staff match it to the record, or make a new standard one.

**Building.** From a location and the change wanted, `plan` works out the quest:
its category from the book's tables (pp. 120, 125-126; "Heroic" is Epic here), its
difficulty (the rating; Historic +1 to taking control, Guards +1 to infiltrating;
p. 126 lets qualities raise it past 5), the requirements its qualities suggest at
the levels for its rating, and why it can't be built: a locked location, a Haven,
or a controlled one to acquire before Insolvent ×3 opens it to a Complex quest.

**Completing** a location quest makes its change (`complete`): control passes to
its leader, a quality is added (and the rating goes up) or swapped, the type is
upgraded, a negative is added, or an infiltration's victory is recorded. A
controller who loses the location is told, without the record.

**Negatives.** Staff remove one level of a negative for what the book asks (p.
127-129): Resources dots for Damaged, Elite influence for Insolvent and Shunned,
Underworld influence for Compromised and Out of Code, each at the location's
rating, spent as a quest requirement's expenditure is. Out of Code gets worse by
itself when two games pass without it being removed (`game_passed`), and staff
are told before and when it does. Insolvent ×2 makes the location forfeit if its
rating is above its controller's Resources, which staff confirm.

**What qualities give** (`held`): Profitable, Hangout, Clubhouse, Artistic, Fancy
and Lowdown and Dirty give the controller what they say, unless a negative
switches them off; a secret negative does too, without the player being told why.
Fancy and Lowdown and Dirty go into the next cycle's action allowance.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import audit, locations, quest_requirements, quests
from horatio.models import Character, Location, Quest, QuestRequest, QuestScenario, Troupe, User
from horatio.notifications import notify, staff_for
from horatio.permissions import TroupeAction
from horatio.quest_requirements import (
    BackgroundSpend,
    InfluenceSpend,
    Option,
    TextNeed,
    TraitNeed,
)
from horatio.rules.allowance import AllowanceLine
from horatio.rules.locations import BOOK, LocationRules, Suggestion
from horatio.sheets import conflict, unprocessable

NEGATIVES = ("Damaged", "Insolvent", "Compromised", "Out of Code", "Shunned")
# What removes one level of each negative, at the location's rating (pp. 127-129).
REMOVED_BY: dict[str, Literal["resources", "elite", "underworld"]] = {
    "Damaged": "resources",
    "Insolvent": "elite",
    "Shunned": "elite",
    "Compromised": "underworld",
    "Out of Code": "underworld",
}
REQUEST_KINDS = ("acquire", "quality", "undermine", "repair", "whose")


def page(p: str) -> str:
    return f" ({BOOK}, p. {p})"


# --- the change a quest makes -------------------------------------------------------------

ChangeKind = Literal["acquire", "quality", "swap", "upgrade", "negative", "infiltrate"]


class Change(BaseModel):
    """What a location quest does to its location when it is completed."""

    kind: ChangeKind
    # The quality to add or swap in, with its detail (a Hangout's specialisation).
    quality: str = Field(default="", max_length=80)
    detail: str = Field(default="", max_length=120)
    # The quality swapped out.
    swap_out: str = Field(default="", max_length=80)
    # The negative to add, kept secret from the controller or not.
    negative: str = Field(default="", max_length=40)
    secret: bool = False
    # An infiltration's one victory condition: steal, plant or rescue (p. 126).
    victory: str = Field(default="", max_length=500)


# The book's quest for each type of location: to obtain, affect or add a quality;
# to change one (p. 125); and to upgrade its type (p. 126). None: it can't be.
CATEGORIES: dict[str, dict[str, str | None]] = {
    "standard": {"add": "simple", "change": "simple", "upgrade": "complex"},
    "prestige": {"add": "complex", "change": "simple", "upgrade": "epic"},
    "iconic": {"add": "epic", "change": "complex", "upgrade": None},
}
UPGRADES = {"standard": "prestige", "prestige": "iconic"}
HEROIC = "The book's Heroic quest is Epic here."


def describe_change(location: Location, change: Change) -> str:
    """The change as staff read it: "control passes to its leader"."""
    match change.kind:
        case "acquire":
            return "control passes to its leader"
        case "quality":
            what = f"{change.quality} ({change.detail})" if change.detail else change.quality
            return f"it gains {what}, and its rating goes up by one"
        case "swap":
            return f"{change.swap_out} becomes {change.quality}"
        case "upgrade":
            return f"it becomes {UPGRADES.get(location.kind, location.kind)}"
        case "negative":
            return f"it gains {change.negative}" + (", secret" if change.secret else "")
        case "infiltrate":
            return f"the party achieves its goal: {change.victory}"


def level_of(location: Location, name: str) -> int:
    return next((n["level"] for n in location.negatives if n["name"] == name), 0)


def quality_names(location: Location) -> list[str]:
    return [q["name"] for q in location.qualities]


@dataclass
class Modifier:
    reason: str
    amount: int


@dataclass
class Suggested:
    """A requirement a quality suggests, at the level for the location's rating."""

    source: str
    options: list[Option]


@dataclass
class Plan:
    category: str
    # Why the category is what it is, where it isn't plain from the table.
    category_note: str
    difficulty: int
    modifiers: list[Modifier]
    suggestions: list[Suggested]
    # What lets the party meet one requirement fewer (Derelict, a conglomerate).
    fewer: list[str]
    # Why no such quest can be built now; None when it can.
    refusal: str | None


def level_for(levels: Sequence[int], rating: int) -> int:
    """A suggestion's level for a location of `rating`: its levels spread evenly
    over ratings 1 to 5, lowest first ("Crafts [2,3,4]" is 2 for ratings 1-2, 3 for
    3-4 and 4 for 5)."""
    if not levels:
        return 1
    return levels[min(len(levels) - 1, (rating - 1) * len(levels) // 5)]


# Trait names a suggestion gives that are backgrounds; the rest are skills.
BACKGROUNDS = {"Resources", "Retainers", "Fame", "Contacts", "Allies", "Herd", "Haven", "Mentor"}
INFLUENCES = {"Influences: The Elite": "elite", "Influences: The Underworld": "underworld"}


def trait_option(name: str, level: int, detail: str, expend: bool) -> Option:
    special = "" if detail.startswith("of ") else detail
    influence = INFLUENCES.get(name)
    if expend and influence is not None:
        return InfluenceSpend(type=influence, level=level, area=special)  # type: ignore[arg-type]
    if expend:
        return BackgroundSpend(name=name, dots=level)
    category = "backgrounds" if name in BACKGROUNDS or influence else "skills"
    return TraitNeed(category=category, name=name, rating=level, specialization=special)  # type: ignore[arg-type]


def suggestion_options(s: Suggestion, rating: int) -> list[Option]:
    """A catalogue suggestion as a requirement's alternatives."""
    if s.text:
        return [TextNeed(text=s.text)]
    if s.power:
        return [TraitNeed(category="power", name=s.power.split(": ", 1)[1], rating=1)]
    level = level_for(s.levels, rating)
    names = list(s.traits) or [s.trait]
    found = [trait_option(n, level, s.detail, s.expend) for n in names]
    if s.alternative:
        found.append(TextNeed(text=s.alternative[0].upper() + s.alternative[1:]))
    return found


def suggestions(rules: LocationRules, location: Location, change: Change) -> list[Suggested]:
    """What the location's qualities suggest at the levels for its rating, and what
    the quality being added does."""
    names = list(dict.fromkeys(quality_names(location)))
    if change.kind in ("quality", "swap") and change.quality and change.quality not in names:
        names.append(change.quality)
    found: list[Suggested] = []
    for name in names:
        known = rules.qualities.get(name)
        if known is None:
            continue
        for s in known.suggested:
            found.append(Suggested(name, suggestion_options(s, location.rating)))
    return found


def controls(location: Location, character_id: uuid.UUID | None) -> bool:
    return character_id is not None and character_id in (location.controller_id, location.joint_id)


def refusal(
    db: Session, rules: LocationRules, location: Location, change: Change, leader: Character | None
) -> str | None:
    """Why the quest can't target the location now, if it can't."""
    if location.locked:
        return f"{location.name} is locked: no quest may target it."
    if location.kind == "haven":
        return (
            f"{location.name} is a Haven: it can't be targeted as a Stock Location can"
            f"{page('117')}."
        )
    hostile = change.kind in ("acquire", "negative", "infiltrate")
    if hostile and location.haven_of_id is not None:
        return f"{location.name} is a character's Haven: it can't be targeted{page('117')}."
    held = location.control in ("character", "named")
    if change.kind == "acquire":
        if location.control == "uncontrollable":
            return f"No one can control {location.name}{page('121')}."
        if leader is not None and controls(location, leader.id):
            return f"{leader.name} already controls {location.name}."
        if held and level_of(location, "Insolvent") < 3:
            who = locations.who(db, location.controller_id, location.controller_name)
            return (
                f"{location.name} is controlled by {who}: it must be undermined first"
                f"{page('121')}. Insolvent ×3 opens it to anyone, with a Complex quest"
                f"{page('128')}."
            )
    changes_it = change.kind in ("quality", "swap", "upgrade")
    if changes_it and leader is not None and not controls(location, leader.id):
        return f"Only whoever controls {location.name} changes it, and {leader.name} doesn't."
    if change.kind == "upgrade" and CATEGORIES[location.kind]["upgrade"] is None:
        return f"An iconic location can't be upgraded further{page('126')}."
    if change.kind == "negative":
        known = rules.negatives.get(change.negative)
        if known is None:
            return "Choose the negative quality to impose."
        most = locations.catalogue.most_negative(rules, change.negative, quality_names(location))
        if level_of(location, change.negative) >= most:
            return f"{location.name} already has {change.negative} ×{most}, the most it takes."
    if change.kind == "infiltrate" and not change.victory.strip():
        return "Give the infiltration its one victory condition: steal, plant or rescue."
    if change.kind == "swap" and change.swap_out not in quality_names(location):
        return f"Choose which of {location.name}'s qualities is swapped."
    if change.kind in ("quality", "swap"):
        if change.quality not in rules.qualities:
            return f"{change.quality or 'That'} isn't a location quality in this troupe."
        draft = changed_draft(db, location, change, leader)
        had = set(quality_names(location))
        if reason := locations.problem(rules, draft, had, locations.this_year()):
            return reason
    return None


def category_of(location: Location, change: Change) -> tuple[str, str]:
    """The quest's category, and a note where the table isn't the whole story."""
    if location.kind not in CATEGORIES:
        return "simple", ""
    table = CATEGORIES[location.kind]
    held = location.control in ("character", "named")
    if change.kind == "acquire" and held and level_of(location, "Insolvent") >= 3:
        return "complex", f"Insolvent ×3: anyone may take it with a Complex quest{page('128')}."
    column = {"swap": "change", "upgrade": "upgrade"}.get(change.kind, "add")
    category = table[column] or "epic"
    return category, HEROIC if category == "epic" else ""


def difficulty_of(location: Location, change: Change) -> tuple[int, list[Modifier]]:
    """The location's rating, and what its qualities add (p. 126)."""
    modifiers = [Modifier(f"Rating {location.rating}", location.rating)]
    names = quality_names(location)
    if change.kind == "acquire" and "Historic" in names:
        modifiers.append(Modifier("Historic +1", 1))
    if change.kind == "infiltrate" and "Guards" in names:
        modifiers.append(Modifier("Guards +1", 1))
    return min(10, sum(m.amount for m in modifiers)), modifiers


def fewer_requirements(
    db: Session, rules: LocationRules, location: Location, leader: Character | None
) -> list[str]:
    found: list[str] = []
    if "Derelict" in quality_names(location):
        found.append("Derelict: one requirement fewer.")
    if rules.on("conglomerates") and location.parent_id is not None and leader is not None:
        parent = db.get(Location, location.parent_id)
        if parent is not None and controls(parent, leader.id):
            found.append(
                f"{leader.name} controls its conglomerate, {parent.name}: one requirement "
                "can be waived (house option: Conglomerates)."
            )
    return found


def plan(
    db: Session, troupe: Troupe, location: Location, change: Change, leader: Character | None
) -> Plan:
    rules = locations.rules_for(db, troupe)
    category, note = category_of(location, change)
    difficulty, modifiers = difficulty_of(location, change)
    return Plan(
        category=category,
        category_note=note,
        difficulty=difficulty,
        modifiers=modifiers,
        suggestions=suggestions(rules, location, change),
        fewer=fewer_requirements(db, rules, location, leader),
        refusal=refusal(db, rules, location, change, leader),
    )


# --- building the quest ------------------------------------------------------------------


def checked_location(db: Session, troupe: Troupe, location_id: uuid.UUID) -> Location:
    location = db.get(Location, location_id)
    if location is None or location.troupe_id != troupe.id:
        raise unprocessable("Choose one of the troupe's locations.")
    return location


def build(
    db: Session,
    staff: User,
    troupe: Troupe,
    location: Location,
    change: Change,
    fields: quests.QuestFields,
    requirements: Sequence[Sequence[Option]],
    request: QuestRequest | None,
) -> Quest:
    """A location quest, in draft, with the requirements staff picked. Refused, with
    the reason, when the location can't be targeted."""
    leader_id = request.character_id if request is not None else fields.leader_id
    leader = db.get(Character, leader_id) if leader_id else None
    if reason := plan(db, troupe, location, change, leader).refusal:
        raise conflict(reason)
    quest = quests.create(db, staff, troupe, fields, request=request)
    quest.location_id = location.id
    quest.location_change = change.model_dump()
    quests.log(
        db, quest, staff, f"aimed it at {location.name}: {describe_change(location, change)}"
    )
    for options in requirements:
        quests.add_requirement(db, staff, quest, options)
    if request is not None and request.location_id is None:
        request.location_id = location.id
    db.flush()
    audit.record(
        db,
        staff,
        "location.quest_built",
        troupe_id=troupe.id,
        quest=quest.name,
        change=describe_change(location, change),
        **locations.describe(location),
    )
    return quest


# --- completing it -------------------------------------------------------------------------


def changed_draft(
    db: Session, location: Location, change: Change, leader: Character | None
) -> locations.Draft:
    """The location as the change leaves it."""
    draft = locations.draft_of(location)
    match change.kind:
        case "acquire":
            if leader is not None:
                draft.control = "character"
                draft.controller_id = leader.id
                draft.controller_name = ""
            draft.joint_id = None
            draft.joint_name = ""
            draft.heir_id = None
            draft.heir_name = ""
        case "quality":
            draft.qualities.append(locations.QualityIn(change.quality, change.detail))
            draft.rating = min(5, draft.rating + 1)
        case "swap":
            index = next(i for i, q in enumerate(draft.qualities) if q.name == change.swap_out)
            draft.qualities[index] = locations.QualityIn(change.quality, change.detail)
        case "upgrade":
            draft.kind = UPGRADES.get(draft.kind, draft.kind)
        case "negative":
            by = leader.name if leader else ""
            for n in draft.negatives:
                if n.name == change.negative:
                    n.level += 1
                    n.secret = n.secret or change.secret
                    break
            else:
                draft.negatives.append(locations.NegativeIn(change.negative, 1, change.secret, by))
        case "infiltrate":
            pass
    return draft


def complete(db: Session, staff: User, quest: Quest) -> None:
    """Make the change a completed location quest makes, log it on the quest and the
    location, and tell a controller who lost it."""
    location = db.get(Location, quest.location_id) if quest.location_id else None
    if location is None or quest.location_change is None:
        quests.log(db, quest, staff, "its location is no longer on the list, so nothing changed")
        return
    troupe = db.get_one(Troupe, quest.troupe_id)
    change = Change(**quest.location_change)
    leader = db.get(Character, quest.leader_id) if quest.leader_id else None
    rules = locations.rules_for(db, troupe)
    if reason := refusal(db, rules, location, change, leader):
        raise conflict(
            f"The quest's change to {location.name} can't be made: {reason} "
            "Change the location first, or close the quest."
        )
    lost = location.controller_id if change.kind == "acquire" else None
    if change.kind != "infiltrate":
        _, warnings = locations.save(
            db, staff, troupe, location, changed_draft(db, location, change, leader)
        )
        for warning in warnings:
            quests.log(db, quest, staff, warning)
    what = describe_change(location, change)
    if change.kind == "acquire" and leader is not None:
        what = f"{leader.name} controls it now"
    quests.log(db, quest, staff, f"{location.name}: {what}")
    audit.record(
        db,
        staff,
        "location.quest_completed",
        troupe_id=troupe.id,
        quest=quest.name,
        change=what,
        **locations.describe(location),
    )
    if lost is not None and (leader is None or lost != leader.id):
        lose(db, location, lost)
    forfeit_warning(db, staff, troupe, location)


def lose(db: Session, location: Location, character_id: uuid.UUID) -> None:
    """Tell a character's player it no longer controls the location, saying nothing
    of the record."""
    character = db.get(Character, character_id)
    if character is None or character.kind != "pc":
        return
    notify(
        db,
        [character.player_id],
        "location.lost",
        f"Your character no longer controls {location.name}.",
        f"/characters/{character.id}",
        troupe_id=location.troupe_id,
        character_id=character.id,
    )


# --- negatives -----------------------------------------------------------------------------


def removal_option(name: str, rating: int) -> Option:
    """What removes one level of the negative at this rating (pp. 127-129)."""
    by = REMOVED_BY[name]
    if by == "resources":
        return BackgroundSpend(name="Resources", dots=rating)
    return InfluenceSpend(type=by, level=rating)


def remove_negative(
    db: Session,
    staff: User,
    troupe: Troupe,
    location: Location,
    name: str,
    character: Character,
    request: QuestRequest | None = None,
) -> str:
    """Take one level of a negative off, spending what the book asks of `character`.
    Returns what was spent, as it reads."""
    level = level_of(location, name)
    if level == 0:
        raise conflict(f"{location.name} isn't {name}.")
    if not quests.in_troupe(db, troupe.id, character):
        raise unprocessable("Choose a character in this troupe.")
    option = removal_option(name, location.rating)
    if isinstance(option, BackgroundSpend):
        held = locations.rating_of(db, character, "backgrounds", "Resources")
        if held < option.dots:
            raise conflict(
                f"Removing {name} takes Resources {option.dots}; {character.name} has {held}."
            )
    elif quest_requirements.meets(db, character, option) is False:
        raise conflict(
            f"Removing {name} takes {quest_requirements.label(option)}, which "
            f"{character.name} can't take."
        )
    spent = quest_requirements.spend(
        db,
        staff,
        troupe,
        character,
        option,
        purpose=f"To remove {name} from {location.name}",
        cycle_id=cycle.id if (cycle := quests.log_cycle(db, troupe)) else None,
    )
    negatives: list[dict[str, Any]] = []
    for n in location.negatives:
        if n["name"] == name:
            if n["level"] > 1:
                negatives.append({**n, "level": n["level"] - 1, "games": 0})
        else:
            negatives.append(n)
    location.negatives = negatives
    if name == "Damaged" and level == 1:
        location.damaged_off = []
    paid = quest_requirements.label(option).replace("Expend ", "")
    words = quests.spent_text(spent)
    said = f"{paid} from {character.name}" + (f" ({words})" if words else "")
    db.flush()
    audit.record(
        db,
        staff,
        "location.negative_removed",
        troupe_id=troupe.id,
        negative=f"{name} ×{level}",
        spent=said,
        **locations.describe(location),
    )
    if request is not None:
        quests.finish_request(db, staff, request, "done", f"{location.name} is repaired.")
    return said


def forfeit_reason(db: Session, location: Location) -> str | None:
    """Insolvent ×2: a controller whose Resources are below its rating must give it
    up (p. 128)."""
    if level_of(location, "Insolvent") < 2 or location.controller_id is None:
        return None
    controller = db.get(Character, location.controller_id)
    if controller is None:
        return None
    resources = locations.rating_of(db, controller, "backgrounds", "Resources")
    if location.rating <= resources:
        return None
    return (
        f"Insolvent ×2: {location.name}'s rating {location.rating} is above {controller.name}'s "
        f"Resources {resources}, so it is forfeit{page('128')}."
    )


def forfeit_warning(db: Session, staff: User | None, troupe: Troupe, location: Location) -> None:
    if (reason := forfeit_reason(db, location)) is None:
        return
    notify(
        db,
        staff_for(db, troupe, TroupeAction.MANAGE_LOCATIONS),
        "location.forfeit",
        f"{reason} Confirm it on the location.",
        f"/troupes/{troupe.id}/locations/{location.id}",
        troupe_id=troupe.id,
    )


def forfeit(db: Session, staff: User, location: Location) -> None:
    """Staff confirm a forfeit: nobody controls it now."""
    if forfeit_reason(db, location) is None:
        raise conflict(f"{location.name} isn't forfeit.")
    lost = location.controller_id
    location.control = "none"
    location.controller_id = None
    location.joint_id = None
    location.joint_name = ""
    db.flush()
    audit.record(
        db, staff, "location.forfeit", troupe_id=location.troupe_id, **locations.describe(location)
    )
    if lost is not None:
        lose(db, location, lost)


def game_passed(db: Session, actor: User | None, troupe: Troupe) -> None:
    """A game has passed in the troupe: each Out of Code counts it, and gets worse by
    itself after two (pp. 128-129). Staff are told after the first, and when it does."""
    rules = locations.rules_for(db, troupe)
    staff = staff_for(db, troupe, TroupeAction.MANAGE_LOCATIONS)
    found = db.scalars(select(Location).where(Location.troupe_id == troupe.id))
    for location in found:
        level = level_of(location, "Out of Code")
        if level == 0:
            continue
        most = locations.catalogue.most_negative(rules, "Out of Code", quality_names(location))
        if level >= most:
            continue
        negatives: list[dict[str, Any]] = []
        said = ""
        for n in location.negatives:
            if n["name"] != "Out of Code":
                negatives.append(n)
                continue
            games = n.get("games", 0) + 1
            if games >= 2:
                negatives.append({**n, "level": level + 1, "games": 0})
                said = (
                    f"Out of Code on {location.name} is now ×{level + 1}: two games passed "
                    "without it being removed."
                )
            else:
                negatives.append({**n, "games": games})
                said = (
                    f"Out of Code on {location.name} goes to ×{level + 1} after the next game "
                    "unless it is removed."
                )
        location.negatives = negatives
        db.flush()
        audit.record(
            db,
            actor,
            "location.out_of_code",
            troupe_id=troupe.id,
            said=said,
            **locations.describe(location),
        )
        notify(
            db,
            staff,
            "location.out_of_code",
            said,
            f"/troupes/{troupe.id}/locations/{location.id}",
            troupe_id=troupe.id,
        )


# --- the Resources shortcut ----------------------------------------------------------------


def expend_resources(
    db: Session,
    staff: User,
    quest: Quest,
    scenario: QuestScenario,
    character: Character,
    dots: int,
) -> int:
    """A member expends Resources on a location quest's scenario: dots equal to the
    difficulty give one success, and each dot over one more (p. 120). Returns the
    successes."""
    if quest.location_id is None:
        raise conflict("Resources succeed a step only on a quest to acquire or change a location.")
    quests.ensure_active(quest)
    if scenario.result == "passed":
        raise conflict(f"Scenario {scenario.number} is already passed.")
    if dots < quest.difficulty:
        raise unprocessable(
            f"Resources succeed a step at the quest's difficulty, {quest.difficulty}, or more"
            f"{page('120')}."
        )
    if not quests.in_troupe(db, quest.troupe_id, character):
        raise unprocessable("Choose a character in this troupe.")
    held = locations.rating_of(db, character, "backgrounds", "Resources")
    if held < dots:
        raise conflict(f"{character.name} has Resources {held}, not {dots}.")
    successes = 1 + dots - quest.difficulty
    scenario.resources = [
        *scenario.resources,
        {
            "character_id": str(character.id),
            "name": character.name,
            "dots": dots,
            "successes": successes,
        },
    ]
    plural = "success" if successes == 1 else "successes"
    quests.log(
        db,
        quest,
        staff,
        f"{character.name} expended Resources {dots} on scenario {scenario.number}: "
        f"{successes} {plural}",
    )
    db.flush()
    return successes


# --- requests ------------------------------------------------------------------------------


class RequestFields(BaseModel):
    kind: Literal["acquire", "quality", "undermine", "repair", "whose"]
    # The place, typed in, to acquire or undermine.
    name: str = Field(default="", max_length=120)
    address: str = Field(default="", max_length=500)
    map_link: str = Field(default="", max_length=1000)
    # One of the character's own locations, to add a quality to or repair.
    location_id: uuid.UUID | None = None
    quality: str = Field(default="", max_length=80)
    detail: str = Field(default="", max_length=120)
    # A negative quality to impose, or an infiltration with its victory condition.
    negative: str = Field(default="", max_length=40)
    victory: str = Field(default="", max_length=500)
    # The character whose locations a Contacts lookup asks after.
    target: str = Field(default="", max_length=120)
    reason: str = Field(default="", max_length=4000)


def own_location(
    db: Session, character: Character, troupe: Troupe, location_id: uuid.UUID | None
) -> Location:
    location = db.get(Location, location_id) if location_id else None
    if location is None or location.troupe_id != troupe.id or not controls(location, character.id):
        raise unprocessable(f"Choose one of {character.name}'s locations.")
    return location


def make_request(
    db: Session, player: User, character: Character, body: RequestFields
) -> QuestRequest:
    """A player's location request, with the objective written for them."""
    troupe = quests.home_troupe(db, character)
    if troupe is None:
        raise conflict("This character's home troupe does not run quests.")
    name = locations.tidy(body.name)
    where = f"{name}, {body.address.strip()}" if body.address.strip() else name
    details: dict[str, Any] = {}
    location: Location | None = None
    match body.kind:
        case "acquire":
            if not name:
                raise unprocessable("Name the place you want.")
            objective = f"Acquire {where}"
            details = {
                "name": name,
                "address": body.address.strip(),
                "map_link": body.map_link.strip(),
            }
        case "quality":
            location = own_location(db, character, troupe, body.location_id)
            rules = locations.rules_for(db, troupe)
            if body.quality not in rules.qualities:
                raise unprocessable("Choose a quality from the catalogue.")
            what = (
                f"{body.quality} ({body.detail.strip()})" if body.detail.strip() else body.quality
            )
            objective = f"Add {what} to {location.name}"
            details = {"quality": body.quality, "detail": body.detail.strip()}
        case "undermine":
            if not name:
                raise unprocessable("Name the place, and give its address if you know it.")
            details = {"name": name, "address": body.address.strip()}
            if body.negative:
                if body.negative not in NEGATIVES:
                    raise unprocessable(
                        "Choose Damaged, Insolvent, Compromised, Out of Code or Shunned."
                    )
                objective = f"Undermine {where}: {body.negative}"
                details["negative"] = body.negative
            else:
                victory = body.victory.strip()
                if not victory:
                    raise unprocessable(
                        "Choose a negative quality, or say what infiltrating it is for."
                    )
                objective = f"Infiltrate {where}: {victory}"
                details["victory"] = victory
        case "repair":
            location = own_location(db, character, troupe, body.location_id)
            objective = f"Repair {location.name}"
        case "whose":
            target = locations.tidy(body.target)
            if not target:
                raise unprocessable("Name the character whose locations you want to learn.")
            if locations.rating_of(db, character, "backgrounds", "Contacts") < 1:
                raise conflict(
                    f"Learning whose locations are whose takes a dot of Contacts{page('126')}; "
                    f"{character.name} has none."
                )
            objective = f"Learn which locations {target} controls, expending a dot of Contacts"
            details = {"target": target}
    return quests.make_request(
        db,
        player,
        character,
        objective=objective,
        reason=body.reason,
        companions="",
        kind=body.kind,
        details=details,
        location_id=location.id if location else None,
    )


def match(
    db: Session,
    staff: User,
    troupe: Troupe,
    request: QuestRequest,
    location_id: uuid.UUID | None,
    new: locations.Draft | None,
) -> Location:
    """Match a request to acquire or undermine a place to the troupe's record of it,
    or make a new standard location from it."""
    if request.kind not in ("acquire", "undermine"):
        raise conflict("Only a request to acquire or undermine a place is matched to one.")
    if request.status in ("answered", "withdrawn"):
        raise conflict("This request is already answered.")
    if location_id is not None:
        location = checked_location(db, troupe, location_id)
    else:
        if new is None:
            raise unprocessable("Choose a location, or make a new one.")
        new.name = new.name or request.details.get("name", "")
        new.address = new.address or request.details.get("address", "")
        new.map_link = new.map_link or request.details.get("map_link", "")
        location, _ = locations.save(db, staff, troupe, None, new)
    request.location_id = location.id
    if request.status == "new":
        request.status = "working"
    db.flush()
    return location


@dataclass
class Whose:
    name: str
    locations: list[str] = field(default_factory=list[str])


def whose(db: Session, troupe: Troupe, target: str) -> list[Whose]:
    """For staff answering a Contacts lookup: the troupe's characters of that name,
    and the locations each controls; Hole in the Wall hides one unless the asker
    has been there (p. 123)."""
    found: list[Whose] = []
    wanted = target.casefold()
    for character in quests.troupe_characters(db, troupe.id):
        if wanted not in character.name.casefold():
            continue
        held = db.scalars(
            select(Location)
            .where(
                Location.troupe_id == troupe.id,
                or_(Location.controller_id == character.id, Location.joint_id == character.id),
            )
            .order_by(Location.name)
        )
        found.append(
            Whose(
                character.name,
                [
                    f"{loc.name} (Hole in the Wall: only if they have been there)"
                    if "Hole in the Wall" in quality_names(loc)
                    else loc.name
                    for loc in held
                ],
            )
        )
    return found


# --- what qualities give their controller --------------------------------------------------


@dataclass
class Effect:
    quality: str
    # What it gives: "Resources 1", "Contacts 1 (Bar regulars)".
    gives: str
    on: bool
    # Why it is off, for staff only: "Insolvent ×1".
    off_because: str = ""
    # An action it adds to each downtime's allowance.
    action_kind: str | None = None


@dataclass
class HeldLocation:
    location: Location
    effects: list[Effect]


def effective(location: Location, name: str, raised_by: str) -> int:
    """A negative's level, the first ignored where a quality does so (Sturdy, Public
    Property)."""
    level = level_of(location, name)
    return max(0, level - 1) if raised_by in quality_names(location) else level


def switched_off(location: Location, quality: str, kind: str) -> str:
    """The negative switching a quality off, if one does."""
    out_of_code = effective(location, "Out of Code", "Public Property")
    if out_of_code >= 3:
        return f"Out of Code ×{level_of(location, 'Out of Code')}"
    damaged = effective(location, "Damaged", "Sturdy")
    if damaged >= 3 and kind == "standard":
        return f"Damaged ×{level_of(location, 'Damaged')}"
    if damaged >= 1 and quality in location.damaged_off:
        return f"Damaged ×{level_of(location, 'Damaged')}"
    if quality == "Profitable" and level_of(location, "Insolvent") >= 1:
        return f"Insolvent ×{level_of(location, 'Insolvent')}"
    if quality in ("Artistic", "Fancy", "Lowdown and Dirty") and level_of(location, "Shunned") >= 1:
        return f"Shunned ×{level_of(location, 'Shunned')}"
    return ""


def effects_of(rules: LocationRules, location: Location) -> list[Effect]:
    found: list[Effect] = []

    def add(quality: str, gives: str, action_kind: str | None = None) -> None:
        known = rules.qualities.get(quality)
        why = switched_off(location, quality, known.kind if known else "standard")
        found.append(Effect(quality, gives, not why, why, action_kind))

    names = quality_names(location)
    if (profitable := names.count("Profitable")) > 0:
        add("Profitable", f"Resources {profitable}")
    for q in location.qualities:
        detail = f" ({q['detail']})" if q.get("detail") else ""
        if q["name"] == "Hangout":
            add("Hangout", f"Contacts 1{detail}")
        elif q["name"] == "Clubhouse":
            add("Clubhouse", f"Allies 1{detail}")
    if "Artistic" in names:
        add("Artistic", "Fame +1 while known to control it")
    if "Fancy" in names:
        add("Fancy", "+1 Elite influence action each downtime", "influence_elite")
    if "Lowdown and Dirty" in names:
        add(
            "Lowdown and Dirty",
            "+1 Underworld influence action each downtime",
            "influence_underworld",
        )
    shunned = level_of(location, "Shunned")
    if shunned == 2:
        found.append(Effect("Shunned", f"Fame −{location.rating}", True, "Shunned ×2"))
    elif shunned >= 3:
        found.append(
            Effect(
                "Shunned",
                "No Fame, and Influences can't be raised with XP, while it controls this",
                True,
                f"Shunned ×{shunned}",
            )
        )
    return found


def held(db: Session, character: Character) -> list[HeldLocation]:
    """The locations the character controls, alone or jointly, and what each gives it.
    Only the controller has a location's effects."""
    found: list[HeldLocation] = []
    rules_by_troupe: dict[uuid.UUID, LocationRules] = {}
    for location in locations.held_by(db, character.id):
        troupe = db.get(Troupe, location.troupe_id)
        if troupe is None or troupe.archived_at is not None:
            continue
        if troupe.id not in rules_by_troupe:
            rules_by_troupe[troupe.id] = locations.rules_for(db, troupe)
        effects = (
            effects_of(rules_by_troupe[troupe.id], location)
            if location.controller_id == character.id
            else []
        )
        found.append(HeldLocation(location, effects))
    return found


def allowance_lines(db: Session, character: Character, troupe_id: uuid.UUID) -> list[AllowanceLine]:
    """What the character's locations in the troupe add to a downtime's allowance:
    Fancy and Lowdown and Dirty, or why they don't."""
    lines: list[AllowanceLine] = []
    for h in held(db, character):
        if h.location.troupe_id != troupe_id:
            continue
        for e in h.effects:
            if e.action_kind is None:
                continue
            source = f"{h.location.name} ({e.quality})"
            if e.on:
                lines.append(AllowanceLine(e.action_kind, source, 1))
            else:
                lines.append(AllowanceLine(e.action_kind, source, 0, "Not available this cycle."))
    return lines
