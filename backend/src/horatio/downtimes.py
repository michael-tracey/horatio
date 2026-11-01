"""Downtime cycles, their forms, participants and submissions (CONTEXT.md: Downtimes).

A cycle starts as a draft, with a copy of the troupe's previous form (or a
default form of one action question per action kind). Opening it fixes who
takes part and each participant's action allowance, worked out from the
approved sheet and the troupe's rules; later sheet changes do not alter it.
Storytellers and assistant storytellers can add or remove participants after
opening, but only characters whose home troupe runs the cycle.

While the troupe runs quests, each new form has the Quest action too
(horatio.quest_actions).

Players save answers as a draft and submit them, and can keep editing until
the grace period ends. A submission after the close date is marked late;
after the grace period only a storyteller's say-so lets one in.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from horatio import audit, feeding, influence, responses, suspensions
from horatio.models import (
    AllowanceAdjustment,
    Answer,
    Character,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    OwedAction,
    Question,
    RuleSet,
    Submission,
    Troupe,
    User,
    XpEntry,
)
from horatio.rules import feeding as feeding_rules
from horatio.rules.allowance import AllowanceLine, allowance
from horatio.rules.model import SheetTrait
from horatio.rules.store import read_troupe_rules
from horatio.sheets import conflict, pending_disciplines, sheet_rows, unprocessable

ANSWER_TYPES = ("long_text", "short_text", "choice", "number", "yes_no")
# Questions that spend an action of their action kind: an action question, and the
# Quest action (horatio.quest_actions).
SPENDING = ("action", "quest")


def now() -> datetime:
    """The current time; tests replace this."""
    return datetime.now(UTC)


# --- the form ---------------------------------------------------------------------------


@dataclass
class QuestionSpec:
    kind: str
    prompt: str
    action_kind: str | None = None
    help_text: str = ""
    answer_type: str = "long_text"
    options: Sequence[str] = ()
    required: bool = False
    max_answers: int | None = None
    visible_to: dict[str, Any] | None = None
    id: uuid.UUID | None = None


def troupe_action_kinds(db: Session, troupe: Troupe) -> dict[str, str]:
    """Every action kind the troupe's characters could have, across all splats: key -> name."""
    kinds: dict[str, str] = {}
    for splat in db.scalars(select(RuleSet.splat).order_by(RuleSet.splat)):
        for kind in read_troupe_rules(db, splat, troupe.id).action_kinds().values():
            kinds.setdefault(kind.key, kind.name)
    return kinds


def quest_question() -> QuestionSpec:
    """The Quest action (horatio.quest_actions), spending a general action until the
    troupe chooses another kind."""
    return QuestionSpec(
        kind="quest",
        action_kind="general",
        prompt="Quest",
        help_text="Choose a quest your character takes part in, and say what they do towards it.",
    )


def default_form(db: Session, troupe: Troupe) -> list[QuestionSpec]:
    return [
        QuestionSpec(kind="action", action_kind=key, prompt=name)
        for key, name in troupe_action_kinds(db, troupe).items()
    ]


def check_question(spec: QuestionSpec, action_kinds: dict[str, str]) -> None:
    if spec.kind not in ("action", "custom", "quest"):
        raise unprocessable(f"Unknown question kind {spec.kind!r}.")
    if spec.kind in SPENDING:
        if spec.action_kind not in action_kinds:
            raise unprocessable(f"No action kind {spec.action_kind!r} in this troupe's rules.")
        if spec.max_answers is not None and spec.max_answers < 1:
            raise unprocessable("max_answers must be at least 1.")
    elif spec.action_kind is not None or spec.max_answers is not None:
        raise unprocessable("Custom questions spend no actions.")
    if spec.answer_type not in ANSWER_TYPES:
        raise unprocessable(f"Unknown answer type {spec.answer_type!r}.")
    if spec.answer_type == "choice" and not spec.options:
        raise unprocessable(f"{spec.prompt!r} is a choice question with no options.")
    if not spec.prompt.strip():
        raise unprocessable("Every question needs a prompt.")


def questions(db: Session, cycle: DowntimeCycle) -> list[Question]:
    return list(
        db.scalars(
            select(Question).where(Question.cycle_id == cycle.id).order_by(Question.position)
        )
    )


