"""A troupe's locations (CONTEXT.md: Location): the Stock Locations that matter in
its chronicle, and its characters' Havens placed on the list. Its storytellers and
assistant storytellers keep them; players never see the record (#326 shows a
controller the names of their locations, and what their qualities give them).

The rules (MET: VTM Vol. II Issue 1, pp. 117-133), as horatio.rules.locations has
them for the troupe:

- a location is standard, prestige or iconic, rated 1 to 5. A standard one has
  up to its rating in qualities, the others twice that; only an iconic one has
  iconic qualities, and none has more than one supernatural quality (p. 121);
- an Elysium has Elysium qualities: one, a second after a decade unviolated,
  then one more each century (p. 131);
- negative qualities go to ×3 (×4 for Damaged with Sturdy, Out of Code with
  Public Property), and staff may keep any of them secret (p. 127);
- a character controls up to five locations, and one more for each dot of
  Retainers (or Kinfolk) (p. 119). A Haven doesn't count (p. 117), nor, under the
  conglomerates house option, a parent whose every subsidiary the character
  controls. Going over is refused, or allowed and shown to staff, as the troupe
  sets it (`Troupe.location_limit`). Joint control counts for both controllers.

A change breaking a rule is refused with the reason. A quality a location already
has stays when the catalogue no longer offers it (an option switched off, a troupe
quality archived), and counts as a standard quality.

Every change goes in the troupe's audit log, naming the location, which is also
the location's own log. No event names a character, so none reaches a character's
log, which its player can read.
"""

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from horatio import audit
from horatio.influence_log import in_troupe
from horatio.models import AuditEvent, Character, Location, Troupe, TroupeLocationQuality, User
from horatio.rules import locations as catalogue
from horatio.rules.locations import (
    BASE_CONTROL,
    BOOK,
    CONTROL_BACKGROUNDS,
    LocationRules,
    Quality,
    Suggestion,
)
from horatio.sheets import conflict, sheet_rows, unprocessable

CONTROLS = ("character", "named", "none", "uncontrollable")
INFLUENCE_TYPES = ("elite", "underworld")
HAVEN = "Haven"


def suggestion_from(raw: dict[str, Any]) -> Suggestion:
    return catalogue.suggestion_from(raw, "suggestion")


def own_quality(row: TroupeLocationQuality) -> Quality:
    return Quality(
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        text=row.text,
        detail=row.detail,
        repeatable=row.repeatable,
        suggested=tuple(suggestion_from(s) for s in row.suggested),
        house=True,
    )


def own_qualities(db: Session, troupe_id: uuid.UUID) -> list[TroupeLocationQuality]:
    """The troupe's own qualities, archived ones too, by name."""
    return list(
        db.scalars(
            select(TroupeLocationQuality)
            .where(TroupeLocationQuality.troupe_id == troupe_id)
            .order_by(TroupeLocationQuality.name)
        )
    )


def rules_for(db: Session, troupe: Troupe) -> LocationRules:
    """The catalogue as the troupe plays it."""
    own = [own_quality(q) for q in own_qualities(db, troupe.id) if q.archived_at is None]
    return catalogue.played(catalogue.load_catalogue(), troupe.location_options_off, own)


def this_year() -> int:
    return datetime.now(UTC).year


def page(p: str | None) -> str:
    return f" ({BOOK}, p. {p})" if p else ""


# --- a location's fields ----------------------------------------------------------------


@dataclass
class QualityIn:
    name: str
    detail: str = ""


@dataclass
class NegativeIn:
    name: str
    level: int = 1
    secret: bool = False
    by: str = ""


@dataclass
class Draft:
    """Everything a location holds that staff set."""

    name: str
    kind: str = "standard"
    rating: int = 1
    parent_id: uuid.UUID | None = None
    qualities: list[QualityIn] = field(default_factory=list[QualityIn])
    negatives: list[NegativeIn] = field(default_factory=list[NegativeIn])
    control: str = "none"
    controller_id: uuid.UUID | None = None
    controller_name: str = ""
    joint_id: uuid.UUID | None = None
    joint_name: str = ""
    heir_id: uuid.UUID | None = None
    heir_name: str = ""
    influence_type: str | None = None
    influence_area: str = ""
    address: str = ""
    web_address: str = ""
    map_link: str = ""
    feeding_block: str = ""
    locked: bool = False
    haven_of_id: uuid.UUID | None = None
    haven_advantages: list[str] = field(default_factory=list[str])
    elysium_since: int | None = None
    notes: str = ""


