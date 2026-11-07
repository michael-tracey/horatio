"""Downtime keywords (#509): what kind of action an answer is, chosen first.

A player answering an action question first chooses its **keyword**: Feed, Patrol,
Investigate, Learn, Narrative and so on. The keyword decides what else the answer asks
for (its fields), which action kinds it can be spent from, what it costs, where staff
resolve it in the troupe's resolution order, and what follows from it on its own. It is
kept in the answer's `structured`, as `keyword`, with its fields beside it. An answer
with no keyword, as every answer from before keywords, counts as Narrative.

**The defaults** follow the book where it has a rule (MET: VTM pp. 93, 97, 111-113,
307-308) and the troupes' downtime primers for the rest. A troupe changes them as house
rules: renames, rewords, reorders, adds its own, or retires one. Retiring keeps it on
past downtimes. Its first change writes the whole list for the troupe
(`DowntimeKeyword`), so its rows are the list; a default that is new since joins the
end.

**What follows** from a default keyword, which it keeps when a troupe renames it:

- **Feed** answers are the character's feeding actions in the Feeding section
  (horatio.feeding stays the one source of truth). A Feed in a feeding territory stands
  in for one without spending an action, once a cycle, as the territories rule has it.
- **Patrol** answers are its patrols of the territories it holds.
- **Learn** answers stand for the actions learning owes (horatio.downtimes.owe_actions):
  each is offered ready-made, and confirming one costs nothing more, as the owed action
  is already off the allowance.
- **Observe** and **Cancel** are Computer's Cancel and Observe (horatio.targets), from
  the one action a cycle the skill gives.
- **Quest** is the form's Quest action (horatio.quest_actions), never chosen on another
  question.

Influence answers take no keyword: their influence action says what they are, and
places them in the resolution order.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, influence, social_age
from horatio.models import (
    Answer,
    Character,
    DowntimeKeyword,
    OwedAction,
    Question,
    Troupe,
    User,
)
from horatio.sheets import conflict, unprocessable

KEY = "keyword"
# What a keyword can ask for besides the description, and where each is kept in
# `structured`. A character is one the action is aimed at (horatio.targets); a target
# is a character, or something else in words.
FIELDS: dict[str, str] = {
    "character": "One character it is aimed at",
    "target": "Who or what it is aimed at: a character, or something else in words",
    "territory": "A feeding territory",
    "trait": "What to learn",
    "teacher": "The teacher, if any",
    "item": "The item wanted",
}
SUBJECT = "subject"
TERRITORY = "territory"
LEARN = "learn"
TEACHER = "teacher"
ITEM = "item"
OWED = "owed_action_id"
# Keys of `structured` that belong to a keyword's fields, dropped when it no longer
# asks for them.
FIELD_KEYS: dict[str, tuple[str, ...]] = {
    "target": (SUBJECT,),
    "territory": (TERRITORY,),
    "trait": (LEARN, OWED),
    "teacher": (TEACHER,),
    "item": (ITEM,),
}

# The resolution order, after Land of the Sky's: influence first, then Computer's
# Cancels, the other actions, and Computer's Observes last.
STEPS: dict[int, str] = {
    1: "Influence Defends, Blocks, Boosts and Attacks",
    2: "Indirect influence attacks",
    3: "Other influence actions, highest first, Word on the Street last",
    4: "Cancels",
    5: "Downtime actions, in the order staff choose",
    6: "Observes",
}
NORMAL_STEP = 5
LAST_LOOKUP = "word_on_the_street"

NARRATIVE = "narrative"
QUEST = "quest"
FEED = "feed"
PATROL = "patrol"
LEARN_KEY = "learn"
OBSERVE = "observe"
CANCEL = "cancel"
BEYOND = "beyond_your_means"
CRAFT = "craft"
PERFORM = "perform"
# Owed actions that a Learn action stands for: learning a dot, or gaining a merit.
LEARNING_REASONS = ("Learning ", "Gaining ")


@dataclass(frozen=True)
class Keyword:
    key: str
    name: str
    explanation: str
    fields: tuple[str, ...] = ()
    action_kinds: tuple[str, ...] = ("general",)
    computers_only: bool = False
    science: bool = False
    cost: int = 1
    required_for: tuple[str, ...] = ()
    step: int = NORMAL_STEP
    position: int = 0
    retired: bool = False

    @property
    def effect(self) -> str | None:
        """What follows from it on its own: its default's key, or None for the troupe's own."""
        return self.key if self.key in DEFAULT_KEYS else None

    def asks(self, field_key: str) -> bool:
        return field_key in self.fields


DEFAULTS: tuple[Keyword, ...] = tuple(
    replace(k, position=n)
    for n, k in enumerate(
        (
            Keyword(
                FEED,
                "Feed",
                "Hunt for Blood between games. Each Feed action is a feeding action; feeding in"
                " a territory stands in for one without spending one.",
                fields=("territory",),
            ),
            Keyword(
                PATROL,
                "Patrol",
                "Watch a feeding territory your character holds for poachers. It makes feeding"
                " there harder for others, but doesn't say who fed.",
                fields=("territory",),
            ),
            Keyword(
                "investigate",
                "Investigate",
                "Find something out about a character, a territory, a plot or a quest, or"
                " uncover someone's other identity. Say who or what, and how.",
                fields=("target",),
                science=True,
            ),
            Keyword(
                BEYOND,
                "Beyond Your Means",
                "Get hold of one item, with one quality, that your Resources don't run to.",
                fields=("item",),
            ),
            Keyword(
                QUEST,
                "Quest",
                "Work toward a quest your character already has, in the form's Quest action.",
                action_kinds=(),
            ),
            Keyword(
                LEARN_KEY,
                "Learn",
                "Learn a discipline dot, a technique or an elder power. What you have bought"
                " shows ready-made: confirm it.",
                fields=("trait", "teacher"),
            ),
            Keyword(
                CRAFT,
                "Craft",
                "Make something with Crafts. Say what and how. Two Craft actions can raise"
                " Resources by one for the month.",
                science=True,
            ),
            Keyword(
                PERFORM,
                "Perform",
                "Perform with Performance. Say what and how. Two Perform actions can raise"
                " Fame by one for the month.",
            ),
            Keyword(
                NARRATIVE,
                "Narrative",
                "Anything else: dealing with an NPC, a ritual, and so on.",
                science=True,
            ),
            Keyword(
                "rhetorical",
                "Rhetorical",
                "Colour for your character, with no effect on the game. Staff may only skim it.",
            ),
            Keyword(
                OBSERVE,
                "Observe",
                "With the Computer skill: staff tell you of one of a character's actions."
                " They never learn of it.",
                fields=("character",),
                computers_only=True,
                step=6,
            ),
            Keyword(
                CANCEL,
                "Cancel",
                "With the Computer skill: staff don't resolve one of a character's actions."
                " They learn it was cancelled, but not by whom.",
                fields=("character",),
                computers_only=True,
                step=4,
            ),
        )
    )
)
DEFAULT_KEYS = {k.key for k in DEFAULTS}
DEFAULT_BY_KEY = {k.key: k for k in DEFAULTS}


# --- the troupe's list --------------------------------------------------------------------


def from_row(row: DowntimeKeyword) -> Keyword:
    return Keyword(
        key=row.key,
        name=row.name,
        explanation=row.explanation,
        fields=tuple(row.fields),
        action_kinds=tuple(row.action_kinds),
        computers_only=row.computers_only,
        science=row.science,
        cost=row.cost,
        required_for=tuple(row.required_for),
        step=row.step,
        position=row.position,
        retired=row.retired_at is not None,
    )


def rows(db: Session, troupe_id: uuid.UUID) -> list[DowntimeKeyword]:
    return list(
        db.scalars(
            select(DowntimeKeyword)
            .where(DowntimeKeyword.troupe_id == troupe_id)
            .order_by(DowntimeKeyword.position, DowntimeKeyword.id)
        )
    )


def troupe_keywords(db: Session, troupe_id: uuid.UUID) -> list[Keyword]:
    """Every keyword the troupe has, retired ones too, in its order."""
    found = [from_row(r) for r in rows(db, troupe_id)]
    if not found:
        return list(DEFAULTS)
    have = {k.key for k in found}
    last = max(k.position for k in found)
    found += [
        replace(k, position=last + 1 + n) for n, k in enumerate(DEFAULTS) if k.key not in have
    ]
    return found


def by_key(keywords: Iterable[Keyword]) -> dict[str, Keyword]:
    return {k.key: k for k in keywords}


def keyword_of(structured: Mapping[str, Any]) -> str | None:
    value = structured.get(KEY)
    return value if isinstance(value, str) and value else None


# --- what a character is offered --------------------------------------------------------


@dataclass(frozen=True)
class Context:
    """What decides which keywords a character is offered in a cycle."""

    # It has the Computer skill (horatio.targets).
    computer: bool = False
    # Its feeding goes through feeding actions: tracked, without the Rack, and it feeds.
    feeds: bool = False
    # Feeding territories are played, so Feed and Patrol name one.
    territories: bool = False
    # Its social age, for keywords required each cycle.
    age: str = ""


def context(db: Session, character: Character, troupe: Troupe, feeds: bool) -> Context:
    from horatio import targets, territories

    return Context(
        computer=targets.has_computer(db, character),
        feeds=feeds,
        territories=territories.on(troupe),
        age=social_age.standings(db, [character.id])[character.id].age,
    )


def fits(keyword: Keyword, question: Question, ctx: Context) -> bool:
    """Whether the keyword can be chosen for an answer to the question, now."""
    if keyword.retired or question.kind != "action":
        return False
    if (question.action_kind or "") not in keyword.action_kinds:
        return False
    if keyword.computers_only and not ctx.computer:
        return False
    if keyword.effect == FEED and not ctx.feeds:
        return False
    if keyword.effect == PATROL and not ctx.territories:
        return False
    return keyword.effect != QUEST


def offered(keywords: Sequence[Keyword], question: Question, ctx: Context) -> list[Keyword]:
    return [k for k in keywords if fits(k, question, ctx)]


def takes_keywords(keywords: Sequence[Keyword], question: Question) -> bool:
    """Whether answers to the question are given a keyword at all: an action question
    of a kind some keyword is spent from. Influence answers aren't."""
    return question.kind == "action" and any(
        (question.action_kind or "") in k.action_kinds for k in keywords if not k.retired
    )


