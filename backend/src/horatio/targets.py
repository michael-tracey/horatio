"""Downtime actions aimed at characters (#507; CONTEXT.md: Target).

**Aimed at.** An action answer can name the characters it is aimed at: spying on
them, investigating them, working against them. Its player picks them from the
troupe's characters, home or visiting, not retired, never its own. They are kept in
the answer's `structured`, as `aimed_at`: a list of character ids. Only action
questions take them, not a custom question or the Quest action. A kind of action
that needs a target can ask `check` to refuse one without.

**Who sees it.** The player who aims it, and the troupe's storytellers and assistant
storytellers. Never the target's player, and never a narrator: what narrators are
shown of an answer leaves it out (`without_aim`). The troupe's log notes it when the
downtime is submitted, belonging to no character, so it reaches no character's log.

**Cancel and Observe** (MET: VTM p. 93): the Computer skill lets a character cancel or
observe one downtime action of another character's. Its player marks one action a cycle
as a Cancel or an Observe (`counter`), aimed at one character; with keywords
(horatio.keywords), choosing the Cancel or Observe keyword marks it. Staff pair it with the
action of that character's it works on (`Answer.paired_answer_id`), and judge whether
it does.

**A Haven's Location** (p. 102): an action aimed at a character whose Haven, on this
troupe's locations, has the Location advantage costs two actions, and the allowance
counts it so. Its player is told only that it costs 2. Staff can say the action isn't
against them (`Answer.not_against`), such as a friendly visit, or that they no longer
stay in their Haven, and it costs 1 again.
"""

