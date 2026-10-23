"""Answering downtimes: assignment, responses, fill tables and delivery.

Every answer in a submitted downtime gets a response. Storytellers and
assistant storytellers assign each one to a staff member or to any narrator,
and can write any response themselves. A narrator writes only responses
assigned to them, can accept one assigned to any narrator (it then becomes
theirs), and can decline one, which sends it back unassigned. Narrators see
the question, the player's answer and the character's name, never the sheet.

Delivery sends a submission's written responses to its player, once per
channel. The only channel today is Horatio itself: the player reads the
results in the app. Discord and email need credentials and come later.
"""

import random
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, delivery, feeding
from horatio.models import (
    Answer,
    Character,
    CycleParticipant,
    Delivery,
    DowntimeCycle,
    Question,
    RandomTable,
    Response,
    Submission,
    Troupe,
    TroupeStaff,
    User,
)
from horatio.notifications import notify
from horatio.permissions import Role, troupe_role
from horatio.sheets import conflict, unprocessable

RUNNING = (Role.LEAD_STORYTELLER, Role.STORYTELLER, Role.ASSISTANT_STORYTELLER)


def now() -> datetime:
    return datetime.now(UTC)


# --- keeping responses in step with answers ---------------------------------------------


def sync_responses(db: Session, submission: Submission) -> None:
    """Give every answer of a submitted downtime a response."""
    if submission.status != "submitted":
        return
    answers = db.scalars(select(Answer).where(Answer.submission_id == submission.id))
    for answer in answers:
        if db.scalar(select(Response.id).where(Response.answer_id == answer.id)) is None:
            db.add(Response(answer_id=answer.id))
    db.flush()


def written_answer_ids(db: Session, submission: Submission) -> set[uuid.UUID]:
    """Answers whose responses are written, which the player can no longer change."""
    return set(
        db.scalars(
            select(Answer.id)
            .join(Response, Response.answer_id == Answer.id)
            .where(Answer.submission_id == submission.id, Response.status == "written")
        )
    )


def drop_unwritten_responses(db: Session, answer_ids: set[uuid.UUID]) -> None:
    for response in db.scalars(select(Response).where(Response.answer_id.in_(answer_ids))):
        db.delete(response)
    db.flush()


# --- the work list ----------------------------------------------------------------------


@dataclass
class WorkItem:
    response: Response
    answer: Answer
    question: Question
    character: Character
    cycle: DowntimeCycle


def work_items(db: Session, cycle: DowntimeCycle) -> list[WorkItem]:
    rows = db.execute(
        select(Response, Answer, Question, Character)
        .join(Answer, Response.answer_id == Answer.id)
        .join(Question, Answer.question_id == Question.id)
        .join(Submission, Answer.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None))
        .order_by(Character.name, Question.position, Answer.slot)
    )
    return [WorkItem(r, a, q, c, cycle) for r, a, q, c in rows]