def write_questions(
    db: Session, staff: User, cycle: DowntimeCycle, specs: Sequence[QuestionSpec], troupe: Troupe
) -> list[Question]:
    """Replace the cycle's form. Questions keep their ids when given them back, so
    answers stay attached; a question that already has answers cannot be removed."""
    if cycle.status not in ("draft", "open"):
        raise conflict("The form of a closed cycle cannot change.")
    kinds = troupe_action_kinds(db, troupe)
    for spec in specs:
        check_question(spec, kinds)

    existing = {q.id: q for q in questions(db, cycle)}
    kept = {spec.id for spec in specs if spec.id is not None}
    if kept - existing.keys():
        raise unprocessable("Some question ids are not on this cycle's form.")
    for question_id in existing.keys() - kept:
        if db.scalar(select(Answer.id).where(Answer.question_id == question_id).limit(1)):
            raise conflict(f"{existing[question_id].prompt!r} has answers and cannot be removed.")
        db.delete(existing[question_id])
    db.flush()

    result: list[Question] = []
    for position, spec in enumerate(specs):
        question = existing.get(spec.id) if spec.id else None
        if question is None:
            question = Question(cycle_id=cycle.id)
            db.add(question)
        question.position = position
        question.kind = spec.kind
        question.action_kind = spec.action_kind
        question.prompt = spec.prompt
        question.help_text = spec.help_text
        question.answer_type = spec.answer_type
        question.options = list(spec.options)
        question.required = spec.required
        question.max_answers = spec.max_answers
        question.visible_to = spec.visible_to
        result.append(question)
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.form_changed",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        cycle_status=cycle.status,
        questions=len(result),
    )
    return result


# --- cycles -----------------------------------------------------------------------------


def create_cycle(
    db: Session,
    staff: User,
    troupe: Troupe,
    name: str,
    closes_at: datetime,
    grace_ends_at: datetime,
    completion_xp: int | None = None,
) -> DowntimeCycle:
    """A new cycle, its form copied from the troupe's last one. Completing it earns
    `completion_xp`, or the troupe's usual amount."""
    if grace_ends_at < closes_at:
        raise unprocessable("The grace period cannot end before the cycle closes.")
    previous = db.scalar(
        select(DowntimeCycle)
        .where(DowntimeCycle.troupe_id == troupe.id)
        .order_by(DowntimeCycle.id.desc())
        .limit(1)
    )
    cycle = DowntimeCycle(
        troupe_id=troupe.id,
        name=name,
        closes_at=closes_at,
        grace_ends_at=grace_ends_at,
        completion_xp=troupe.downtime_xp if completion_xp is None else completion_xp,
        # Each clan's feeding carries on from the last cycle until staff change it.
        feeding_difficulty=dict(previous.feeding_difficulty) if previous else {},
    )
    db.add(cycle)
    db.flush()
    if previous is None:
        specs = default_form(db, troupe)
    else:
        specs = [
            QuestionSpec(
                kind=q.kind,
                action_kind=q.action_kind,
                prompt=q.prompt,
                help_text=q.help_text,
                answer_type=q.answer_type,
                options=q.options,
                required=q.required,
                max_answers=q.max_answers,
                visible_to=q.visible_to,
            )
            for q in questions(db, previous)
        ]
    if troupe.quests_enabled and not any(spec.kind == "quest" for spec in specs):
        specs.append(quest_question())
    write_questions(db, staff, cycle, specs, troupe)
    audit.record(db, staff, "downtime.cycle_created", troupe_id=troupe.id, cycle_id=cycle.id)
    return cycle


def set_completion_xp(db: Session, staff: User, cycle: DowntimeCycle, amount: int) -> None:
    """Change what completing the cycle earns, until it closes. Awards already given
    stand; storytellers correct one by hand if they need to."""
    if cycle.status not in ("draft", "open"):
        raise conflict("This cycle has closed; its experience for completing is settled.")
    cycle.completion_xp = amount
    audit.record(
        db,
        staff,
        "downtime.completion_xp_set",
        troupe_id=cycle.troupe_id,
        cycle_id=cycle.id,
        amount=amount,
    )