def asked_fields(keyword: Keyword, ctx: Context) -> tuple[str, ...]:
    """The keyword's fields as the character is asked them: a territory only while
    territories are played."""
    return tuple(f for f in keyword.fields if f != "territory" or ctx.territories)


# --- an answer ----------------------------------------------------------------------------


def text(structured: Mapping[str, Any], key: str) -> str:
    value = structured.get(key)
    return value.strip() if isinstance(value, str) else ""


def learning_owed(db: Session, participant_id: uuid.UUID) -> list[OwedAction]:
    """The actions learning owes that came off this participation, which Learn actions
    stand for."""
    return [
        o
        for o in db.scalars(
            select(OwedAction)
            .where(OwedAction.participant_id == participant_id, OwedAction.action_kind == "general")
            .order_by(OwedAction.id)
        )
        if o.play_event_id is None and o.reason.startswith(LEARNING_REASONS)
    ]


def learning_text(reason: str) -> tuple[str, str]:
    """What an owed action learns, and from whom: "Learning Celerity 2 from Mira (...)"
    is ("Celerity 2", "Mira")."""
    what = reason.split(" (", 1)[0]
    for prefix in LEARNING_REASONS:
        if what.startswith(prefix):
            what = what[len(prefix) :]
            break
    what, _, teacher = what.partition(" from ")
    return what.strip(), teacher.strip()


