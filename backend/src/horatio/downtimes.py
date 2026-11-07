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
after the grace period only a storyteller's say-so lets one in. While the
cycle is open, staff can remind the players whose downtimes are not submitted.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from horatio import (
    audit,
    feeding,
    influence,
    item_expiry,
    keywords,
    notifications,
    preferences,
    responses,
    retainer_upkeep,
    suspensions,
    targets,
)
from horatio.models import (
    AllowanceAdjustment,
    Answer,
    AuditEvent,
    Character,
    CharacterTrait,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    HeldStatus,
    OwedAction,
    Question,
    Response,
    RuleSet,
    Submission,
    TraitCategory,
    TraitDefinition,
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


def past_due(cycle: DowntimeCycle, at: datetime | None = None) -> bool:
    """Whether the cycle is past Due (#469): its Due time, `closes_at`, has come.
    Player Nominations and Remembrances are published from then."""
    return cycle.closes_at <= (at or now())


WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def due_text(user: User, at: datetime) -> str:
    """A cycle's Due, or its Accepted until, for a message to `user`: in their time
    zone, date format and clock, as the app writes a deadline, "Sat 14 Nov, 6:00 pm
    EST" (#469). The year shows when it isn't this one (always, in ISO)."""
    prefs = preferences.read(user)
    zone = ZoneInfo(prefs.time_zone or "UTC")
    local = at.astimezone(zone)
    with_year = prefs.date_format == "iso" or local.year != now().astimezone(zone).year
    if prefs.date_format == "iso":
        day = f"{local:%Y-%m-%d}"
    elif prefs.date_format == "month_day":
        day = f"{local.month}/{local.day}" + (f"/{local.year}" if with_year else "")
    else:
        day = f"{local.day} {MONTHS[local.month - 1]}" + (f" {local.year}" if with_year else "")
    if prefs.clock == "24":
        clock = f"{local:%H:%M}"
    else:
        clock = f"{local.hour % 12 or 12}:{local:%M} {'am' if local.hour < 12 else 'pm'}"
    name = local.tzname() or ""
    if name[:1] in "+-":
        # A zone with no abbreviation, such as Asia/Dubai's "+04", as "GMT+4".
        hours, minutes = int(name[1:3]), name[3:5]
        name = f"GMT{name[0]}{hours}" + (f":{minutes}" if minutes and minutes != "00" else "")
    return f"{WEEKDAYS[local.weekday()]} {day}, {clock} {name}".rstrip()


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


def held_statuses(db: Session, character: Character) -> list[str]:
    """The fleeting and negative status the character holds, by name: Triumphant
    changes its feeding (horatio.rules.feeding)."""
    return list(db.scalars(select(HeldStatus.name).where(HeldStatus.character_id == character.id)))


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
    participant.feeding = feeding_rules.basis(rules, sheet, held_statuses(db, character))
    participant.allowance = totals
    participant.allowance_breakdown = [
        {"action_kind": line.action_kind, "source": line.source, "amount": line.amount}
        | ({"note": line.note} if line.note else {})
        | ({"only": line.only} if line.only else {})
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
    # It asks for the remembrances waiting for the next cycle (horatio.remembrances).
    from horatio import remembrances

    remembrances.asked_in(db, cycle, troupe)
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
    # The troupe's Retainer upkeep kept as a downtime cost, and Retainer growth.
    retainer_upkeep.cycle_closed(db, staff, cycle)
    # Items that expire with the cycle go now (horatio.item_expiry).
    item_expiry.check_due(db, cycle_ids=[cycle.id])


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


def addable(db: Session, cycle: DowntimeCycle) -> list[tuple[Character, User]]:
    """The characters `add_participant` would take, with their players, by name:
    the troupe's active player characters not taking part, a removed one included."""
    taking_part = select(CycleParticipant.character_id).where(
        CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None)
    )
    rows = db.execute(
        select(Character, User)
        .join(User, Character.player_id == User.id)
        .where(
            Character.home_troupe_id == cycle.troupe_id,
            Character.kind == "pc",
            Character.status == "active",
            Character.id.not_in(taking_part),
        )
        .order_by(Character.name)
    )
    return [(character, player) for character, player in rows]


# --- chasing submissions ----------------------------------------------------------------


def not_submitted(db: Session, cycle: DowntimeCycle) -> list[tuple[Character, User]]:
    """The characters taking part whose downtimes are not submitted, with their players."""
    rows = db.execute(
        select(Character, User)
        .select_from(CycleParticipant)
        .join(Character, CycleParticipant.character_id == Character.id)
        .join(User, Character.player_id == User.id)
        .outerjoin(Submission, Submission.participant_id == CycleParticipant.id)
        .where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.removed_at.is_(None),
            or_(Submission.id.is_(None), Submission.status != "submitted"),
        )
        .order_by(Character.name)
    )
    return [(character, player) for character, player in rows]