def award_completion_xp(
    db: Session,
    player: User,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
) -> None:
    """On submitting: the cycle's XP for completing it, once per participant however
    often it is reopened and submitted again."""
    if character.kind != "pc" or participant.completion_xp_entry_id or cycle.completion_xp <= 0:
        return
    entry = XpEntry(
        character_id=character.id,
        kind="award",
        amount=cycle.completion_xp,
        reason=f"Completed downtime: {cycle.name}",
        entered_by=player.id,
    )
    db.add(entry)
    db.flush()
    participant.completion_xp_entry_id = entry.id
    audit.record(
        db,
        player,
        "xp.downtime_completed",
        troupe_id=cycle.troupe_id,
        character_id=character.id,
        cycle_id=cycle.id,
        amount=cycle.completion_xp,
    )


def allowance_sheet(db: Session, character: Character) -> list[SheetTrait]:
    """The sheet allowances are worked out from: as it stands, leaving out discipline
    dots still waiting on the home troupe."""
    pending = {
        (d.trait_definition_id, d.detail): d.from_rating
        for _, d in pending_disciplines(db, character)
    }
    sheet: list[SheetTrait] = []
    for row in sheet_rows(db, character):
        trait = row.as_rules_trait()
        held = pending.get((row.definition.id, row.trait.detail))
        if held is not None:
            trait = replace(trait, rating=held)
        sheet.append(trait)
    return sheet


def fill_allowance(
    db: Session, participant: CycleParticipant, character: Character, troupe: Troupe
) -> None:
    rules = read_troupe_rules(db, character.splat, troupe.id)
    sheet = allowance_sheet(db, character)
    totals, lines = allowance(rules, sheet)
    # What the character's locations add: Fancy, Lowdown and Dirty (horatio.location_quests).
    from horatio import location_quests

    found: list[AllowanceLine] = list(lines)
    for line in location_quests.allowance_lines(db, character, troupe.id):
        if line.action_kind in totals:
            totals[line.action_kind] += line.amount
            found.append(line)
    participant.feeding = feeding_rules.basis(rules, sheet)
    participant.allowance = totals
    participant.allowance_breakdown = [
        {"action_kind": line.action_kind, "source": line.source, "amount": line.amount}
        | ({"note": line.note} if line.note else {})
        for line in found
    ]


def open_cycle(db: Session, staff: User, cycle: DowntimeCycle, troupe: Troupe) -> int:
    """Open the cycle and fix its participants. Returns how many there are."""
    if cycle.status != "draft":
        raise conflict(f"This cycle is already {cycle.status}.")
    already_open = db.scalar(
        select(DowntimeCycle.id).where(
            DowntimeCycle.troupe_id == troupe.id, DowntimeCycle.status == "open"
        )
    )
    if already_open is not None:
        raise conflict("Another cycle is already open in this troupe.")
    cycle.status = "open"
    cycle.opened_at = now()
    db.flush()
    # Characters whose home troupe this is: it accepted them when it became their home.
    characters = db.scalars(
        select(Character).where(
            Character.home_troupe_id == troupe.id,
            Character.status == "active",
            Character.kind == "pc",
        )
    )
    count = 0
    for character in characters:
        participant = CycleParticipant(cycle_id=cycle.id, character_id=character.id)
        fill_allowance(db, participant, character, troupe)
        db.add(participant)
        db.flush()
        settle_owed_actions(db, participant, cycle)
        count += 1
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.cycle_opened",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        participants=count,
    )
    return count


def close_cycle(db: Session, staff: User, cycle: DowntimeCycle) -> None:
    if cycle.status != "open":
        raise conflict(f"Only an open cycle can close; this one is {cycle.status}.")
    cycle.status = "closed"
    cycle.closed_at = now()
    db.flush()
    audit.record(db, staff, "downtime.cycle_closed", troupe_id=cycle.troupe_id, cycle_id=cycle.id)


# --- participants -----------------------------------------------------------------------