SCALARS = (
    "name",
    "kind",
    "rating",
    "parent_id",
    "control",
    "controller_id",
    "controller_name",
    "joint_id",
    "joint_name",
    "heir_id",
    "heir_name",
    "influence_type",
    "influence_area",
    "address",
    "web_address",
    "map_link",
    "feeding_block",
    "locked",
    "haven_of_id",
    "elysium_since",
    "notes",
)


def draft_of(location: Location) -> Draft:
    return Draft(
        **{k: getattr(location, k) for k in SCALARS},
        qualities=[QualityIn(q["name"], q.get("detail", "")) for q in location.qualities],
        negatives=[
            NegativeIn(n["name"], n["level"], n.get("secret", False), n.get("by", ""))
            for n in location.negatives
        ],
        haven_advantages=list(location.haven_advantages),
    )


def tidy(text: str) -> str:
    return " ".join(text.split())


def tidied(draft: Draft) -> Draft:
    """The draft with its text trimmed, and what its control leaves out cleared."""
    draft.name = tidy(draft.name)
    for key in ("controller_name", "joint_name", "heir_name", "influence_area", "feeding_block"):
        setattr(draft, key, tidy(getattr(draft, key)))
    for key in ("address", "web_address", "map_link", "notes"):
        setattr(draft, key, getattr(draft, key).strip())
    draft.qualities = [QualityIn(tidy(q.name), tidy(q.detail)) for q in draft.qualities]
    draft.negatives = [
        NegativeIn(tidy(n.name), n.level, n.secret, tidy(n.by)) for n in draft.negatives
    ]
    if draft.control != "character":
        draft.controller_id = None
    if draft.control != "named":
        draft.controller_name = ""
    if draft.joint_id is not None:
        draft.joint_name = ""
    if draft.heir_id is not None:
        draft.heir_name = ""
    if draft.influence_type is None:
        draft.influence_area = ""
    if draft.haven_of_id is None:
        draft.haven_advantages = []
    return draft


# --- the rules on one location ----------------------------------------------------------


def most_qualities(rules: LocationRules, draft: Draft) -> int:
    return catalogue.most_qualities(rules, draft.kind, draft.rating)


def type_name(rules: LocationRules, draft: Draft) -> str:
    return f"{rules.types[draft.kind].name.lower()} {draft.rating}"


def counted_qualities(rules: LocationRules, draft: Draft) -> int:
    """Its qualities that count toward its limit: not Elysium qualities, nor one
    that says it doesn't count (Derelict). One no longer offered counts."""
    found = 0
    for q in draft.qualities:
        known = rules.qualities.get(q.name)
        if known is None or (known.counts and known.kind != "elysium"):
            found += 1
    return found


def quality_problem(rules: LocationRules, draft: Draft, had: set[str], year: int) -> str | None:
    """Why the location's qualities break the rules, if they do."""
    if draft.kind == "haven":
        if draft.qualities:
            return (
                "A haven has its Haven's advantages, not qualities: make it a standard, "
                "prestige or iconic location to give it qualities."
            )
        return None
    names = Counter(q.name for q in draft.qualities)
    limit = most_qualities(rules, draft)
    for q in draft.qualities:
        if not q.name:
            return "Choose a quality."
        known = rules.qualities.get(q.name)
        if known is None:
            if q.name in had:
                continue
            return f"{q.name} isn't a location quality in this troupe."
        if known.kind == "iconic" and draft.kind != "iconic":
            return f"{q.name} is an iconic quality: only an iconic location has one{page('121')}."
        if known.kind == "elysium" and draft.elysium_since is None:
            return f"{q.name} is an Elysium quality: only an Elysium has one{page('131')}."
        lowest = rules.min_rating.get(q.name)
        if lowest is not None and draft.rating < lowest:
            return (
                f"{q.name} needs a location rated {lowest} or higher "
                "(house option: Limits on qualities)."
            )
        for other in known.excludes:
            if other in names:
                return f"{q.name} can't be held with {other}{page(known.page)}."
        if q.name in rules.per_qualities:
            most = catalogue.most_of(rules, q.name, limit)
            if names[q.name] > most:
                return (
                    f"A location that can have {limit} qualities has {q.name} at most "
                    f"{times(most)}: one for each {rules.per_qualities[q.name]} "
                    "(house option: Limits on qualities)."
                )
        elif known.repeatable:
            same = [x for x in draft.qualities if x.name == q.name and x.detail == q.detail]
            if len(same) > 1:
                what = f" for {q.detail}" if q.detail else ""
                other = known.detail.lower() or "detail"
                return f"This location has {q.name}{what} twice: give each another {other}."
        elif names[q.name] > 1:
            return f"A location has {q.name} only once{page(known.page)}."
    supernatural = [q.name for q in draft.qualities if kind_of(rules, q.name) == "supernatural"]
    if len(supernatural) > 1:
        both = " and ".join(supernatural)
        return f"A location has one supernatural quality at most{page('125')}, not {both}."
    counted = counted_qualities(rules, draft)
    if counted > limit:
        return (
            f"A {type_name(rules, draft)} location has at most {limit} qualities{page('121')}; "
            f"this one would have {counted}."
        )
    if draft.elysium_since is not None:
        if draft.elysium_since > year:
            return "An Elysium can't be unviolated since a year still to come."
        allowed = catalogue.elysium_qualities(year - draft.elysium_since)
        held = sum(1 for q in draft.qualities if kind_of(rules, q.name) == "elysium")
        if held > allowed:
            return (
                f"An Elysium unviolated since {draft.elysium_since} has "
                f"{allowed} Elysium {'quality' if allowed == 1 else 'qualities'}: one, a second "
                f"after a decade, and one more each century{page('131')}."
            )
    return None