def item_for(db: Session, response_id: uuid.UUID) -> WorkItem | None:
    row = db.execute(
        select(Response, Answer, Question, Character, DowntimeCycle)
        .join(Answer, Response.answer_id == Answer.id)
        .join(Question, Answer.question_id == Question.id)
        .join(Submission, Answer.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .join(DowntimeCycle, CycleParticipant.cycle_id == DowntimeCycle.id)
        .where(Response.id == response_id)
    ).first()
    return WorkItem(*row) if row else None


def is_running(db: Session, user: User, troupe: Troupe) -> bool:
    return user.is_custodian or troupe_role(db, user, troupe) in RUNNING


def mine(db: Session, user: User, cycle: DowntimeCycle) -> list[WorkItem]:
    """What `user` is to write in this cycle, plus the any-narrator pool for narrators."""
    troupe = db.get_one(Troupe, cycle.troupe_id)
    narrator = troupe_role(db, user, troupe) == Role.NARRATOR
    return [
        item
        for item in work_items(db, cycle)
        if item.response.assigned_to_user_id == user.id
        or (narrator and item.response.assigned_to_any_narrator)
    ]


# --- assigning and writing --------------------------------------------------------------


def assign(
    db: Session,
    staff: User,
    item: WorkItem,
    troupe: Troupe,
    user_id: uuid.UUID | None,
    any_narrator: bool,
) -> None:
    if user_id is not None and any_narrator:
        raise unprocessable("Assign to one staff member or to any narrator, not both.")
    if user_id is not None and user_id != troupe.lead_user_id:
        on_staff = db.scalar(
            select(TroupeStaff.id).where(
                TroupeStaff.troupe_id == troupe.id, TroupeStaff.user_id == user_id
            )
        )
        if on_staff is None:
            raise unprocessable("Responses can only be assigned to this troupe's staff.")
    response = item.response
    response.assigned_to_user_id = user_id
    response.assigned_to_any_narrator = any_narrator
    response.assigned_by = staff.id
    if response.status != "written":
        response.status = "assigned" if (user_id or any_narrator) else "unassigned"
    db.flush()
    audit.record(
        db,
        staff,
        "response.assigned",
        troupe_id=troupe.id,
        character_id=item.character.id,
        response_id=response.id,
        to_user_id=user_id,
        any_narrator=any_narrator,
    )


def accept(db: Session, narrator: User, item: WorkItem, troupe: Troupe) -> None:
    if not item.response.assigned_to_any_narrator:
        raise conflict("Only responses assigned to any narrator can be accepted.")
    item.response.assigned_to_any_narrator = False
    item.response.assigned_to_user_id = narrator.id
    db.flush()
    audit.record(
        db,
        narrator,
        "response.accepted",
        troupe_id=troupe.id,
        character_id=item.character.id,
        response_id=item.response.id,
    )


def decline(db: Session, narrator: User, item: WorkItem, troupe: Troupe) -> None:
    """Send it back to the storytellers and assistant storytellers to reassign."""
    if item.response.assigned_to_user_id != narrator.id:
        raise conflict("You can only decline responses assigned to you.")
    if item.response.status == "written":
        raise conflict("This response is already written.")
    item.response.assigned_to_user_id = None
    item.response.status = "unassigned"
    db.flush()
    audit.record(
        db,
        narrator,
        "response.declined",
        troupe_id=troupe.id,
        character_id=item.character.id,
        response_id=item.response.id,
    )


def can_write(db: Session, user: User, item: WorkItem, troupe: Troupe) -> bool:
    return is_running(db, user, troupe) or item.response.assigned_to_user_id == user.id


def write(db: Session, staff: User, item: WorkItem, troupe: Troupe, body: str) -> None:
    if not can_write(db, staff, item, troupe):
        raise conflict("This response is not assigned to you.")
    if item.cycle.status == "complete":
        raise conflict("This cycle is complete.")
    response = item.response
    if delivered(db, item.answer.submission_id):
        raise conflict("These results have already been delivered.")
    response.body = body.strip()
    if response.body:
        response.status = "written"
        response.written_by = staff.id
        response.written_at = now()
    else:
        response.status = (
            "assigned"
            if response.assigned_to_user_id or response.assigned_to_any_narrator
            else "unassigned"
        )
        response.written_by = None
        response.written_at = None
    db.flush()
    audit.record(
        db,
        staff,
        "response.written",
        troupe_id=troupe.id,
        character_id=item.character.id,
        response_id=response.id,
        length=len(response.body),
    )


# --- fill tables ------------------------------------------------------------------------

PLACEHOLDER = re.compile(r"\[([^\[\]]+)\]")


def roll(
    tables: dict[str, list[str]], name: str, rng: random.Random | None = None, depth: int = 0
) -> str:
    """A random entry from table `name`, with any "[Other Table]" placeholders
    filled from those tables. Placeholders naming no table are left as written."""
    rng = rng or random.Random()
    entries = tables.get(name.lower())
    if not entries:
        raise unprocessable(f"The {name!r} table has no entries.")
    text = rng.choice(entries)
    if depth >= 5:
        return text

    def fill(match: re.Match[str]) -> str:
        other = match.group(1)
        if other.lower() not in tables or not tables[other.lower()]:
            return match.group(0)
        return roll(tables, other, rng, depth + 1)

    return PLACEHOLDER.sub(fill, text)


def troupe_tables(db: Session, troupe: Troupe) -> dict[str, list[str]]:
    return {
        t.name.lower(): t.entries
        for t in db.scalars(select(RandomTable).where(RandomTable.troupe_id == troupe.id))
    }


# --- delivery ---------------------------------------------------------------------------


def delivered(db: Session, submission_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Delivery.id).where(
                Delivery.submission_id == submission_id,
                Delivery.channel == "horatio",
                Delivery.status == "sent",
                Delivery.test_mode.is_(False),
            )
        )
        is not None
    )