@dataclass
class Checked:
    """What `check_answer` found, for the allowance and the Feeding section."""

    keyword: Keyword | None
    # Actions it costs before a Haven's Location doubles it.
    cost: int = 1


def check_answer(
    db: Session,
    keywords: Mapping[str, Keyword],
    ctx: Context,
    question: Question,
    structured: Mapping[str, Any],
    before: Answer | None,
    owed: Mapping[uuid.UUID, OwedAction],
) -> tuple[dict[str, Any], Checked]:
    """An answer's `structured` with its keyword and fields as they are kept. The keyword
    must be one offered to the question, or the one it had before (a keyword retired
    since stays). Fields the keyword doesn't ask for are dropped; what it does ask for
    is checked when it is given, and needed only on submitting (`missing`)."""
    from horatio import targets

    kept = dict(structured)
    key = keyword_of(kept)
    if key is None:
        kept.pop(KEY, None)
        for keys in FIELD_KEYS.values():
            for k in keys:
                kept.pop(k, None)
        return kept, Checked(None)
    keyword = keywords.get(key)
    had = keyword_of(before.structured) if before is not None else None
    if keyword is None or (not fits(keyword, question, ctx) and had != key):
        raise unprocessable(f"{question.prompt!r}: choose one of the keywords offered.")
    asked = set(asked_fields(keyword, ctx)) | set(keyword.fields if had == key else ())
    for name, keys in FIELD_KEYS.items():
        if name not in asked:
            for k in keys:
                kept.pop(k, None)
    for k in (SUBJECT, LEARN, TEACHER, ITEM):
        if k in kept:
            if not isinstance(kept[k], str) or len(kept[k]) > 500:
                raise unprocessable(f"{question.prompt!r}: {k} is a line of text.")
            kept[k] = kept[k].strip()
            if not kept[k]:
                del kept[k]
    if TERRITORY in kept:
        try:
            uuid.UUID(str(kept[TERRITORY]))
        except ValueError:
            raise unprocessable(f"{question.prompt!r}: choose a feeding territory.") from None
        kept[TERRITORY] = str(kept[TERRITORY])
    if keyword.asks("character") and len(targets.aimed_at(kept)) > 1:
        raise unprocessable(f"{question.prompt!r}: {keyword.name} is aimed at one character.")
    # Computer's Cancel and Observe are marked by their keyword, once it is aimed.
    if keyword.effect in (OBSERVE, CANCEL) and len(targets.aimed_at(kept)) == 1:
        kept[targets.COUNTER] = keyword.effect
    else:
        kept.pop(targets.COUNTER, None)
    cost = keyword.cost
    if OWED in kept:
        try:
            owed_id = uuid.UUID(str(kept[OWED]))
        except ValueError:
            owed_id = None
        if owed_id is None or owed_id not in owed or keyword.effect != LEARN_KEY:
            raise unprocessable(f"{question.prompt!r}: that isn't something you're learning.")
        kept[OWED] = str(owed_id)
        # The owed action is already off the allowance.
        cost = 0
    if keyword.effect == FEED and TERRITORY in kept:
        # Feeding in a territory stands in for a feeding action without spending one.
        cost = 0
    kept[KEY] = key
    return kept, Checked(keyword, cost)