import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, responses
from horatio.models import (
    Answer,
    Character,
    DowntimeCycle,
    Location,
    Question,
    Response,
    Submission,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.sheets import conflict, sheet_rows, unprocessable

AIMED_AT = "aimed_at"
COUNTER = "counter"
COUNTERS = {"cancel": "Cancel", "observe": "Observe"}
# The skill that cancels or observes (p. 93), and the Haven advantage that doubles (p. 102).
COMPUTER = "Computer"
LOCATION = "Location"
KEYS = (AIMED_AT, COUNTER)


def aimed_at(structured: Mapping[str, Any]) -> list[uuid.UUID]:
    """The characters an answer is aimed at, by id."""
    raw = structured.get(AIMED_AT)
    found: list[uuid.UUID] = []
    for value in raw if isinstance(raw, list) else []:
        try:
            target = uuid.UUID(str(value))
        except ValueError:
            continue
        if target not in found:
            found.append(target)
    return found


def counter_of(structured: Mapping[str, Any]) -> str | None:
    """ "cancel" or "observe" for a Cancel or Observe, else None."""
    value = structured.get(COUNTER)
    return value if value in COUNTERS else None


def aiming(structured: Mapping[str, Any]) -> dict[str, Any]:
    """Only the parts of `structured` that say who the answer is aimed at, and how."""
    return {k: structured[k] for k in KEYS if k in structured}


def without_aim(structured: Mapping[str, Any]) -> dict[str, Any]:
    """`structured` with who it is aimed at left out, for those who may not see it."""
    return {k: v for k, v in structured.items() if k not in KEYS}


def choices(db: Session, troupe_id: uuid.UUID, character: Character) -> list[Character]:
    """Who the character can aim an action at in this troupe: its player characters,
    home or visiting, not retired, but itself, by name."""
    return list(
        db.scalars(
            select(Character)
            .join(TroupeMembership, TroupeMembership.character_id == Character.id)
            .where(
                TroupeMembership.troupe_id == troupe_id,
                TroupeMembership.left_at.is_(None),
                Character.status == "active",
                Character.kind == "pc",
                Character.id != character.id,
            )
            .order_by(Character.name, Character.id)
        )
    )


def with_location(db: Session, troupe_id: uuid.UUID, ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
    """Of `ids`, the characters whose Haven on the troupe's locations has the Location
    advantage (p. 102)."""
    if not ids:
        return set()
    havens = db.scalars(
        select(Location).where(Location.troupe_id == troupe_id, Location.haven_of_id.in_(ids))
    )
    return {h.haven_of_id for h in havens if h.haven_of_id and LOCATION in h.haven_advantages}


def has_computer(db: Session, character: Character) -> bool:
    return any(
        r.category.key == "skills" and r.definition.name == COMPUTER and (r.trait.rating or 0) > 0
        for r in sheet_rows(db, character)
    )


def doubled(
    structured: Mapping[str, Any], not_against: bool, located: Collection[uuid.UUID]
) -> bool:
    """Whether the answer costs two actions: aimed at someone whose Haven has Location,
    and not said by staff to be not against them."""
    return not not_against and any(t in located for t in aimed_at(structured))


def cost(structured: Mapping[str, Any], not_against: bool, located: Collection[uuid.UUID]) -> int:
    return 2 if doubled(structured, not_against, located) else 1


def check(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    question: Question,
    structured: Mapping[str, Any],
    before: Answer | None,
    *,
    required: bool = False,
) -> dict[str, Any]:
    """An answer's `structured` with who it is aimed at as it is kept. The targets
    must be characters it can aim at; one it was aimed at before stays, though it
    has left since. A Cancel or Observe is aimed at one character, by a character with
    the Computer skill."""
    raw = structured.get(AIMED_AT)
    if raw is not None and (
        not isinstance(raw, list) or len(aimed_at(structured)) != len({str(v) for v in raw})
    ):
        raise unprocessable(f"{question.prompt!r}: who it is aimed at is a list of characters.")
    targets = aimed_at(structured)
    counter = structured.get(COUNTER)
    if question.kind != "action":
        if targets or counter is not None:
            raise unprocessable(f"{question.prompt!r} can't be aimed at a character.")
        return dict(structured)
    if required and not targets:
        raise unprocessable(f"{question.prompt!r}: choose who it is aimed at.")
    had = aiming(before.structured) if before is not None else {}
    allowed = {c.id for c in choices(db, cycle.troupe_id, character)}
    allowed |= set(aimed_at(had))
    if any(t not in allowed for t in targets):
        raise unprocessable(f"{question.prompt!r}: choose characters of this troupe to aim it at.")
    if counter is not None:
        if counter not in COUNTERS:
            raise unprocessable(f"{question.prompt!r}: an action cancels or observes, or neither.")
        if len(targets) != 1:
            raise unprocessable(
                f"{question.prompt!r}: a {COUNTERS[counter]} is aimed at one character."
            )
        if counter_of(had) != counter and not has_computer(db, character):
            raise unprocessable(
                f"{question.prompt!r}: only a character with the Computer skill can cancel or "
                "observe another's action (p. 93)."
            )
    kept = without_aim(structured)
    if targets:
        kept[AIMED_AT] = [str(t) for t in targets]
    if counter is not None:
        kept[COUNTER] = counter
    return kept


def log(
    db: Session,
    player: User,
    character: Character,
    cycle: DowntimeCycle,
    question: Question,
    answer: Answer,
) -> None:
    """Note an action aimed at characters in the troupe's log, for its staff. It
    names no character as its own, so no character's log shows it."""
    targets = aimed_at(answer.structured)
    if not targets:
        return
    names = {c.id: c.name for c in db.scalars(select(Character).where(Character.id.in_(targets)))}
    counter = counter_of(answer.structured)
    audit.record(
        db,
        player,
        "downtime.aimed",
        troupe_id=cycle.troupe_id,
        cycle_id=cycle.id,
        character_name=character.name,
        question=question.prompt,
        targets=", ".join(names.get(t, "?") for t in targets),
        how=f", as a {COUNTERS[counter]}" if counter else "",
    )


def log_submission(
    db: Session, player: User, character: Character, cycle: DowntimeCycle, submission: Submission
) -> None:
    """On submitting: note each action aimed at characters."""
    for answer, question in db.execute(
        select(Answer, Question)
        .join(Question, Answer.question_id == Question.id)
        .where(Answer.submission_id == submission.id)
        .order_by(Question.position, Answer.slot)
    ):
        log(db, player, character, cycle, question, answer)


# --- what staff see -------------------------------------------------------------------------


@dataclass
class Aimed:
    """One action aimed at a character, as staff resolve it."""

    item: responses.WorkItem
    # The target's Haven has Location, so it costs two unless it isn't against them.
    located: bool
    # A Cancel or Observe: the target's action staff paired it with.
    paired: responses.WorkItem | None = None


@dataclass
class Target:
    character: Character
    actions: list[Aimed] = field(default_factory=list[Aimed])
    # Its own actions this cycle, for pairing a Cancel or Observe with.
    own: list[responses.WorkItem] = field(default_factory=list[responses.WorkItem])


def by_target(db: Session, cycle: DowntimeCycle) -> list[Target]:
    """The characters actions in the cycle's submitted downtimes are aimed at, by
    name, each with those actions."""
    items = responses.work_items(db, cycle)
    by_answer = {i.answer.id: i for i in items}
    ids = {t for i in items for t in aimed_at(i.answer.structured)}
    located = with_location(db, cycle.troupe_id, ids)
    characters = {c.id: c for c in db.scalars(select(Character).where(Character.id.in_(ids)))}
    targets: dict[uuid.UUID, Target] = {i: Target(characters[i]) for i in ids if i in characters}
    for item in items:
        for target_id in aimed_at(item.answer.structured):
            if target_id in targets:
                paired = (
                    by_answer.get(item.answer.paired_answer_id)
                    if item.answer.paired_answer_id
                    else None
                )
                targets[target_id].actions.append(Aimed(item, target_id in located, paired))
        if item.character.id in targets and item.question.kind == "action":
            targets[item.character.id].own.append(item)
    return sorted(targets.values(), key=lambda t: (t.character.name, t.character.id))


def paired_item(db: Session, item: responses.WorkItem) -> responses.WorkItem | None:
    """The action a Cancel or Observe is paired with."""
    if item.answer.paired_answer_id is None:
        return None
    response_id = db.scalar(
        select(Response.id).where(Response.answer_id == item.answer.paired_answer_id)
    )
    return responses.item_for(db, response_id) if response_id else None


def countered_by(db: Session, item: responses.WorkItem) -> list[responses.WorkItem]:
    """The Cancels and Observes staff paired with this action."""
    found = db.scalars(select(Answer.id).where(Answer.paired_answer_id == item.answer.id))
    ids = set(found)
    if not ids:
        return []
    return [i for i in responses.work_items(db, item.cycle) if i.answer.id in ids]


def set_not_against(
    db: Session, staff: User, item: responses.WorkItem, troupe: Troupe, value: bool
) -> None:
    """Staff say the action isn't against those it is aimed at, so it costs one
    action however their Havens stand; or that it is after all."""
    if not aimed_at(item.answer.structured):
        raise conflict("That action isn't aimed at anyone.")
    item.answer.not_against = value
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.not_against" if value else "downtime.against",
        troupe_id=troupe.id,
        cycle_id=item.cycle.id,
        character_name=item.character.name,
        question=item.question.prompt,
    )


def pair(
    db: Session,
    staff: User,
    item: responses.WorkItem,
    troupe: Troupe,
    paired: responses.WorkItem | None,
) -> None:
    """Pair a Cancel or Observe with the action of its target's it works on, or undo
    the pairing with None."""
    counter = counter_of(item.answer.structured)
    if counter is None:
        raise conflict("Only a Cancel or Observe is paired with another action.")
    if paired is not None:
        if paired.cycle.id != item.cycle.id or paired.character.id not in aimed_at(
            item.answer.structured
        ):
            raise unprocessable("Pair it with an action of the character it is aimed at.")
        if paired.question.kind != "action" or counter_of(paired.answer.structured):
            raise unprocessable("A Cancel or Observe can't be paired with that action.")
    item.answer.paired_answer_id = paired.answer.id if paired else None
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.paired" if paired else "downtime.unpaired",
        troupe_id=troupe.id,
        cycle_id=item.cycle.id,
        character_name=item.character.name,
        how=COUNTERS[counter],
        target=paired.character.name if paired else "",
        question=paired.question.prompt if paired else "",
    )


def names_of(db: Session, structureds: Sequence[Mapping[str, Any]]) -> dict[uuid.UUID, str]:
    ids = {t for s in structureds for t in aimed_at(s)}
    if not ids:
        return {}
    return {c.id: c.name for c in db.scalars(select(Character).where(Character.id.in_(ids)))}