@dataclass(frozen=True)
class Reminded:
    players: int
    characters: int


def remind(db: Session, staff: User, cycle: DowntimeCycle, troupe: Troupe) -> Reminded:
    """Remind each player whose downtime is not submitted, in the bell (and by email
    for those who choose it), and record it for staff to see when they last did."""
    if cycle.status != "open":
        raise conflict("Only an open cycle's downtimes can be chased.")
    waiting = not_submitted(db, cycle)
    if not waiting:
        raise conflict("Every downtime is submitted: there is no one to remind.")
    for character, player in waiting:
        # Before Due, the Due; after it, until when a late one is accepted.
        when = (
            f"Accepted until {due_text(player, cycle.grace_ends_at)}"
            if past_due(cycle)
            else f"Due {due_text(player, cycle.closes_at)}"
        )
        notifications.notify(
            db,
            [player.id],
            "downtime.reminder",
            f"{character.name}'s downtime for {cycle.name} isn't submitted yet. {when}.",
            f"/characters/{character.id}/downtime",
            troupe_id=troupe.id,
            character_id=character.id,
        )
    reminded = Reminded(players=len({player.id for _, player in waiting}), characters=len(waiting))
    audit.record(
        db,
        staff,
        "downtime.reminded",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        players=reminded.players,
        characters=reminded.characters,
    )
    return reminded


@dataclass(frozen=True)
class Reminder:
    at: datetime
    by: str
    players: int