def add_participant(
    db: Session, staff: User, cycle: DowntimeCycle, troupe: Troupe, character: Character
) -> CycleParticipant:
    if cycle.status not in ("draft", "open"):
        raise conflict("Participants can only be added to a draft or open cycle.")
    if cycle.status == "draft":
        raise conflict("Participants are chosen when the cycle opens.")
    if (
        character.home_troupe_id != troupe.id
        or character.kind != "pc"
        or character.status != "active"
    ):
        raise conflict("Only active characters whose home troupe this is can take part.")
    participant = db.scalar(
        select(CycleParticipant).where(
            CycleParticipant.cycle_id == cycle.id, CycleParticipant.character_id == character.id
        )
    )
    if participant is not None and participant.removed_at is None:
        raise conflict("That character is already taking part.")
    if participant is None:
        participant = CycleParticipant(cycle_id=cycle.id, character_id=character.id)
        fill_allowance(db, participant, character, troupe)
        db.add(participant)
    else:
        fill_allowance(db, participant, character, troupe)
    participant.removed_at = None
    participant.removed_by = None
    participant.added_by = staff.id
    db.flush()
    settle_owed_actions(db, participant, cycle)
    audit.record(
        db,
        staff,
        "downtime.participant_added",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        character_id=character.id,
    )
    return participant


def remove_participant(
    db: Session, staff: User, participant: CycleParticipant, troupe: Troupe
) -> None:
    """Marked removed rather than deleted, so a submission and its responses stay."""
    if participant.removed_at is not None:
        raise conflict("That character has already been removed.")
    participant.removed_at = now()
    participant.removed_by = staff.id
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.participant_removed",
        troupe_id=troupe.id,
        cycle_id=participant.cycle_id,
        character_id=participant.character_id,
    )


def owe_actions(db: Session, user: User, character: Character, amount: int, reason: str) -> None:
    """Record downtime actions the character owes its home troupe, and take them
    from its current cycle if it has not submitted yet."""
    if amount <= 0 or character.home_troupe_id is None or character.kind != "pc":
        return
    db.add(
        OwedAction(
            character_id=character.id,
            troupe_id=character.home_troupe_id,
            action_kind="general",
            amount=amount,
            reason=reason,
            owed_by=user.id,
        )
    )
    db.flush()
    current = current_participation(db, character)
    if current is not None:
        settle_owed_actions(db, current[1], current[0])


def settle_owed_actions(db: Session, participant: CycleParticipant, cycle: DowntimeCycle) -> None:
    """Take what the character owes off this participation, unless its downtime
    is already submitted (then it waits for the next cycle)."""
    submitted = db.scalar(
        select(Submission.id).where(
            Submission.participant_id == participant.id, Submission.status == "submitted"
        )
    )
    if submitted is not None:
        return
    owed = db.scalars(
        select(OwedAction).where(
            OwedAction.character_id == participant.character_id,
            OwedAction.troupe_id == cycle.troupe_id,
            OwedAction.participant_id.is_(None),
        )
    )
    for debt in owed:
        db.add(
            AllowanceAdjustment(
                participant_id=participant.id,
                action_kind=debt.action_kind,
                delta=-debt.amount,
                reason=debt.reason,
                adjusted_by=debt.owed_by,
                owed_action_id=debt.id,
            )
        )
        debt.participant_id = participant.id
    db.flush()


def adjust_allowance(
    db: Session,
    staff: User,
    participant: CycleParticipant,
    troupe: Troupe,
    action_kind: str,
    delta: int,
    reason: str,
) -> AllowanceAdjustment:
    if action_kind not in troupe_action_kinds(db, troupe):
        raise unprocessable(f"No action kind {action_kind!r} in this troupe's rules.")
    adjustment = AllowanceAdjustment(
        participant_id=participant.id,
        action_kind=action_kind,
        delta=delta,
        reason=reason,
        adjusted_by=staff.id,
    )
    db.add(adjustment)
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.allowance_adjusted",
        troupe_id=troupe.id,
        character_id=participant.character_id,
        action_kind=action_kind,
        delta=delta,
        reason=reason,
    )
    return adjustment


def adjustments(db: Session, participant: CycleParticipant) -> list[AllowanceAdjustment]:
    return list(
        db.scalars(
            select(AllowanceAdjustment)
            .where(AllowanceAdjustment.participant_id == participant.id)
            .order_by(AllowanceAdjustment.id)
        )
    )


def allowance_totals(db: Session, participant: CycleParticipant) -> dict[str, int]:
    """The allowance with its adjustments, before any is stopped at zero."""
    totals = dict(participant.allowance)
    for adjustment in adjustments(db, participant):
        totals[adjustment.action_kind] = totals.get(adjustment.action_kind, 0) + adjustment.delta
    return totals