def missing(keyword: Keyword, structured: Mapping[str, Any], ctx: Context) -> list[str]:
    """What the keyword asks for that the answer doesn't give yet, in words."""
    from horatio import targets

    aimed = targets.aimed_at(structured)
    gaps: list[str] = []
    for name in asked_fields(keyword, ctx):
        if name == "character" and len(aimed) != 1:
            gaps.append("who it is aimed at")
        elif name == "target" and not aimed and not text(structured, SUBJECT):
            gaps.append("who or what it is aimed at")
        elif name == "territory" and keyword.effect == PATROL and not structured.get(TERRITORY):
            gaps.append("which territory")
        elif name == "trait" and not text(structured, LEARN):
            gaps.append("what to learn")
        elif name == "item" and not text(structured, ITEM):
            gaps.append("the item wanted")
    return gaps


def required_now(keywords: Sequence[Keyword], ctx: Context) -> list[Keyword]:
    """The keywords this character must take each cycle, by its social age."""
    return [k for k in keywords if not k.retired and ctx.age and ctx.age in k.required_for]


def details(db: Session, structured: Mapping[str, Any]) -> list[str]:
    """What the answer's keyword fields say, in words, for staff: never who it is aimed
    at, which only some staff see (horatio.targets)."""
    from horatio.models import FeedingTerritory

    found: list[str] = []
    territory = structured.get(TERRITORY)
    if territory:
        try:
            row = db.get(FeedingTerritory, uuid.UUID(str(territory)))
        except ValueError:
            row = None
        found.append(f"Territory: {row.name if row else 'one no longer listed'}")
    for key, label in (
        (SUBJECT, "About"),
        (LEARN, "Learning"),
        (TEACHER, "Teacher"),
        (ITEM, "Wanted"),
    ):
        if text(structured, key):
            found.append(f"{label}: {text(structured, key)}")
    if structured.get(OWED):
        found.append("Already taken from the allowance, as learning owes")
    return found