def reminders(db: Session, cycle: DowntimeCycle) -> list[Reminder]:
    """When staff reminded players about this cycle, newest first."""
    rows = db.execute(
        select(AuditEvent, User.display_name)
        .outerjoin(User, AuditEvent.actor_id == User.id)
        .where(
            AuditEvent.troupe_id == cycle.troupe_id,
            AuditEvent.action == "downtime.reminded",
            AuditEvent.data["cycle_id"].astext == str(cycle.id),
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
    return [
        Reminder(at=event.created_at, by=name or "?", players=int(event.data.get("players", 0)))
        for event, name in rows
    ]


@dataclass(frozen=True)
class Counts:
    """How far a cycle has got, for a line in a list of cycles."""

    participants: int = 0
    submitted: int = 0
    responses: int = 0
    written: int = 0


def counts(db: Session, cycle_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Counts]:
    """Each cycle's participants, submissions and responses, in two queries for all."""
    taking_part = CycleParticipant.removed_at.is_(None)
    found: dict[uuid.UUID, Counts] = {}
    for cycle_id, participants, submitted in db.execute(
        select(
            CycleParticipant.cycle_id,
            func.count(CycleParticipant.id),
            func.count(Submission.id).filter(Submission.status == "submitted"),
        )
        .outerjoin(Submission, Submission.participant_id == CycleParticipant.id)
        .where(CycleParticipant.cycle_id.in_(cycle_ids), taking_part)
        .group_by(CycleParticipant.cycle_id)
    ):
        found[cycle_id] = Counts(participants=participants, submitted=submitted)
    for cycle_id, total, written in db.execute(
        select(
            CycleParticipant.cycle_id,
            func.count(Response.id),
            func.count(Response.id).filter(Response.status == "written"),
        )
        .select_from(Response)
        .join(Answer, Response.answer_id == Answer.id)
        .join(Submission, Answer.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .where(CycleParticipant.cycle_id.in_(cycle_ids), taking_part)
        .group_by(CycleParticipant.cycle_id)
    ):
        found[cycle_id] = replace(found.get(cycle_id, Counts()), responses=total, written=written)
    return found


def owe_actions(
    db: Session,
    user: User,
    character: Character,
    amount: int,
    reason: str,
    *,
    source: str | None = None,
    response_id: uuid.UUID | None = None,
) -> OwedAction | None:
    """Record downtime actions the character owes its home troupe, and take them
    from its current cycle if it has not submitted yet. `source` and `response_id`
    say what owes them, where staff applied it from a response
    (horatio.downtime_effects)."""
    if amount <= 0 or character.home_troupe_id is None or character.kind != "pc":
        return None
    debt = OwedAction(
        character_id=character.id,
        troupe_id=character.home_troupe_id,
        action_kind="general",
        amount=amount,
        reason=reason,
        owed_by=user.id,
        source=source,
        response_id=response_id,
    )
    db.add(debt)
    db.flush()
    current = current_participation(db, character)
    if current is not None:
        settle_owed_actions(db, current[1], current[0])
    return debt


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


# --- Quick Hands, Quick Work ------------------------------------------------------------
# A technique (Vol. II Issue 1, p. 76): used in a downtime, it gives two more actions,
# but the character cannot feed, use its own Herd or take Herd from others, and starts
# its next game at half Blood. The player chooses it on the form each cycle, until the
# downtime is submitted. Giving its Herd to others is still allowed: the technique
# stops only the character's own use of what restores Blood.

QUICK_HANDS = ("techniques", "Quick Hands, Quick Work")
QUICK_HANDS_ACTIONS = 2
QUICK_HANDS_NOTE = (
    "No feeding this cycle, and the next game starts at half Blood (Vol. II Issue 1, p. 76)."
)


def has_quick_hands(db: Session, character: Character) -> bool:
    category, name = QUICK_HANDS
    return (
        db.scalar(
            select(CharacterTrait.id)
            .join(TraitDefinition, CharacterTrait.trait_definition_id == TraitDefinition.id)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(
                CharacterTrait.character_id == character.id,
                TraitCategory.key == category,
                TraitDefinition.name == name,
                or_(CharacterTrait.rating.is_(None), CharacterTrait.rating != 0),
            )
            .limit(1)
        )
        is not None
    )


def quick_hands_on(db: Session, participant: CycleParticipant) -> bool:
    return bool(
        db.scalar(select(Submission.quick_hands).where(Submission.participant_id == participant.id))
    )


def extra_lines(db: Session, participant: CycleParticipant) -> list[dict[str, Any]]:
    """Breakdown lines the player's choices this cycle add: Quick Hands, Quick Work."""
    if not quick_hands_on(db, participant):
        return []
    return [
        {
            "action_kind": "general",
            "source": QUICK_HANDS[1],
            "amount": QUICK_HANDS_ACTIONS,
            "note": QUICK_HANDS_NOTE,
        }
    ]


def choose_quick_hands(
    db: Session, character: Character, participant: CycleParticipant, on: bool
) -> None:
    """Use the technique this cycle, or not, until the downtime is submitted."""
    submission = submission_for(db, participant)
    if (submission.quick_hands if submission else False) == on:
        return
    if submission is not None and submission.status == "submitted":
        raise conflict("Quick Hands, Quick Work can only change before the downtime is submitted.")
    if on and not has_quick_hands(db, character):
        raise unprocessable("This character doesn't have Quick Hands, Quick Work.")
    if submission is None:
        submission = Submission(participant_id=participant.id)
        db.add(submission)
    submission.quick_hands = on
    db.flush()


def breakdown(db: Session, participant: CycleParticipant) -> list[dict[str, Any]]:
    """Where the allowance came from: the sheet when the cycle opened, and the
    player's choices this cycle."""
    return [*participant.allowance_breakdown, *extra_lines(db, participant)]


def allowance_totals(db: Session, participant: CycleParticipant) -> dict[str, int]:
    """The allowance with its adjustments, before any is stopped at zero."""
    totals = dict(participant.allowance)
    for line in extra_lines(db, participant):
        totals[line["action_kind"]] = totals.get(line["action_kind"], 0) + line["amount"]
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
    for line in breakdown(db, participant):
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


def closed_to(db: Session, cycle: DowntimeCycle, participant: CycleParticipant) -> str | None:
    """Why the downtime is closed to this participant, though the cycle is open: the
    troupe's absentee downtimes ask for a game attended lately (horatio.game_xp). A
    storyteller's Accept late lets it in anyway."""
    from horatio import game_xp

    if participant.late_accepted_by is not None:
        return None
    return game_xp.downtime_closed(db, cycle, db.get_one(Character, participant.character_id))


def ensure_can_submit(db: Session, cycle: DowntimeCycle, participant: CycleParticipant) -> None:
    if cycle.status != "open":
        raise conflict("This cycle is not open.")
    if now() > cycle.grace_ends_at and participant.late_accepted_by is None:
        raise conflict("The grace period is over. Ask a storyteller to accept a late downtime.")
    closed = closed_to(db, cycle, participant)
    if closed:
        raise conflict(closed)


@dataclass
class AnswerSpec:
    question_id: uuid.UUID
    body: str
    slot: int = 1
    structured: dict[str, Any] | None = None


def influence_part(structured: dict[str, Any] | None) -> dict[str, Any]:
    """An answer's fields that its influence action is checked on: not who it is aimed
    at, nor the project it counts toward."""
    from horatio import projects

    return projects.without_project(targets.without_aim(structured or {}))


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


def answer_keywords(
    db: Session,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    character: Character,
    troupe: Troupe,
) -> tuple[keywords.Context, list[keywords.Keyword]]:
    """What decides the keywords the character is offered, and the troupe's keywords."""
    show = feeding.shown(troupe)
    feeds = (
        show.tracked
        and not show.rack
        and feeding.participant_basis(db, participant, character, cycle).get("clan") is not None
    )
    return keywords.context(db, character, troupe, feeds), keywords.troupe_keywords(db, troupe.id)


def keywords_feed(
    answer: feeding.FeedingAnswer,
    before: feeding.FeedingAnswer,
    fed: keywords.Fed,
    show: feeding.Shown,
) -> bool:
    """The Feeding section with the actions, territory and patrols the Feed and Patrol
    answers give, in place of the section's own. Once they are gone, so are what they
    gave. Whether answers give any of it, now or before."""
    had = list(before.from_keywords)
    parts: list[str] = []
    if fed.actions is not None:
        answer.actions = fed.actions
        if show.territories:
            answer.territory = fed.territory or ""
        parts.append("actions")
    elif "actions" in had:
        answer.actions = 0
        if show.territories:
            answer.territory = ""
    if fed.patrols is not None and show.territories:
        answer.patrols = [feeding.Patrol(t, n) for t, n in fed.patrols.items()]
        parts.append("patrols")
    elif "patrols" in had:
        answer.patrols = []
    answer.from_keywords = parts
    return bool(parts or had)


def save_answers(
    db: Session,
    player: User,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    specs: Sequence[AnswerSpec],
    feeding_answer: feeding.FeedingAnswer | None = None,
    quick_hands: bool | None = None,
) -> Submission:
    """Replace the character's answers, and its Feeding section when given one.
    Blank answers are dropped, but for a Quest action that names its quest. Feeding
    actions come out of the general actions. An action aimed at someone whose Haven
    has Location costs two (horatio.targets). `quick_hands` uses Quick Hands, Quick
    Work this cycle, or not; left out, it stays as it was."""
    from horatio import projects, quest_actions

    ensure_can_submit(db, cycle, participant)
    suspensions.refuse_character(db, character)
    if quick_hands is not None:
        choose_quick_hands(db, character, participant, quick_hands)
    using_quick_hands = quick_hands_on(db, participant)
    allowance_now = effective_allowance(db, participant)
    shown = {q.id: q for q in visible_questions(db, cycle, character, allowance_now)}

    submission = submission_for(db, participant)
    before_now = answers_for(db, submission) if submission else []
    existing = {(a.question_id, a.slot): a for a in before_now}
    standings: dict[influence.InfluenceType, influence.Standing] | None = None

    feeding_before = feeding.answer_of(submission)
    troupe = db.get_one(Troupe, cycle.troupe_id)
    tracked = feeding.tracked(troupe)
    show = feeding.shown(troupe)

    def names_quest(spec: AnswerSpec) -> bool:
        question = shown.get(spec.question_id)
        return question is not None and question.kind == "quest" and bool(spec.structured)

    kept = [s for s in specs if s.body.strip() or names_quest(s)]
    # Each answer's keyword and its fields (horatio.keywords), checked first: Feed and
    # Patrol answers make the Feeding section's actions and patrols.
    ctx, keyword_list = answer_keywords(db, cycle, participant, character, troupe)
    by_key = keywords.by_key(keyword_list)
    owed = {o.id: o for o in keywords.learning_owed(db, participant.id)}
    checked: dict[tuple[uuid.UUID, int], keywords.Checked] = {}
    confirmed: set[str] = set()
    for spec in kept:
        question = shown.get(spec.question_id)
        if question is None or question.kind != "action":
            continue
        before = existing.get((spec.question_id, spec.slot))
        spec.structured, found = keywords.check_answer(
            db, by_key, ctx, question, spec.structured or {}, before, owed
        )
        owed_id = spec.structured.get(keywords.OWED)
        if owed_id is not None:
            if owed_id in confirmed:
                raise unprocessable("Each thing learned is one Learn action.")
            confirmed.add(owed_id)
        checked[(spec.question_id, spec.slot)] = found
    from_answers = keywords.feeding_from(
        [
            (c.keyword, s.structured or {})
            for s in kept
            if (c := checked.get((s.question_id, s.slot)))
        ]
    )

    if feeding_answer is None or not tracked:
        # A troupe that doesn't track feeding keeps what was entered before, for when
        # it switches feeding on again, and its actions count for nothing.
        feeding_answer = feeding_before
    else:
        # What a rule that is off would set stays as it was; Horatio alone throws the hunt.
        feeding_answer.hunt = feeding_before.hunt
        if not show.resonance:
            feeding_answer.resonance = feeding_before.resonance
        if not show.territories:
            feeding_answer.territory = feeding_before.territory
            feeding_answer.patrols = feeding_before.patrols
    derived = (
        tracked
        and not show.rack
        and keywords_feed(feeding_answer, feeding_before, from_answers, show)
    )
    if derived or feeding_answer is not feeding_before:
        feeding.check_answer(
            db,
            cycle,
            character,
            feeding.participant_basis(db, participant, character, cycle),
            feeding_answer,
            quick_hands=using_quick_hands,
        )
    # Feeding actions and patrols come out of the general actions, but for those Feed and
    # Patrol answers give, which spend their own; with the Rack, a vessel stands in for
    # feeding actions.
    fed = (
        feeding_answer.actions
        if tracked and not show.rack and "actions" not in feeding_answer.from_keywords
        else 0
    )
    fed += (
        feeding_answer.patrolling
        if show.territories and "patrols" not in feeding_answer.from_keywords
        else 0
    )
    used: dict[str, int] = {"general": fed}
    if fed > allowance_now.get("general", 0):
        raise unprocessable(
            f"That is more {'feeding and patrol' if show.territories else 'feeding'} actions "
            f"than the {allowance_now.get('general', 0)} "
            "downtime actions this character has."
        )
    per_question: dict[uuid.UUID, int] = {}
    # Actions of each kind that cost two, aimed at someone whose Haven has Location.
    doubled: dict[str, int] = {}
    seen: set[tuple[uuid.UUID, int]] = set()
    chosen_quests: set[uuid.UUID] = set()
    counters = 0
    # Whose Havens have Location, of everyone the answers are aimed at.
    located = targets.with_location(
        db, cycle.troupe_id, {t for s in kept for t in targets.aimed_at(s.structured or {})}
    )
    for spec in kept:
        question = shown.get(spec.question_id)
        if question is None:
            raise unprocessable("That question is not on this character's form.")
        if (spec.question_id, spec.slot) in seen or spec.slot < 1:
            raise unprocessable(f"{question.prompt!r}: each answer needs its own slot, from 1.")
        seen.add((spec.question_id, spec.slot))
        check_answer(question, spec)
        before = existing.get((spec.question_id, spec.slot))
        spec.structured = targets.check(
            db, character, cycle, question, spec.structured or {}, before
        )
        spec.structured = projects.check_answer(
            db, character, cycle, question, spec.structured, before
        )
        found = checked.get((spec.question_id, spec.slot))
        counters += targets.counter_of(spec.structured) is not None or bool(
            found and found.keyword and found.keyword.computers_only
        )
        if counters > 1:
            raise unprocessable(
                "The Computer skill cancels or observes one action a cycle (MET: VTM p. 93)."
            )
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
            changed = before is None or influence_part(spec.structured) != influence_part(
                before.structured
            )
            if influence_type is not None and changed:
                # Checked when it changes, so a rating lowered since does not lock it.
                standings = standings or influence.standings(db, character)
                influence.check_answer(
                    standings[influence_type], question.prompt, spec.structured or {}
                )
            # Staff's word that it isn't against them holds while it is aimed as it was.
            not_against = (
                before is not None
                and before.not_against
                and targets.aiming(before.structured) == targets.aiming(spec.structured)
            )
            base = found.cost if found is not None else 1
            cost = base * targets.cost(spec.structured, not_against, located)
            doubled[kind] = doubled.get(kind, 0) + (cost > base)
            used[kind] = used.get(kind, 0) + cost
            if used[kind] > allowance_now.get(kind, 0):
                feeding_spent = fed if kind == "general" else 0
                raise unprocessable(
                    f"That is more {kind.replace('_', ' ')} actions than the "
                    f"{allowance_now.get(kind, 0)} this character has"
                    + (
                        f", with {feeding_spent} spent feeding"
                        + (" or patrolling" if show.territories else "")
                        if feeding_spent
                        else ""
                    )
                    + (
                        f", and {doubled[kind]} that "
                        + ("costs" if doubled[kind] == 1 else "cost")
                        + " 2 actions"
                        if doubled[kind]
                        else ""
                    )
                    + "."
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
    aimed_anew: list[Answer] = []
    for spec in kept:
        answer = existing.get((spec.question_id, spec.slot))
        if answer is None:
            answer = Answer(
                submission_id=submission.id, question_id=spec.question_id, slot=spec.slot
            )
            db.add(answer)
        answer.body = spec.body.strip()
        aimed_before = targets.aiming(answer.structured or {})
        answer.structured = spec.structured or {}
        if targets.aiming(answer.structured) != aimed_before:
            # Aimed anew, it is judged anew: staff's word on it no longer stands.
            answer.not_against = False
            answer.paired_answer_id = None
            if submission.status == "submitted":
                aimed_anew.append(answer)
    submission.feeding = feeding_answer.stored()
    # When the player last saved, for staff chasing downtimes: a change to the
    # answers alone would leave the submission's own row, and its time, as it was.
    submission.updated_at = now()
    db.flush()
    responses.sync_responses(db, submission)
    if submission.status == "submitted":
        quest_actions.join_chosen(db, player, character, submission)
        for answer in aimed_anew:
            targets.log(db, player, character, cycle, shown[answer.question_id], answer)
    return submission


def keyword_gaps(
    db: Session,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
    character: Character,
    submission: Submission | None,
    allowance_now: dict[str, int],
) -> list[str]:
    """What the answers' keywords ask for that they don't give yet, and the keywords
    the character must take each cycle that no answer has (horatio.keywords)."""
    troupe = db.get_one(Troupe, cycle.troupe_id)
    ctx, keyword_list = answer_keywords(db, cycle, participant, character, troupe)
    by_key = keywords.by_key(keyword_list)
    questions = {q.id: q for q in visible_questions(db, cycle, character, allowance_now)}
    answers = answers_for(db, submission) if submission else []
    gaps: list[str] = []
    for answer in answers:
        key = keywords.keyword_of(answer.structured)
        keyword = by_key.get(key) if key else None
        if keyword is None:
            continue
        lacking = keywords.missing(keyword, answer.structured, ctx)
        if lacking:
            gaps.append(f"say {' and '.join(lacking)} for your {keyword.name} action")
    taken = {keywords.keyword_of(a.structured) for a in answers}
    for keyword in keywords.required_now(keyword_list, ctx):
        if keyword.key in taken:
            continue
        if any(keywords.fits(keyword, q, ctx) for q in questions.values()):
            gaps.append(f"add a {keyword.name} action, which {ctx.age}s take each cycle")
    return gaps


def submit(
    db: Session,
    player: User,
    character: Character,
    cycle: DowntimeCycle,
    participant: CycleParticipant,
) -> Submission:
    """Submit the downtime, joining the party of each quest its Quest actions name."""
    from horatio import quest_actions

    ensure_can_submit(db, cycle, participant)
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
    gaps = keyword_gaps(db, cycle, participant, character, submission, allowance_now)
    if gaps:
        raise unprocessable("Before you submit: " + "; ".join(gaps) + ".")
    if submission is None:
        submission = Submission(participant_id=participant.id)
        db.add(submission)
    resubmitted = submission.status == "submitted"
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
    if not resubmitted:
        # Changed after, an answer is noted as it is saved.
        targets.log_submission(db, player, character, cycle, submission)
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