def kind_of(rules: LocationRules, name: str) -> str:
    known = rules.qualities.get(name)
    return known.kind if known else "standard"


def times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def negative_problem(rules: LocationRules, draft: Draft) -> str | None:
    seen: set[str] = set()
    names = {q.name for q in draft.qualities}
    for n in draft.negatives:
        known = rules.negatives.get(n.name)
        if known is None:
            return f"{n.name or 'That'} isn't a negative quality."
        if n.name in seen:
            return f"Give {n.name} once, at its level."
        seen.add(n.name)
        most = catalogue.most_negative(rules, n.name, names)
        if not 1 <= n.level <= most:
            raised = f" ({most} with {known.raised_by})" if most > 3 else ""
            return f"{n.name} goes from ×1 to ×{min(most, 3)}{raised}{page(known.page)}."
    return None


def control_problem(draft: Draft) -> str | None:
    if draft.control not in CONTROLS:
        return "Choose who controls it."
    if draft.control == "character" and draft.controller_id is None:
        return "Choose the character who controls it."
    if draft.control == "named" and not draft.controller_name:
        return "Give the name of whoever controls it."
    has_joint = draft.joint_id is not None or bool(draft.joint_name)
    if has_joint and draft.control not in ("character", "named"):
        return "Joint control needs someone in control to share it with."
    if draft.joint_id is not None and draft.joint_id == draft.controller_id:
        return "Joint control is shared with someone else."
    if draft.kind == "haven" and draft.control == "uncontrollable":
        return "A haven is its owner's: it can't be uncontrollable."
    return None


def haven_problem(rules: LocationRules, draft: Draft) -> str | None:
    if draft.kind == "haven" and draft.haven_of_id is None:
        return "Choose whose Haven it is."
    if draft.kind == "haven" and draft.elysium_since is not None:
        return "A haven can't be an Elysium: make it a Stock Location first."
    if len(set(draft.haven_advantages)) != len(draft.haven_advantages):
        return f"A Haven has each advantage once{page_core('102')}."
    for name in draft.haven_advantages:
        if name not in rules.haven_advantages:
            return f"{name} isn't a Haven advantage."
    return None


def page_core(p: str) -> str:
    return f" (MET: VTM, p. {p})"


def problem(rules: LocationRules, draft: Draft, had: set[str], year: int) -> str | None:
    """Why the draft breaks the rules, before looking at anyone's sheet."""
    if not draft.name:
        return "Give the location a name."
    if draft.kind not in rules.types:
        return "Choose standard, prestige, iconic or haven."
    if not 1 <= draft.rating <= 5:
        return f"A location is rated 1 to 5{page('118')}."
    if draft.influence_type is not None and draft.influence_type not in INFLUENCE_TYPES:
        return "Its influence area is Elite or Underworld."
    return (
        quality_problem(rules, draft, had, year)
        or negative_problem(rules, draft)
        or control_problem(draft)
        or haven_problem(rules, draft)
    )


# --- control ------------------------------------------------------------------------------


