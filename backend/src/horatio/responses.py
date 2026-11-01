"""Answering downtimes: assignment, responses, fill tables and delivery.

Every answer in a submitted downtime gets a response. Storytellers and
assistant storytellers assign each one to a staff member or to any narrator,
and can write any response themselves. A narrator writes only responses
assigned to them, can accept one assigned to any narrator (it then becomes
theirs), and can decline one, which sends it back unassigned. Narrators see
the question, the player's answer and the character's name, never the sheet.

Delivery sends a submission's written responses to its player: in Horatio, and
on each connector the troupe has on (horatio.delivery). By default only
downtimes with every response written go. Responses can still be written or
changed once delivered; the downtime then shows as changed, and the next
delivery sends it again as an update.
"""

import random
import re
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
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


def work_items(
    db: Session, cycle: DowntimeCycle, response_ids: Collection[uuid.UUID] | None = None
) -> list[WorkItem]:
    """The cycle's responses, by character; with `response_ids`, only those of them."""
    query = (
        select(Response, Answer, Question, Character)
        .join(Answer, Response.answer_id == Answer.id)
        .join(Question, Answer.question_id == Question.id)
        .join(Submission, Answer.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None))
        .order_by(Character.name, Question.position, Answer.slot)
    )
    if response_ids is not None:
        query = query.where(Response.id.in_(response_ids))
    return [WorkItem(r, a, q, c, cycle) for r, a, q, c in db.execute(query)]


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