def effective_allowance(db: Session, participant: CycleParticipant) -> dict[str, int]:
    """The allowance with its adjustments. None goes below zero."""
    return {k: max(0, v) for k, v in allowance_totals(db, participant).items()}


def shortfall(
    db: Session,
    participant: CycleParticipant,
    adjusted: Sequence[AllowanceAdjustment] | None = None,
) -> dict[str, int]:
    """Actions taken off beyond the allowance, such as more influence spent at
    games than the character's rating allows a month (MET: VtM core, p. 510), or
    flaws taking more than the character has (Hunted's two, from an allowance of
    one): counted from the breakdown, before the allowance stopped at zero.
    `adjusted` is its adjustments, when already loaded."""
    totals: dict[str, int] = {}
    for line in participant.allowance_breakdown:
        totals[line["action_kind"]] = totals.get(line["action_kind"], 0) + line["amount"]
    for adjustment in adjustments(db, participant) if adjusted is None else adjusted:
        totals[adjustment.action_kind] = totals.get(adjustment.action_kind, 0) + adjustment.delta
    return {kind: -total for kind, total in totals.items() if total < 0}


# --- submissions ------------------------------------------------------------------------


def current_participation(
    db: Session, character: Character
) -> tuple[DowntimeCycle, CycleParticipant] | None:
    """The open cycle this character is taking part in, if any."""
    found = db.execute(
        select(DowntimeCycle, CycleParticipant)
        .join(CycleParticipant, CycleParticipant.cycle_id == DowntimeCycle.id)
        .where(
            CycleParticipant.character_id == character.id,
            CycleParticipant.removed_at.is_(None),
            DowntimeCycle.status == "open",
        )
    ).first()
    return (found[0], found[1]) if found else None


def visible_questions(
    db: Session, cycle: DowntimeCycle, character: Character, allowance: dict[str, int]
) -> list[Question]:
    """The questions this character is asked: custom ones for its splat, and action
    ones for kinds it has actions of; the Quest action while the troupe runs quests."""
    troupe = db.get(Troupe, cycle.troupe_id)
    shown: list[Question] = []
    for q in questions(db, cycle):
        splats = (q.visible_to or {}).get("splats")
        if splats and character.splat not in splats:
            continue
        if q.kind in SPENDING and allowance.get(q.action_kind or "", 0) == 0:
            continue
        if q.kind == "quest" and (troupe is None or not troupe.quests_enabled):
            continue
        shown.append(q)
    return shown


def submission_for(db: Session, participant: CycleParticipant) -> Submission | None:
    return db.scalar(select(Submission).where(Submission.participant_id == participant.id))


@dataclass(frozen=True)
class Waiting:
    """What waits for a character's player between games."""

    # When the downtime it has yet to submit is due (the soonest, if several); None for none.
    due: datetime | None = None
    # When each cycle's results last reached the player, newest first.
    delivered: tuple[datetime, ...] = ()


