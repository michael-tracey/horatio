"""The Quest action: quests in downtime (CONTEXT.md: Quest Action; MET: VTM Vol. II
Issue 1, p. 102).

**A troupe's form asks it** once quests are on: a question of the kind `quest`, added
to each new cycle's form. It spends an action of the kind its `action_kind` names:
general unless the troupe chooses another, such as a quest allowance of its own made
with the allowance rules.

**The player picks one quest** their character can take part in: one it leads or is
in, one shared with it, one posted to the troupe, one it unlocked. Only the cycle's
troupe's quests, still under way. The answer keeps the quest and the scenario the
party faces next (`{"quest_id": ..., "scenario": n}`). Submitting it joins the party
if the character is not in it yet.

**Staff answer it** like any response, beside the quest: its scenario, its
requirements, and who else put in an action for it. For a Complex or Epic quest each
participant spends a downtime action before each scenario (Nothing's Simple, p. 102),
so a party member with no Quest action that cycle shows as not having spent one;
staff decide what follows. Staff record the scenario's result once, and it becomes
the response for every member's Quest action on that scenario in the cycle.

**It goes out with the cycle's delivery**, in the downtime results of those who put
in an action, and as a quest's news (horatio.quests) to the rest of the party, never
on its own. A result recorded at a game goes out at once (horatio.quests).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, quests, responses
from horatio.models import (
    Answer,
    Character,
    CycleParticipant,
    DowntimeCycle,
    Quest,
    Question,
    QuestScenario,
    Response,
    Submission,
    Troupe,
    User,
)
from horatio.sheets import conflict, unprocessable

# How a character stands with a quest it may choose: in the party, or able to join.
TAKES_PART = ("leader", "joined", "invited", "offered")


def now() -> datetime:
    return datetime.now(UTC)


def quest_id_of(structured: dict[str, Any]) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(structured["quest_id"]))
    except (KeyError, ValueError):
        return None


def choices(
    db: Session, character: Character, cycle: DowntimeCycle
) -> list[tuple[Quest, quests.Role_]]:
    """The quests the character can choose in this cycle: the cycle's troupe's, under
    way, that it leads, is in, or may join."""
    troupe = db.get(Troupe, cycle.troupe_id)
    if troupe is None or not troupe.quests_enabled:
        return []
    return [
        (q, role)
        for q, role in quests.visible_quests(db, character)
        if q.troupe_id == cycle.troupe_id and q.status == "active" and role in TAKES_PART
    ]


def check_answer(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    question: Question,
    structured: dict[str, Any],
    before: Answer | None,
    chosen: set[uuid.UUID],
) -> tuple[dict[str, Any], Quest]:
    """A Quest action's answer as it is kept: the quest it names, which the character
    must be able to take part in, and the scenario the party faces next. One it
    already had is not checked again; it moves on to the next scenario if the one it
    was for has passed since, unless it is already answered."""
    quest_id = quest_id_of(structured)
    quest = db.get(Quest, quest_id) if quest_id else None
    if quest is None:
        raise unprocessable(f"{question.prompt!r}: choose a quest.")
    if quest.id in chosen:
        raise unprocessable(f"{quest.name} is already chosen in another Quest action.")
    chosen.add(quest.id)
    if before is not None and quest_id_of(before.structured) == quest.id:
        kept = dict(before.structured)
        answered = db.scalar(
            select(Response.id).where(Response.answer_id == before.id, Response.status == "written")
        )
        current = quests.current_scenario(db, quest) if quest.status == "active" else None
        if answered is None and current is not None:
            kept["scenario"] = current.number
        return kept, quest
    if quest.id not in {q.id for q, _ in choices(db, character, cycle)}:
        raise unprocessable(f"{character.name} cannot take part in {quest.name}.")
    scenario = quests.current_scenario(db, quest)
    if scenario is None:
        raise unprocessable(f"{quest.name} has no scenario left to face.")
    return {"quest_id": str(quest.id), "scenario": scenario.number}, quest


def join_chosen(db: Session, user: User, character: Character, submission: Submission) -> None:
    """On submitting: join the party of each quest the character's Quest actions name,
    where it is not in it yet."""
    rows = db.scalars(
        select(Answer)
        .join(Question, Answer.question_id == Question.id)
        .where(Answer.submission_id == submission.id, Question.kind == "quest")
    )
    for answer in rows:
        quest_id = quest_id_of(answer.structured)
        quest = db.get(Quest, quest_id) if quest_id else None
        if quest is None or quest.status != "active":
            continue
        if quests.role_of(db, quest, character) in ("invited", "offered"):
            quests.join(db, user, quest, character)


# --- what staff see ------------------------------------------------------------------------


@dataclass
class Action:
    character: Character
    answer: Answer
    response: Response | None

    @property
    def scenario(self) -> int | None:
        found = self.answer.structured.get("scenario")
        return found if isinstance(found, int) else None


def actions(db: Session, quest: Quest, cycle: DowntimeCycle) -> list[Action]:
    """The submitted Quest actions naming this quest in the cycle, by character."""
    rows = db.execute(
        select(Answer, Character, Response)
        .join(Question, Answer.question_id == Question.id)
        .join(Submission, Answer.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .join(Character, CycleParticipant.character_id == Character.id)
        .outerjoin(Response, Response.answer_id == Answer.id)
        .where(
            Question.cycle_id == cycle.id,
            Question.kind == "quest",
            Submission.status == "submitted",
            CycleParticipant.removed_at.is_(None),
            Answer.structured["quest_id"].astext == str(quest.id),
        )
        .order_by(Character.name)
    )
    return [Action(c, a, r) for a, c, r in rows]


def not_spent(db: Session, quest: Quest, cycle: DowntimeCycle) -> list[Character]:
    """For a Complex or Epic quest, its party's player characters who put in no Quest
    action for it this cycle (Nothing's Simple, p. 102). Staff decide what follows."""
    if quest.category == "simple":
        return []
    acted = {a.character.id for a in actions(db, quest, cycle)}
    return [c for c in quests.party(db, quest) if c.kind == "pc" and c.id not in acted]


def cycle_now(db: Session, troupe_id: uuid.UUID) -> DowntimeCycle | None:
    """The cycle whose Quest actions staff are answering: the open one, or else the
    last closed."""
    return db.scalar(
        select(DowntimeCycle)
        .where(DowntimeCycle.troupe_id == troupe_id, DowntimeCycle.status.in_(("open", "closed")))
        .order_by((DowntimeCycle.status == "open").desc(), DowntimeCycle.closes_at.desc())
        .limit(1)
    )


# --- recording the result, and delivering it -----------------------------------------------


def response_text(quest: Quest, scenario: QuestScenario) -> str:
    said = "passed" if scenario.result == "passed" else "failed"
    lines = [f"{quest.name}, scenario {scenario.number}: {said}."]
    if scenario.result_text:
        lines.append(scenario.result_text)
    if quest.status in ("completed", "failed"):
        lines.append(f"The quest is {quest.status}.")
    return "\n\n".join(lines)


def record(
    db: Session,
    staff: User,
    item: responses.WorkItem,
    result: Literal["passed", "failed"],
    text: str | None,
    *,
    ends: bool,
) -> None:
    """Record the result of the scenario a Quest action was for, on the quest. It is
    the response to every member's Quest action on that scenario in the cycle, and
    goes out with the cycle's delivery."""
    if item.question.kind != "quest":
        raise unprocessable("This is not a Quest action.")
    if item.cycle.status == "complete":
        raise conflict("This cycle is complete.")
    if responses.delivered(db, item.answer.submission_id):
        raise conflict("These results have already been delivered.")
    quest_id = quest_id_of(item.answer.structured)
    quest = db.get(Quest, quest_id) if quest_id else None
    number = item.answer.structured.get("scenario")
    scenario = (
        db.scalar(
            select(QuestScenario).where(
                QuestScenario.quest_id == quest.id, QuestScenario.number == number
            )
        )
        if quest is not None
        else None
    )
    if quest is None or scenario is None:
        raise conflict("This action's quest or scenario is no longer there.")
    quests.send_result(db, staff, quest, scenario, result, text, ends=ends, cycle=item.cycle)
    body = response_text(quest, scenario)
    for action in actions(db, quest, item.cycle):
        response = action.response
        if response is None or action.scenario != scenario.number:
            continue
        if responses.delivered(db, action.answer.submission_id):
            continue
        response.body = body
        response.status = "written"
        response.written_by = staff.id
        response.written_at = now()
    db.flush()


def deliver(db: Session, staff: User, cycle: DowntimeCycle) -> int:
    """With the cycle's delivery: send each scenario result recorded through it. Those
    whose downtime results carried it have it there; the rest of the party is told
    as a quest's news, with a post on the troupe's connectors. Returns how many
    results went out."""
    rows = list(
        db.execute(
            select(QuestScenario, Quest)
            .join(Quest, QuestScenario.quest_id == Quest.id)
            .where(
                QuestScenario.cycle_id == cycle.id,
                QuestScenario.result.is_not(None),
                QuestScenario.sent_at.is_(None),
            )
            .order_by(Quest.name, QuestScenario.number)
        )
    )
    for scenario, quest in rows:
        told = {
            a.character.id
            for a in actions(db, quest, cycle)
            if a.scenario == scenario.number
            and a.response is not None
            and a.response.status == "written"
            and responses.delivered(db, a.answer.submission_id)
        }
        scenario.sent_at = now()
        later = any(
            s.number > scenario.number and s.result is not None for s in quests.scenarios(db, quest)
        )
        ended = quest.status if quest.status in ("completed", "failed") and not later else None
        summary, subject, full_text = quests.result_news(quest, scenario, ended)
        quests.tell(
            db,
            staff,
            quest,
            [c for c in quests.party(db, quest) if c.id not in told],
            "quest.result",
            summary,
            subject=subject,
            full_text=full_text,
        )
        quests.log(db, quest, staff, f"sent scenario {scenario.number}'s result with {cycle.name}")
        audit.record(
            db,
            staff,
            "quest.result_delivered",
            troupe_id=quest.troupe_id,
            quest=quest.name,
            scenario=scenario.number,
            cycle=cycle.name,
        )
    db.flush()
    return len(rows)