def compose(db: Session, cycle: DowntimeCycle, character: Character, submission: Submission) -> str:
    """The message a player receives: the answer to their feeding, then each answered
    question, what they did, and the result."""
    rows = db.execute(
        select(Question, Answer, Response)
        .join(Answer, Answer.question_id == Question.id)
        .join(Response, Response.answer_id == Answer.id)
        .where(Answer.submission_id == submission.id, Response.status == "written")
        .order_by(Question.position, Answer.slot)
    )
    parts = [f"**Downtime results for {character.name} ({cycle.name})**"]
    fed = feeding.compose(db, submission)
    if fed is not None:
        parts.append(fed)
    for question, answer, response in rows:
        parts.append(
            f"**{question.prompt}**\n*Your action:* {answer.body}\n*Result:* {response.body}"
        )
    return "\n\n".join(parts)


def deliver_cycle(
    db: Session, staff: User, cycle: DowntimeCycle, troupe: Troupe
) -> tuple[int, int]:
    """Deliver every submission that has written responses: in Horatio, where it
    was not delivered already, and queued on each of the troupe's connectors that
    has nothing for it yet. Returns how many were delivered in Horatio, and how
    many deliveries were queued on connectors."""
    if cycle.status not in ("closed", "complete"):
        raise conflict("Close the cycle before delivering results.")
    rows = db.execute(
        select(Submission, Character)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.removed_at.is_(None),
            Submission.status == "submitted",
        )
    )
    connectors = delivery.enabled_connectors(db, troupe.id)
    count = queued = 0
    for submission, character in rows:
        has_written = db.scalar(
            select(Response.id)
            .join(Answer, Response.answer_id == Answer.id)
            .where(Answer.submission_id == submission.id, Response.status == "written")
            .limit(1)
        )
        if has_written is None and submission.feeding_result is None:
            continue
        message = compose(db, cycle, character, submission)
        queued += delivery.queue(db, staff, connectors, cycle, character, submission, message)
        if delivered(db, submission.id):
            continue
        feeding.mark_half_blood(db, character, submission)
        db.add(
            Delivery(
                submission_id=submission.id,
                channel="horatio",
                status="sent",
                message=message,
                sent_by=staff.id,
                sent_at=now(),
                attempts=1,
            )
        )
        notify(
            db,
            [character.player_id],
            "downtime.delivered",
            f"Downtime results for {character.name} ({cycle.name}) are ready.",
            f"/characters/{character.id}/results",
            troupe_id=troupe.id,
            character_id=character.id,
        )
        count += 1
    db.flush()
    audit.record(
        db,
        staff,
        "downtime.delivered",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        count=count,
        queued=queued,
    )
    return count, queued


def complete_cycle(db: Session, staff: User, cycle: DowntimeCycle) -> None:
    if cycle.status != "closed":
        raise conflict("Only a closed cycle can be completed.")
    cycle.status = "complete"
    db.flush()
    audit.record(
        db, staff, "downtime.cycle_completed", troupe_id=cycle.troupe_id, cycle_id=cycle.id
    )