# --- what follows: feeding ----------------------------------------------------------------


@dataclass
class Fed:
    """The Feeding section's actions, territory and patrols, as Feed and Patrol answers
    give them; None for a part no answer gives, which the section keeps."""

    actions: int | None = None
    territory: str | None = None
    patrols: dict[uuid.UUID, int] | None = None


def feeding_from(answers: Sequence[tuple[Keyword | None, Mapping[str, Any]]]) -> Fed:
    feeds = [s for k, s in answers if k is not None and k.effect == FEED]
    fed = Fed()
    if feeds:
        in_territory = [s for s in feeds if s.get(TERRITORY)]
        if len(in_territory) > 1:
            raise unprocessable(
                "A character feeds in a territory once a cycle (Vol. 2, p. 305): choose one."
            )
        fed.actions = len(feeds) - len(in_territory)
        fed.territory = str(in_territory[0][TERRITORY]) if in_territory else ""
    patrols = [s for k, s in answers if k is not None and k.effect == PATROL and s.get(TERRITORY)]
    if patrols:
        fed.patrols = {}
        for s in patrols:
            territory = uuid.UUID(str(s[TERRITORY]))
            fed.patrols[territory] = fed.patrols.get(territory, 0) + 1
    return fed


# --- the resolution order ---------------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    """Where an answer comes in the resolution order, and what to call its kind."""

    step: int
    # Sorts it within its step.
    rank: tuple[int, ...]
    # Its keyword's name, or what stands in for one: Narrative for an action with
    # none, the action kind for influence, Quest, or Question for a custom question.
    label: str
    key: str | None


def place(
    keywords: Mapping[str, Keyword],
    question: Question,
    structured: Mapping[str, Any],
    kinds: Mapping[str, str],
    influence_action: influence.InfluenceAction | None = None,
) -> Placed:
    """`influence_action`: an influence answer's named action, as the troupe's rules
    have it."""
    if question.kind == "quest":
        quest = keywords.get(QUEST)
        return Placed(
            quest.step if quest else NORMAL_STEP,
            (quest.position if quest else 0,),
            quest.name if quest else "Quest",
            QUEST,
        )
    if question.kind == "custom":
        return Placed(NORMAL_STEP, (10_000,), "Question", None)
    key = keyword_of(structured)
    if key is None and influence.type_of(question.action_kind) is not None:
        label = kinds.get(question.action_kind or "", "Influence action")
        if influence_action is not None and influence_action.conflict:
            return Placed(1, (0,), label, None)
        level = influence_action.level if influence_action is not None else None
        last = influence_action is not None and influence_action.key == LAST_LOOKUP
        return Placed(3, (int(last), -(level or 0)), label, None)
    keyword = keywords.get(key or NARRATIVE)
    if keyword is None:
        return Placed(NORMAL_STEP, (9_999,), "Narrative", key)
    return Placed(keyword.step, (keyword.position,), keyword.name, keyword.key)


# --- the troupe's house rules -----------------------------------------------------------


@dataclass
class Change:
    """A keyword as a storyteller sets it."""

    name: str
    explanation: str = ""
    fields: list[str] = field(default_factory=list[str])
    action_kinds: list[str] = field(default_factory=lambda: ["general"])
    computers_only: bool = False
    science: bool = False
    cost: int = 1
    required_for: list[str] = field(default_factory=list[str])
    step: int = NORMAL_STEP