def waiting(db: Session, character_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Waiting]:
    """For each character, the downtime due and the results delivered, asked in two
    queries for all of them. A character with neither is left out."""
    due: dict[uuid.UUID, datetime] = {}
    for character_id, closes_at in db.execute(
        select(CycleParticipant.character_id, DowntimeCycle.closes_at)
        .join(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
        .outerjoin(Submission, Submission.participant_id == CycleParticipant.id)
        .where(
            CycleParticipant.character_id.in_(character_ids),
            CycleParticipant.removed_at.is_(None),
            DowntimeCycle.status == "open",
            or_(Submission.id.is_(None), Submission.status != "submitted"),
        )
    ):
        due[character_id] = min(closes_at, due.get(character_id, closes_at))
    delivered: dict[uuid.UUID, list[datetime]] = defaultdict(list)
    for character_id, sent_at in db.execute(
        select(CycleParticipant.character_id, func.max(Delivery.sent_at))
        .join(Submission, Delivery.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .where(
            CycleParticipant.character_id.in_(character_ids),
            Delivery.channel == "horatio",
            Delivery.status == "sent",
            Delivery.test_mode.is_(False),
            Delivery.sent_at.is_not(None),
        )
        .group_by(CycleParticipant.character_id, CycleParticipant.cycle_id)
    ):
        if sent_at is not None:
            delivered[character_id].append(sent_at)
    return {
        c: Waiting(due=due.get(c), delivered=tuple(sorted(delivered[c], reverse=True)))
        for c in {*due, *delivered}
    }


def answers_for(db: Session, submission: Submission) -> list[Answer]:
    return list(
        db.scalars(
            select(Answer)
            .join(Question, Answer.question_id == Question.id)
            .where(Answer.submission_id == submission.id)
            .order_by(Question.position, Answer.slot)
        )
    )


def ensure_can_submit(cycle: DowntimeCycle, participant: CycleParticipant) -> None:
    if cycle.status != "open":
        raise conflict("This cycle is not open.")
    if now() > cycle.grace_ends_at and participant.late_accepted_by is None:
        raise conflict("The grace period is over. Ask a storyteller to accept a late downtime.")


@dataclass
class AnswerSpec:
    question_id: uuid.UUID
    body: str
    slot: int = 1
    structured: dict[str, Any] | None = None


def check_answer(question: Question, spec: AnswerSpec) -> None:
    body = spec.body.strip()
    if question.answer_type == "choice" and body and body not in question.options:
        raise unprocessable(f"{question.prompt!r}: choose one of the options.")
    if question.answer_type == "number" and body:
        try:
            float(body)
        except ValueError:
            raise unprocessable(f"{question.prompt!r} needs a number.") from None
    if question.answer_type == "yes_no" and body and body not in ("yes", "no"):
        raise unprocessable(f"{question.prompt!r}: answer yes or no.")


def save_answers(
    db: Session,
    player: User,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    specs: Sequence[AnswerSpec],
    feeding_answer: feeding.FeedingAnswer | None = None,
) -> Submission:
    """Replace the character's answers, and its Feeding section when given one.
    Blank answers are dropped, but for a Quest action that names its quest. Feeding
    actions come out of the general actions."""
    from horatio import quest_actions

    ensure_can_submit(cycle, participant)
    suspensions.refuse_character(db, character)
    allowance_now = effective_allowance(db, participant)
    shown = {q.id: q for q in visible_questions(db, cycle, character, allowance_now)}

    submission = submission_for(db, participant)
    before_now = answers_for(db, submission) if submission else []
    existing = {(a.question_id, a.slot): a for a in before_now}
    standings: dict[influence.InfluenceType, influence.Standing] | None = None

    feeding_before = feeding.answer_of(submission)
    if feeding_answer is None:
        feeding_answer = feeding_before
    else:
        feeding.check_answer(
            db,
            cycle,
            character,
            feeding.participant_basis(db, participant, character, cycle),
            feeding_answer,
        )
    used: dict[str, int] = {"general": feeding_answer.actions}
    if feeding_answer.actions > allowance_now.get("general", 0):
        raise unprocessable(
            f"That is more feeding actions than the {allowance_now.get('general', 0)} "
            "downtime actions this character has."
        )
    per_question: dict[uuid.UUID, int] = {}
    seen: set[tuple[uuid.UUID, int]] = set()
    chosen_quests: set[uuid.UUID] = set()

    def names_quest(spec: AnswerSpec) -> bool:
        question = shown.get(spec.question_id)
        return question is not None and question.kind == "quest" and bool(spec.structured)

    kept = [s for s in specs if s.body.strip() or names_quest(s)]
    for spec in kept:
        question = shown.get(spec.question_id)
        if question is None:
            raise unprocessable("That question is not on this character's form.")
        if (spec.question_id, spec.slot) in seen or spec.slot < 1:
            raise unprocessable(f"{question.prompt!r}: each answer needs its own slot, from 1.")
        seen.add((spec.question_id, spec.slot))
        check_answer(question, spec)
        if question.kind == "custom" and spec.slot != 1:
            raise unprocessable(f"{question.prompt!r} takes one answer.")
        if question.kind == "quest":
            spec.structured, quest = quest_actions.check_answer(
                db,
                character,
                cycle,
                question,
                spec.structured or {},
                existing.get((spec.question_id, spec.slot)),
                chosen_quests,
            )
            # A quest chosen with nothing said is taken up as it stands.
            spec.body = spec.body.strip() or quest.name
        if question.kind in SPENDING:
            per_question[question.id] = per_question.get(question.id, 0) + 1
            if (
                question.max_answers is not None
                and per_question[question.id] > question.max_answers
            ):
                raise unprocessable(f"{question.prompt!r} takes at most {question.max_answers}.")
            kind = question.action_kind or ""
            influence_type = influence.type_of(kind) if question.kind == "action" else None
            before = existing.get((spec.question_id, spec.slot))
            changed = before is None or (spec.structured or {}) != before.structured
            if influence_type is not None and changed:
                # Checked when it changes, so a rating lowered since does not lock it.
                standings = standings or influence.standings(db, character)
                influence.check_answer(
                    standings[influence_type], question.prompt, spec.structured or {}
                )
            used[kind] = used.get(kind, 0) + 1
            if used[kind] > allowance_now.get(kind, 0):
                fed = feeding_answer.actions if kind == "general" else 0
                raise unprocessable(
                    f"That is more {kind.replace('_', ' ')} actions than the "
                    f"{allowance_now.get(kind, 0)} this character has"
                    + (f", with {fed} spent feeding." if fed else ".")
                )

    if submission is None:
        submission = Submission(participant_id=participant.id)
        db.add(submission)
        db.flush()
    by_key = {(s.question_id, s.slot): s for s in kept}
    if submission.status == "submitted":
        # A storyteller has already answered these; the player cannot change them now.
        locked = responses.written_answer_ids(db, submission)
        for key, answer in existing.items():
            spec = by_key.get(key)
            if answer.id in locked and (
                spec is None
                or spec.body.strip() != answer.body
                or (spec.structured or {}) != answer.structured
            ):
                raise conflict("A storyteller has already answered that; it can no longer change.")
        responses.drop_unwritten_responses(
            db, {a.id for key, a in existing.items() if key not in seen}
        )
        if (
            submission.feeding_result is not None
            and feeding_answer.stored() != feeding_before.stored()
        ):
            raise conflict(
                "A storyteller has already answered your feeding; it can no longer change."
            )
    for key, answer in existing.items():
        if key not in seen:
            db.delete(answer)
    db.flush()
    for spec in kept:
        answer = existing.get((spec.question_id, spec.slot))
        if answer is None:
            answer = Answer(
                submission_id=submission.id, question_id=spec.question_id, slot=spec.slot
            )
            db.add(answer)
        answer.body = spec.body.strip()
        answer.structured = spec.structured or {}
    submission.feeding = feeding_answer.stored()
    db.flush()
    responses.sync_responses(db, submission)
    if submission.status == "submitted":
        quest_actions.join_chosen(db, player, character, submission)
    return submission


def submit(
    db: Session,
    player: User,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
) -> Submission:
    """Submit the downtime, joining the party of each quest its Quest actions name."""
    from horatio import quest_actions

    ensure_can_submit(cycle, participant)
    suspensions.refuse_character(db, character)
    submission = submission_for(db, participant)
    answered = {a.question_id for a in answers_for(db, submission)} if submission else set()
    allowance_now = effective_allowance(db, participant)
    missing = [
        q.prompt
        for q in visible_questions(db, cycle, character, allowance_now)
        if q.required and q.id not in answered
    ]
    if missing:
        raise unprocessable("Answer these first: " + "; ".join(missing))
    if submission is None:
        submission = Submission(participant_id=participant.id)
        db.add(submission)
    submission.status = "submitted"
    submission.submitted_at = now()
    submission.late = now() > cycle.closes_at
    db.flush()
    responses.sync_responses(db, submission)
    audit.record(
        db,
        player,
        "downtime.submitted",
        troupe_id=cycle.troupe_id,
        character_id=character.id,
        cycle_id=cycle.id,
        late=submission.late,
    )
    award_completion_xp(db, player, character, cycle, participant)
    quest_actions.join_chosen(db, player, character, submission)
    return submission


def accept_late(db: Session, staff: User, participant: CycleParticipant, troupe: Troupe) -> None:
    participant.late_accepted_by = staff.id
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.late_accepted",
        troupe_id=troupe.id,
        character_id=participant.character_id,
        cycle_id=participant.cycle_id,
    )