def rating_of(db: Session, character: Character, category: str, name: str) -> int:
    """Every dot of `name` on the sheet, across its instances (each Retainer)."""
    return sum(
        r.trait.rating or 0
        for r in sheet_rows(db, character)
        if r.category.key == category and r.definition.name == name
    )


def control_limit(db: Session, character: Character) -> tuple[int, str]:
    """How many locations the character can control, and why: five, and one for each
    dot of Retainers or Kinfolk (p. 119)."""
    extra = {n: rating_of(db, character, "backgrounds", n) for n in CONTROL_BACKGROUNDS}
    held = [f"{n} {r}" for n, r in extra.items() if r]
    why = f"{BASE_CONTROL}, and one for each dot of Retainers" + (
        f" ({', '.join(held)})" if held else ""
    )
    return BASE_CONTROL + sum(extra.values()), why


def held_by(db: Session, character_id: uuid.UUID) -> list[Location]:
    """The locations the character controls, alone or jointly, in every troupe."""
    return list(
        db.scalars(
            select(Location)
            .where(or_(Location.controller_id == character_id, Location.joint_id == character_id))
            .order_by(Location.name)
        )
    )


def subsidiaries(db: Session, location: Location) -> list[Location]:
    query = select(Location).where(Location.parent_id == location.id)
    return list(db.scalars(query.order_by(Location.name)))


def options_off(db: Session, troupe_id: uuid.UUID) -> list[str]:
    return db.get_one(Troupe, troupe_id).location_options_off


def not_counted(db: Session, location: Location, character_id: uuid.UUID) -> str | None:
    """Why the location doesn't count toward the character's control limit, if it
    doesn't: a Haven (p. 117), or a conglomerate whose every subsidiary it controls."""
    if location.kind == "haven" or location.haven_of_id is not None:
        return "a Haven"
    if "conglomerates" in options_off(db, location.troupe_id):
        return None
    under = subsidiaries(db, location)
    if under and all(character_id in (s.controller_id, s.joint_id) for s in under):
        return "a conglomerate whose every subsidiary it controls"
    return None


@dataclass
class Held:
    location: Location
    # Why it isn't counted toward the limit; None when it is.
    not_counted: str | None


@dataclass
class Standing:
    held: list[Held]
    limit: int
    why: str

    @property
    def controls(self) -> int:
        return sum(1 for h in self.held if h.not_counted is None)

    @property
    def over(self) -> bool:
        return self.controls > self.limit


def standing(db: Session, character: Character) -> Standing:
    limit, why = control_limit(db, character)
    held = [Held(loc, not_counted(db, loc, character.id)) for loc in held_by(db, character.id)]
    return Standing(held, limit, why)


def over_limit(db: Session, character: Character) -> str | None:
    found = standing(db, character)
    if not found.over:
        return None
    return (
        f"{character.name} would control {found.controls} locations, over the {found.limit} "
        f"they can: {found.why}{page(catalogue.load_catalogue().pages.get('control_page'))}."
    )


# --- checks against the troupe and its characters -----------------------------------------


def checked_character(
    db: Session, troupe: Troupe, character_id: uuid.UUID | None, was: uuid.UUID | None, role: str
) -> Character | None:
    """The character named for `role`, which must be in the troupe; one already named
    stays, even if it has since left."""
    if character_id is None:
        return None
    character = db.get(Character, character_id)
    if character is None or (character_id != was and not in_troupe(db, troupe.id, character)):
        raise unprocessable(f"The {role} must be a character in the troupe.")
    return character


def checked_parent(
    db: Session, rules: LocationRules, troupe: Troupe, location: Location | None, draft: Draft
) -> None:
    if draft.parent_id is None:
        return
    was = location.parent_id if location else None
    if draft.parent_id != was and not rules.on("conglomerates"):
        raise unprocessable("Conglomerates are switched off in this troupe's house rules.")
    parent = db.get(Location, draft.parent_id)
    if parent is None or parent.troupe_id != troupe.id:
        raise unprocessable("Its conglomerate must be one of the troupe's locations.")
    seen: set[uuid.UUID] = set()
    while parent is not None:
        if location is not None and parent.id == location.id:
            raise unprocessable("A location can't be a subsidiary of itself, even in a ring.")
        if parent.id in seen:
            break
        seen.add(parent.id)
        parent = db.get(Location, parent.parent_id) if parent.parent_id else None