def check_change(change: Change, action_kinds: Mapping[str, str]) -> None:
    if not change.name.strip():
        raise unprocessable("A keyword needs a name.")
    unknown = [f for f in change.fields if f not in FIELDS]
    if unknown:
        raise unprocessable(f"No field {unknown[0]!r}.")
    if "character" in change.fields and "target" in change.fields:
        raise unprocessable("Ask for one character, or for a target, not both.")
    kinds = [k for k in change.action_kinds if k not in action_kinds]
    if kinds:
        raise unprocessable(f"No action kind {kinds[0]!r} in this troupe's rules.")
    if change.cost < 0 or change.cost > 5:
        raise unprocessable("A keyword costs 0 to 5 actions.")
    if change.step not in STEPS:
        raise unprocessable("Choose a step of the resolution order.")
    ages = [a for a in change.required_for if a not in social_age.AGES]
    if ages:
        raise unprocessable(f"No social age {ages[0]!r}.")


def materialise(db: Session, troupe_id: uuid.UUID) -> list[DowntimeKeyword]:
    """The troupe's rows, written from the list it plays the first time it changes it."""
    found = rows(db, troupe_id)
    have = {r.key for r in found}
    for keyword in troupe_keywords(db, troupe_id):
        if keyword.key in have:
            continue
        row = DowntimeKeyword(
            troupe_id=troupe_id,
            key=keyword.key,
            position=keyword.position,
            name=keyword.name,
            explanation=keyword.explanation,
            fields=list(keyword.fields),
            action_kinds=list(keyword.action_kinds),
            computers_only=keyword.computers_only,
            science=keyword.science,
            cost=keyword.cost,
            required_for=list(keyword.required_for),
            step=keyword.step,
        )
        db.add(row)
        found.append(row)
    db.flush()
    return sorted(found, key=lambda r: (r.position, r.key))


def row_for(db: Session, troupe_id: uuid.UUID, key: str) -> DowntimeKeyword:
    found = next((r for r in materialise(db, troupe_id) if r.key == key), None)
    if found is None:
        raise unprocessable(f"No keyword {key!r} in this troupe.")
    return found


def apply(row: DowntimeKeyword, change: Change) -> None:
    row.name = change.name.strip()
    row.explanation = change.explanation.strip()
    row.fields = list(dict.fromkeys(change.fields))
    row.action_kinds = list(dict.fromkeys(change.action_kinds))
    row.computers_only = change.computers_only
    row.science = change.science
    row.cost = change.cost
    row.required_for = [a for a in social_age.AGES if a in change.required_for]
    row.step = change.step


def change(
    db: Session,
    staff: User,
    troupe: Troupe,
    key: str,
    new: Change,
    action_kinds: Mapping[str, str],
) -> DowntimeKeyword:
    check_change(new, action_kinds)
    row = row_for(db, troupe.id, key)
    if any(
        r.key != key and r.name.lower() == new.name.strip().lower() for r in rows(db, troupe.id)
    ):
        raise conflict(f"There is already a keyword called {new.name.strip()}.")
    apply(row, new)
    db.flush()
    audit.record(db, staff, "house.keyword_changed", troupe_id=troupe.id, keyword=row.name)
    return row


def add(
    db: Session,
    staff: User,
    troupe: Troupe,
    new: Change,
    action_kinds: Mapping[str, str],
    key: str | None = None,
) -> DowntimeKeyword:
    """Add a keyword of the troupe's own, under a new key; or under `key`, one of
    another troupe's own keys, when its settings are imported (horatio.troupe_settings_share)."""
    check_change(new, action_kinds)
    found = materialise(db, troupe.id)
    if any(r.name.lower() == new.name.strip().lower() for r in found):
        raise conflict(f"There is already a keyword called {new.name.strip()}.")
    row = DowntimeKeyword(
        troupe_id=troupe.id,
        key=key or f"own_{uuid.uuid4().hex[:8]}",
        position=max((r.position for r in found), default=-1) + 1,
        name="",
    )
    apply(row, new)
    db.add(row)
    db.flush()
    audit.record(db, staff, "house.keyword_added", troupe_id=troupe.id, keyword=row.name)
    return row


def retire(db: Session, staff: User, troupe: Troupe, key: str, retired: bool) -> DowntimeKeyword:
    from horatio.downtimes import now

    row = row_for(db, troupe.id, key)
    if (row.retired_at is not None) == retired:
        return row
    row.retired_at = now() if retired else None
    db.flush()
    audit.record(
        db,
        staff,
        "house.keyword_retired" if retired else "house.keyword_restored",
        troupe_id=troupe.id,
        keyword=row.name,
    )
    return row