def unwritten(
    db: Session, user: User, cycle_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """For each cycle, the responses still to write: assigned to `user`, and open
    to any narrator. One query for all of them; a cycle with neither is left out."""
    rows = db.execute(
        select(
            CycleParticipant.cycle_id,
            func.count(Response.id).filter(Response.assigned_to_user_id == user.id),
            func.count(Response.id).filter(Response.assigned_to_any_narrator),
        )
        .select_from(Response)
        .join(Answer, Response.answer_id == Answer.id)
        .join(Submission, Answer.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .where(
            CycleParticipant.cycle_id.in_(cycle_ids),
            CycleParticipant.removed_at.is_(None),
            Response.status != "written",
        )
        .group_by(CycleParticipant.cycle_id)
    )
    return {cycle_id: (yours, pool) for cycle_id, yours, pool in rows if yours or pool}


# --- assigning and writing --------------------------------------------------------------


def check_assignee(
    db: Session, troupe: Troupe, user_id: uuid.UUID | None, any_narrator: bool
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


def assign(
    db: Session,
    staff: User,
    item: WorkItem,
    troupe: Troupe,
    user_id: uuid.UUID | None,
    any_narrator: bool,
) -> None:
    check_assignee(db, troupe, user_id, any_narrator)
    assign_checked(db, staff, item, troupe, user_id, any_narrator)


def assign_many(
    db: Session,
    staff: User,
    items: list[WorkItem],
    troupe: Troupe,
    user_id: uuid.UUID | None,
    any_narrator: bool,
) -> None:
    """Assign several responses to one staff member (or any narrator, or no one) at
    once: the staff member is checked once, and each is assigned as `assign` does."""
    check_assignee(db, troupe, user_id, any_narrator)
    for item in items:
        assign_checked(db, staff, item, troupe, user_id, any_narrator)


def assign_checked(
    db: Session,
    staff: User,
    item: WorkItem,
    troupe: Troupe,
    user_id: uuid.UUID | None,
    any_narrator: bool,
) -> None:
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


def last_delivery(db: Session, submission_id: uuid.UUID) -> Delivery | None:
    """The submission's latest delivery in Horatio: the results its player reads."""
    return db.scalar(
        select(Delivery)
        .where(
            Delivery.submission_id == submission_id,
            Delivery.channel == "horatio",
            Delivery.status == "sent",
            Delivery.test_mode.is_(False),
        )
        .order_by(Delivery.revision.desc())
        .limit(1)
    )


def delivered(db: Session, submission_id: uuid.UUID) -> bool:
    return last_delivery(db, submission_id) is not None


HEADING = "**Downtime results for "
UPDATED_HEADING = "**Updated downtime results for "


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
    parts = [f"{HEADING}{character.name} ({cycle.name})**"]
    fed = feeding.compose(db, submission)
    if fed is not None:
        parts.append(fed)
    for question, answer, response in rows:
        parts.append(
            f"**{question.prompt}**\n*Your action:* {answer.body}\n*Result:* {response.body}"
        )
    return "\n\n".join(parts)


def as_update(message: str) -> str:
    """The results, headed as an update, for a channel that had them before."""
    return message.replace(HEADING, UPDATED_HEADING, 1) if message.startswith(HEADING) else message


@dataclass
class Readiness:
    """Where one submitted downtime stands for delivery."""

    submission: Submission
    character: Character
    # Responses written, with the feeding answer for a character who feeds, of all
    # there are to write.
    answered: int
    to_answer: int
    # Its latest delivery in Horatio, if it has had one; and whether the results
    # would read differently now, from responses written or changed since.
    last: Delivery | None
    changed: bool

    @property
    def finished(self) -> bool:
        return self.answered == self.to_answer

    @property
    def due(self) -> bool:
        """Something its player has not had: first results, or a change since."""
        return self.changed if self.last is not None else self.answered > 0


def readiness(db: Session, cycle: DowntimeCycle) -> list[Readiness]:
    """Each submitted downtime in the cycle, by character name, and how ready it is."""
    rows = db.execute(
        select(Submission, CycleParticipant, Character)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.removed_at.is_(None),
            Submission.status == "submitted",
        )
        .order_by(Character.name)
    ).all()
    ids = [s.id for s, _, _ in rows]
    counts = {
        submission_id: (total, written)
        for submission_id, total, written in db.execute(
            select(
                Answer.submission_id,
                func.count(Response.id),
                func.count(Response.id).filter(Response.status == "written"),
            )
            .join(Response, Response.answer_id == Answer.id)
            .where(Answer.submission_id.in_(ids))
            .group_by(Answer.submission_id)
        )
    }
    lasts: dict[uuid.UUID, Delivery] = {}
    for d in db.scalars(
        select(Delivery)
        .where(
            Delivery.submission_id.in_(ids),
            Delivery.channel == "horatio",
            Delivery.status == "sent",
            Delivery.test_mode.is_(False),
        )
        .order_by(Delivery.revision)
    ):
        assert d.submission_id is not None
        lasts[d.submission_id] = d
    found: list[Readiness] = []
    for submission, participant, character in rows:
        total, written = counts.get(submission.id, (0, 0))
        fed = submission.feeding_result is not None
        feeds = fed or feeding.participant_basis(db, participant, character, cycle).get("clan")
        last = lasts.get(submission.id)
        found.append(
            Readiness(
                submission=submission,
                character=character,
                answered=written + fed,
                to_answer=total + bool(feeds),
                last=last,
                changed=last is not None
                and compose(db, cycle, character, submission) != last.message,
            )
        )
    return found


def up_to_date(
    db: Session, cycle: DowntimeCycle, character: Character, submission: Submission
) -> bool:
    """Whether the player has the submission's results as they stand."""
    last = last_delivery(db, submission.id)
    return last is not None and last.message == compose(db, cycle, character, submission)


@dataclass
class Delivered:
    # Delivered in Horatio, how many of those as updates, and how many deliveries
    # were queued on connectors.
    delivered: int = 0
    updated: int = 0
    queued: int = 0


def deliver_cycle(
    db: Session, staff: User, cycle: DowntimeCycle, troupe: Troupe, *, partial: bool = False
) -> Delivered:
    """Deliver each submission with something new for its player: every one whose
    responses are all written (and, with `partial`, those partly answered too),
    for the first time, or again as an update if responses were written or
    changed since. Each goes out in Horatio and is queued on each of the troupe's
    connectors that has not had it; with them go the quest results recorded
    through the cycle (horatio.quest_actions)."""
    from horatio import quest_actions

    if cycle.status not in ("closed", "complete"):
        raise conflict("Close the cycle before delivering results.")
    connectors = delivery.enabled_connectors(db, troupe.id)
    done = Delivered()
    for ready in readiness(db, cycle):
        submission, character, last = ready.submission, ready.character, ready.last
        if ready.due and (ready.finished or partial):
            message = compose(db, cycle, character, submission)
            revision = last.revision + 1 if last is not None else 1
            # A feeding answer new to the player sets their Blood at the next game.
            fed = feeding.compose(db, submission)
            if fed is not None and (last is None or fed not in last.message):
                feeding.mark_half_blood(db, character, submission)
            db.add(
                Delivery(
                    submission_id=submission.id,
                    channel="horatio",
                    revision=revision,
                    status="sent",
                    message=message,
                    sent_by=staff.id,
                    sent_at=now(),
                    attempts=1,
                )
            )
            news = "have been updated" if last is not None else "are ready"
            notify(
                db,
                [character.player_id],
                "downtime.delivered",
                f"Downtime results for {character.name} ({cycle.name}) {news}.",
                f"/characters/{character.id}/results",
                troupe_id=troupe.id,
                character_id=character.id,
            )
            done.delivered += 1
            done.updated += last is not None
        elif last is not None:
            # Nothing new; a connector switched on since still gets what was sent.
            message, revision = last.message, last.revision
        else:
            continue
        done.queued += delivery.queue(
            db,
            staff,
            connectors,
            cycle,
            character,
            submission,
            message,
            as_update(message),
            revision,
        )
    db.flush()
    quest_actions.deliver(db, staff, cycle)
    audit.record(
        db,
        staff,
        "downtime.delivered",
        troupe_id=troupe.id,
        cycle_id=cycle.id,
        count=done.delivered,
        updated=done.updated,
        queued=done.queued,
    )
    return done


def complete_cycle(db: Session, staff: User, cycle: DowntimeCycle) -> None:
    if cycle.status != "closed":
        raise conflict("Only a closed cycle can be completed.")
    cycle.status = "complete"
    db.flush()
    audit.record(
        db, staff, "downtime.cycle_completed", troupe_id=cycle.troupe_id, cycle_id=cycle.id
    )