def checked_haven(db: Session, rules: LocationRules, owner: Character | None, draft: Draft) -> None:
    if owner is None:
        return
    dots = rating_of(db, owner, "backgrounds", HAVEN)
    if dots < 1:
        raise unprocessable(f"{owner.name} has no Haven background.")
    if len(draft.haven_advantages) > dots:
        raise unprocessable(
            f"{owner.name} has Haven {dots}: one advantage for each dot{page_core('102')}."
        )
    for name in draft.haven_advantages:
        needs = rules.haven_advantages[name].needs
        if needs and rating_of(db, owner, "skills", needs) < 1:
            raise unprocessable(f"The {name} advantage needs the {needs} skill{page_core('102')}.")


def name_taken(db: Session, troupe: Troupe, name: str, keep: Location | None) -> None:
    clash = db.scalar(
        select(Location.id).where(Location.troupe_id == troupe.id, Location.name == name)
    )
    if clash is not None and (keep is None or clash != keep.id):
        raise conflict(f"The troupe already has a location called {name}.")


# --- saving ---------------------------------------------------------------------------------


def apply(location: Location, draft: Draft) -> None:
    for key in SCALARS:
        setattr(location, key, getattr(draft, key))
    location.qualities = [{"name": q.name, "detail": q.detail} for q in draft.qualities]
    location.negatives = [
        {"name": n.name, "level": n.level, "secret": n.secret, "by": n.by} for n in draft.negatives
    ]
    location.haven_advantages = list(draft.haven_advantages)


def counted_for(db: Session, location: Location) -> set[uuid.UUID]:
    """The characters the location counts toward the control limit of."""
    return {
        c
        for c in (location.controller_id, location.joint_id)
        if c is not None and not_counted(db, location, c) is None
    }


def save(
    db: Session, actor: User, troupe: Troupe, location: Location | None, draft: Draft
) -> tuple[Location, list[str]]:
    """Add or change a location, refusing what breaks the rules. Returns it, and
    what staff should know: a control limit gone over where the troupe only notes it."""
    draft = tidied(draft)
    rules = rules_for(db, troupe)
    before = draft_of(location) if location is not None else None
    had = {q.name for q in before.qualities} if before else set[str]()
    if reason := problem(rules, draft, had, this_year()):
        raise unprocessable(reason)
    name_taken(db, troupe, draft.name, location)
    checked_parent(db, rules, troupe, location, draft)
    roles = {
        "controller": ("controller_id", "controller"),
        "joint": ("joint_id", "joint controller"),
        "heir": ("heir_id", "heir"),
        "haven": ("haven_of_id", "Haven's owner"),
    }
    people = {
        key: checked_character(
            db, troupe, getattr(draft, attr), getattr(before, attr) if before else None, role
        )
        for key, (attr, role) in roles.items()
    }
    if (
        before is None
        or draft.haven_advantages != before.haven_advantages
        or (draft.haven_of_id != before.haven_of_id)
    ):
        checked_haven(db, rules, people["haven"], draft)

    counted_before = counted_for(db, location) if location is not None else set[uuid.UUID]()
    # The limit is counted with the change made; refusing it undoes the change.
    savepoint = db.begin_nested()
    if location is None:
        location = Location(troupe_id=troupe.id, created_by=actor.id, name=draft.name)
        db.add(location)
    apply(location, draft)
    db.flush()
    warnings: list[str] = []
    for character_id in counted_for(db, location) - counted_before:
        character = db.get_one(Character, character_id)
        if (over := over_limit(db, character)) is None:
            continue
        if troupe.location_limit == "refuse":
            savepoint.rollback()
            raise conflict(over)
        warnings.append(over)
    savepoint.commit()

    if before is None:
        audit.record(db, actor, "location.added", troupe_id=troupe.id, **describe(location))
    elif changes := changed(db, before, draft):
        audit.record(
            db,
            actor,
            "location.changed",
            troupe_id=troupe.id,
            fields="; ".join(changes),
            **describe(location),
        )
    for warning in warnings:
        audit.record(
            db, actor, "location.over_limit", troupe_id=troupe.id, why=warning, **describe(location)
        )
    return location, warnings


def describe(location: Location) -> dict[str, Any]:
    """What the audit log says about it: also how its own log finds it."""
    return {"location": location.name, "location_id": str(location.id)}


def remove(db: Session, actor: User, location: Location) -> None:
    for child in subsidiaries(db, location):
        child.parent_id = None
    audit.record(db, actor, "location.removed", troupe_id=location.troupe_id, **describe(location))
    db.delete(location)


# --- its log ----------------------------------------------------------------------------------