def reorder(db: Session, staff: User, troupe: Troupe, keys: Sequence[str]) -> None:
    found = materialise(db, troupe.id)
    if sorted(keys) != sorted(r.key for r in found):
        raise unprocessable("Give every keyword, each once, in the new order.")
    position = {k: n for n, k in enumerate(keys)}
    for row in found:
        row.position = position[row.key]
    db.flush()
    audit.record(db, staff, "house.keywords_reordered", troupe_id=troupe.id)


def reset(db: Session, staff: User, troupe: Troupe) -> None:
    """Back to Horatio's defaults. The troupe's own keywords are retired, not removed,
    so its past downtimes keep them."""
    from horatio.downtimes import now

    for row in rows(db, troupe.id):
        default = DEFAULT_BY_KEY.get(row.key)
        if default is None:
            row.retired_at = row.retired_at or now()
            row.position = 1_000 + row.position
            continue
        apply(
            row,
            Change(
                name=default.name,
                explanation=default.explanation,
                fields=list(default.fields),
                action_kinds=list(default.action_kinds),
                computers_only=default.computers_only,
                science=default.science,
                cost=default.cost,
                required_for=list(default.required_for),
                step=default.step,
            ),
        )
        row.position = default.position
        row.retired_at = None
    db.flush()
    audit.record(db, staff, "house.keywords_reset", troupe_id=troupe.id)


# --- in words -----------------------------------------------------------------------------


def describe(keyword: Keyword, kinds: Mapping[str, str]) -> str:
    """The keyword's rules in a sentence, for the House rules tab."""
    parts: list[str] = []
    if keyword.fields:
        parts.append(
            "asks for " + ", ".join(FIELDS[f].split(":")[0].lower() for f in keyword.fields)
        )
    if keyword.computers_only:
        parts.append("only with the Computer skill's action")
    elif keyword.action_kinds:
        parts.append(
            "spent from "
            + " or ".join(kinds.get(k, k.replace("_", " ")).lower() for k in keyword.action_kinds)
            + "s"
        )
    if keyword.science:
        parts.append("fits a Science")
    if keyword.cost != 1:
        parts.append(f"costs {keyword.cost} action{'' if keyword.cost == 1 else 's'}")
    if keyword.required_for:
        parts.append(
            "required each cycle of " + " and ".join(a + "s" for a in keyword.required_for)
        )
    parts.append(f"resolved at step {keyword.step}: {STEPS[keyword.step].lower()}")
    head = f"{keyword.name}: {keyword.explanation}" if keyword.explanation else keyword.name
    return head + " (" + "; ".join(parts) + ")"


def house_settings(
    db: Session, troupe: Troupe, kinds: Mapping[str, str]
) -> list[tuple[str, str, str]]:
    """The troupe's keywords that differ from Horatio's, as (name, how it plays them, the
    default), for the House rules tab."""
    found = rows(db, troupe.id)
    if not found:
        return []
    out: list[tuple[str, str, str]] = []
    keywords = troupe_keywords(db, troupe.id)
    for keyword in keywords:
        default = DEFAULT_BY_KEY.get(keyword.key)
        if keyword.retired:
            if default is not None or keyword.key.startswith("own_"):
                out.append(
                    (
                        f"Downtime keyword: {keyword.name}",
                        "Retired: no longer offered",
                        describe(default, kinds) if default else "Not one of Horatio's keywords",
                    )
                )
            continue
        if default is None:
            out.append(
                (
                    f"Downtime keyword: {keyword.name}",
                    describe(keyword, kinds),
                    "Not one of Horatio's keywords",
                )
            )
        elif replace(keyword, position=0) != replace(default, position=0):
            out.append(
                (
                    f"Downtime keyword: {default.name}",
                    describe(keyword, kinds),
                    describe(default, kinds),
                )
            )
    order = [k.key for k in keywords if not k.retired]
    default_order = [k.key for k in DEFAULTS if k.key in order]
    if [k for k in order if k in DEFAULT_KEYS] != default_order:
        out.append(
            (
                "Order of the downtime keywords",
                ", ".join(k.name for k in keywords if not k.retired),
                ", ".join(k.name for k in DEFAULTS),
            )
        )
    return out