LABELS = {
    "name": "name",
    "kind": "type",
    "rating": "rating",
    "parent_id": "conglomerate",
    "control": "control",
    "controller_id": "controller",
    "controller_name": "controller",
    "joint_id": "joint control",
    "joint_name": "joint control",
    "heir_id": "heir",
    "heir_name": "heir",
    "influence_type": "influence area",
    "influence_area": "influence area",
    "address": "address",
    "web_address": "web address",
    "map_link": "map link",
    "feeding_block": "feeding block",
    "locked": "locked",
    "haven_of_id": "Haven",
    "elysium_since": "Elysium",
    "notes": "notes",
}


def who(db: Session, character_id: uuid.UUID | None, name: str) -> str:
    if character_id is not None:
        character = db.get(Character, character_id)
        return character.name if character else "someone"
    return name or "nobody"


def quality_text(q: QualityIn) -> str:
    return f"{q.name} ({q.detail})" if q.detail else q.name


def negative_text(n: NegativeIn) -> str:
    return f"{n.name} ×{n.level}{', secret' if n.secret else ''}{f' ({n.by})' if n.by else ''}"


def listed_change(label: str, was: list[str], now: list[str]) -> str | None:
    added = Counter(now) - Counter(was)
    gone = Counter(was) - Counter(now)
    if not added and not gone:
        return None
    parts = [f"+{x}" for x in added.elements()] + [f"−{x}" for x in gone.elements()]
    return f"{label} {', '.join(parts)}"


def changed(db: Session, before: Draft, after: Draft) -> list[str]:
    """What a change did, in a few words each, for the log."""
    found: list[str] = []
    labels: list[str] = []
    for key in SCALARS:
        if getattr(before, key) != getattr(after, key) and LABELS[key] not in labels:
            labels.append(LABELS[key])
    for label in labels:
        if label in ("controller", "control"):
            found.append(f"controller {who(db, after.controller_id, after.controller_name)}")
        elif label == "joint control":
            found.append(f"joint control {who(db, after.joint_id, after.joint_name)}")
        elif label == "heir":
            found.append(f"heir {who(db, after.heir_id, after.heir_name)}")
        elif label == "locked":
            found.append("locked" if after.locked else "unlocked")
        elif label in ("type", "rating"):
            if f"type {after.kind} {after.rating}" not in found:
                found.append(f"type {after.kind} {after.rating}")
        else:
            found.append(label)
    found = list(dict.fromkeys(found))
    for item in (
        listed_change(
            "qualities",
            [quality_text(q) for q in before.qualities],
            [quality_text(q) for q in after.qualities],
        ),
        listed_change(
            "negatives",
            [negative_text(n) for n in before.negatives],
            [negative_text(n) for n in after.negatives],
        ),
        listed_change("advantages", before.haven_advantages, after.haven_advantages),
    ):
        if item:
            found.append(item)
    return found


def log_query(location: Location) -> Any:
    return select(AuditEvent).where(
        AuditEvent.troupe_id == location.troupe_id,
        AuditEvent.data["location_id"].astext == str(location.id),
    )


# --- the troupe's own qualities -----------------------------------------------------------


def checked_quality_name(
    db: Session, troupe: Troupe, name: str, keep: TroupeLocationQuality | None
) -> str:
    name = tidy(name)
    if not name:
        raise unprocessable("Give the quality a name.")
    book = {q.name for q in catalogue.load_catalogue().qualities}
    if name in book:
        raise conflict(f"{name} is already a location quality.")
    clash = db.scalar(
        select(TroupeLocationQuality.id).where(
            TroupeLocationQuality.troupe_id == troupe.id, TroupeLocationQuality.name == name
        )
    )
    if clash is not None and (keep is None or clash != keep.id):
        raise conflict(f"The troupe already has a location quality called {name}.")
    return name


def rename_quality(db: Session, troupe: Troupe, old: str, new: str) -> None:
    """Keep the troupe's locations holding a quality it renamed."""
    for location in db.scalars(select(Location).where(Location.troupe_id == troupe.id)):
        if any(q["name"] == old for q in location.qualities):
            location.qualities = [
                {**q, "name": new} if q["name"] == old else q for q in location.qualities
            ]


def holders(db: Session, troupe: Troupe, name: str) -> Sequence[Location]:
    return [
        loc
        for loc in db.scalars(select(Location).where(Location.troupe_id == troupe.id))
        if any(q["name"] == name for q in loc.qualities)
    ]
