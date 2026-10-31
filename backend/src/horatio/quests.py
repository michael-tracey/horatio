"""Quests (MET: VTM Vol. II Issue 1, pp. 99-110; CONTEXT.md: Quest, Quest Request,
Quest Requirement, Scenario, Quest Leader, Party).

Horatio tracks quests; it does not run them. The tests happen at a game or in
downtime, and staff record what came of them.

**A troupe turns quests on** (Troupe.quests_enabled) and sets how many requests a
character may make in a downtime cycle: the open cycle, or the next one if none is
open. While they are off, players see nothing of them and requests are refused.

**A player requests a quest** for their character, in their own words. It waits in
the troupe's queue: `new` until staff start on it (assign it, or build a quest from
it), `working` while they do, then `answered`: with a quest, once its requirements
are sent; as not needed, which gives the slot back; or refused. The player can
withdraw it while it is new, which also gives the slot back.

**Staff build a quest**, from a request or from nothing: a name and objective, a
category and difficulty (the book's numbers of requirements and scenarios are a
guide, not a limit), requirements (horatio.quest_requirements), numbered scenarios
with success and fail text, a leader and a party, Downtime Only, notes for staff
and a log. Requests and quests are assigned as downtime responses are: to one of
the staff or to any narrator, who accepts it. A narrator works only on what is
theirs and never sees sheets; storytellers and assistant storytellers check
requirements against sheets, mark them met (spending what they expend), and send.
Other staff mark that they have read it.

**Delivery is two steps.** Sending the requirements makes the quest active: its
leader and party see its name, objective and requirements, with a notification and
a post on the troupe's connectors (horatio.delivery). Then each scenario's result:
its success or fail text. A passed last scenario completes the quest; staff can
end it as failed with a failed result. Either way it records the date and the
party then.

**Sharing and joining.** The leader's player shares an active quest with other
characters of the troupe, who see it and may join its party. Staff also offer a
quest more widely: to characters they choose, to anyone who passed a given
scenario of another quest, or to the whole troupe, as a board. Whoever joins a
quest with no leader leads it. Staff add characters to the party at a game.

**Closing.** Staff switch a quest off at any point, with a note; it can no longer
be joined or progressed, and those who could see it see why.

**Answering a request.** Staff can answer a merit or flaw request in the approvals
queue with a quest for its character (horatio.merit_requests): completing the quest
approves the request, failing or closing it declines it.

**Telling the Tale** (p. 102): once it ends, the leader's player writes what
happened, and staff edit and approve it as the official account.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from horatio import audit, delivery, quest_requirements
from horatio.models import (
    Character,
    DowntimeCycle,
    Quest,
    QuestLogEntry,
    QuestMember,
    QuestRequest,
    QuestRequirement,
    QuestScenario,
    Troupe,
    TroupeMembership,
    TroupeStaff,
    User,
)
from horatio.notifications import notify
from horatio.permissions import Role, troupe_role
from horatio.quest_requirements import Option
from horatio.sheets import conflict, unprocessable

Category = Literal["simple", "complex", "epic"]
CATEGORIES: tuple[Category, ...] = ("simple", "complex", "epic")
# The book's requirements and scenarios for each point of difficulty (pp. 99-100);
# a Simple quest has one scenario whatever its difficulty.
PER_POINT: dict[str, tuple[int, int]] = {"simple": (1, 0), "complex": (2, 1), "epic": (3, 2)}
RUNNING = (Role.LEAD_STORYTELLER, Role.STORYTELLER, Role.ASSISTANT_STORYTELLER)

Assignable = QuestRequest | Quest


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return now().date()


def guidance(category: str, difficulty: int) -> tuple[int, int]:
    """The book's number of requirements and scenarios for a quest (pp. 99-100)."""
    requirements, scenarios = PER_POINT[category]
    return requirements * difficulty, max(1, scenarios * difficulty)


# --- the troupe's settings ---------------------------------------------------------------


def set_settings(db: Session, user: User, troupe: Troupe, enabled: bool, per_cycle: int) -> None:
    troupe.quests_enabled = enabled
    troupe.quest_requests_per_cycle = per_cycle
    db.flush()
    audit.record(
        db,
        user,
        "house.quests",
        troupe_id=troupe.id,
        state="on" if enabled else "off",
        per_cycle=per_cycle,
    )


# --- who is who ----------------------------------------------------------------------------


def is_running(db: Session, user: User, troupe: Troupe) -> bool:
    return user.is_custodian or troupe_role(db, user, troupe) in RUNNING


def is_narrator(db: Session, user: User, troupe: Troupe) -> bool:
    return not user.is_custodian and troupe_role(db, user, troupe) == Role.NARRATOR


def narrator_may_see(user: User, item: Assignable) -> bool:
    """A narrator sees what is assigned to them, and to any narrator."""
    return item.assigned_to_user_id == user.id or item.assigned_to_any_narrator


def may_work_on(db: Session, user: User, troupe: Troupe, item: Assignable) -> bool:
    """Storytellers and assistant storytellers work on anything; a narrator on what is
    assigned to them alone."""
    return is_running(db, user, troupe) or (
        is_narrator(db, user, troupe) and item.assigned_to_user_id == user.id
    )


def in_troupe(db: Session, troupe_id: uuid.UUID, character: Character) -> bool:
    """A character of the troupe now: a member, home or visiting, or an NPC it keeps."""
    if character.owner_troupe_id == troupe_id:
        return True
    return (
        db.scalar(
            select(TroupeMembership.id).where(
                TroupeMembership.troupe_id == troupe_id,
                TroupeMembership.character_id == character.id,
                TroupeMembership.left_at.is_(None),
            )
        )
        is not None
    )


def troupe_characters(db: Session, troupe_id: uuid.UUID) -> list[Character]:
    """The troupe's active characters, PCs and NPCs, by name."""
    members = select(TroupeMembership.character_id).where(
        TroupeMembership.troupe_id == troupe_id, TroupeMembership.left_at.is_(None)
    )
    return list(
        db.scalars(
            select(Character)
            .where(
                or_(Character.id.in_(members), Character.owner_troupe_id == troupe_id),
                Character.status == "active",
            )
            .order_by(func.lower(Character.name))
        )
    )


# --- requests and their limit --------------------------------------------------------------


def request_cycle(db: Session, troupe: Troupe) -> DowntimeCycle | None:
    """The cycle requests count against now: the open one, or else the next."""
    return db.scalar(
        select(DowntimeCycle)
        .where(DowntimeCycle.troupe_id == troupe.id, DowntimeCycle.status.in_(("open", "draft")))
        .order_by((DowntimeCycle.status == "open").desc(), DowntimeCycle.closes_at)
        .limit(1)
    )


def counts(request: QuestRequest) -> bool:
    """Whether a request uses up one of its character's requests for its cycle."""
    return request.status != "withdrawn" and request.outcome != "not_needed"


def requests_this_cycle(
    db: Session, troupe: Troupe, character: Character, cycle: DowntimeCycle | None
) -> list[QuestRequest]:
    """The character's requests counted against `cycle`; with no cycle, those made
    since the troupe's last cycle closed."""
    query = select(QuestRequest).where(
        QuestRequest.troupe_id == troupe.id, QuestRequest.character_id == character.id
    )
    if cycle is not None:
        query = query.where(QuestRequest.cycle_id == cycle.id)
    else:
        last = db.scalar(
            select(func.max(DowntimeCycle.closed_at)).where(DowntimeCycle.troupe_id == troupe.id)
        )
        query = query.where(QuestRequest.cycle_id.is_(None))
        if last is not None:
            query = query.where(QuestRequest.created_at > last)
    return [r for r in db.scalars(query) if counts(r)]


@dataclass(frozen=True)
class Allowance:
    limit: int
    used: int
    cycle: DowntimeCycle | None
    # Why the character cannot ask now, or None.
    refusal: str | None


def allowance(db: Session, troupe: Troupe | None, character: Character) -> Allowance:
    if troupe is None or not troupe.quests_enabled:
        return Allowance(0, 0, None, "This character's home troupe does not run quests.")
    cycle = request_cycle(db, troupe)
    used = len(requests_this_cycle(db, troupe, character, cycle))
    limit = troupe.quest_requests_per_cycle
    refusal = None
    if character.status != "active":
        refusal = "Only an active character asks for quests."
    elif used >= limit:
        when = f"in {cycle.name}" if cycle else "until the next downtime cycle"
        plural = "request" if limit == 1 else "requests"
        refusal = f"{character.name} has made {used} of {limit} quest {plural} {when}."
    return Allowance(limit, used, cycle, refusal)


def home_troupe(db: Session, character: Character) -> Troupe | None:
    if character.kind != "pc" or character.home_troupe_id is None:
        return None
    troupe = db.get(Troupe, character.home_troupe_id)
    return troupe if troupe is not None and troupe.archived_at is None else None


def make_request(
    db: Session,
    player: User,
    character: Character,
    *,
    objective: str,
    reason: str,
    companions: str,
    kind: str = "custom",
    details: dict[str, Any] | None = None,
    location_id: uuid.UUID | None = None,
) -> QuestRequest:
    """A request in the troupe's queue: a custom quest, or one about a location
    (horatio.location_quests checks those first)."""
    troupe = home_troupe(db, character)
    found = allowance(db, troupe, character)
    if found.refusal is not None or troupe is None:
        raise conflict(found.refusal or "No home troupe.")
    objective = objective.strip()
    if not objective:
        raise unprocessable("Say what you want to achieve.")
    request = QuestRequest(
        troupe_id=troupe.id,
        character_id=character.id,
        requested_by=player.id,
        kind=kind,
        objective=objective,
        reason=reason.strip(),
        companions=companions.strip(),
        details=details or {},
        location_id=location_id,
        cycle_id=found.cycle.id if found.cycle else None,
    )
    db.add(request)
    db.flush()
    audit.record(db, player, "quest.requested", troupe_id=troupe.id, character_id=character.id)
    return request


def withdraw(db: Session, player: User, request: QuestRequest) -> None:
    if request.status != "new":
        raise conflict("Staff have started on this request, so it can no longer be withdrawn.")
    request.status = "withdrawn"
    request.answered_at = now()
    db.flush()
    audit.record(
        db,
        player,
        "quest.request_withdrawn",
        troupe_id=request.troupe_id,
        character_id=request.character_id,
    )


def answer(
    db: Session,
    staff: User,
    request: QuestRequest,
    outcome: Literal["not_needed", "refused", "done"],
    note: str,
) -> None:
    """Answer a request without a quest: not needed (which gives the slot back),
    refused, or done (a repair made, a Contacts lookup answered), with a note for
    the player."""
    if request.status in ("answered", "withdrawn"):
        raise conflict("This request is already answered.")
    if request.quest_id is not None:
        raise conflict("A quest is being built from this request; close the quest instead.")
    note = note.strip()
    if not note:
        raise unprocessable("Give the player a note.")
    finish_request(db, staff, request, outcome, note)


def finish_request(
    db: Session, staff: User, request: QuestRequest, outcome: str, note: str = ""
) -> None:
    request.status = "answered"
    request.outcome = outcome
    request.note = note
    request.answered_by = staff.id
    request.answered_at = now()
    db.flush()
    character = db.get_one(Character, request.character_id)
    if outcome != "quest":
        said = {"not_needed": "isn't needed", "done": "is answered"}.get(outcome, "was refused")
        notify(
            db,
            [request.requested_by],
            "quest.answered",
            f"{character.name}'s quest request {said}: {note}",
            f"/characters/{character.id}/quests",
            troupe_id=request.troupe_id,
            character_id=character.id,
        )
    audit.record(
        db,
        staff,
        "quest.request_answered",
        troupe_id=request.troupe_id,
        character_id=character.id,
        outcome=outcome.replace("_", " "),
    )


def request_of(db: Session, quest: Quest) -> QuestRequest | None:
    return db.scalar(select(QuestRequest).where(QuestRequest.quest_id == quest.id))


# --- assignment, shared by requests and quests ---------------------------------------------


def assign(
    db: Session,
    staff: User,
    troupe: Troupe,
    item: Assignable,
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
            raise unprocessable("Only this troupe's staff can be assigned.")
    item.assigned_to_user_id = user_id
    item.assigned_to_any_narrator = any_narrator
    item.assigned_by = staff.id
    if isinstance(item, QuestRequest):
        if item.status in ("answered", "withdrawn"):
            raise conflict("This request is already answered.")
        if item.quest_id is None:
            item.status = "working" if (user_id or any_narrator) else "new"
    else:
        who = (
            "any narrator"
            if any_narrator
            else (db.get_one(User, user_id).display_name if user_id else "no one")
        )
        log(db, item, staff, f"assigned it to {who}")
    db.flush()


def accept(db: Session, narrator: User, item: Assignable) -> None:
    """A narrator takes on what is assigned to any narrator; it is then theirs."""
    if not item.assigned_to_any_narrator:
        raise conflict("Only what is assigned to any narrator can be accepted.")
    item.assigned_to_any_narrator = False
    item.assigned_to_user_id = narrator.id
    if isinstance(item, Quest):
        log(db, item, narrator, "accepted it")
    db.flush()


def mark_read(item: Assignable, user: User) -> None:
    item.read_by = {**item.read_by, str(user.id): now().isoformat()}


# --- the quest itself ----------------------------------------------------------------------


def log(db: Session, quest: Quest, actor: User | None, text: str) -> None:
    db.add(QuestLogEntry(quest_id=quest.id, actor_id=actor.id if actor else None, text=text))


def scenarios(db: Session, quest: Quest) -> list[QuestScenario]:
    return list(
        db.scalars(
            select(QuestScenario)
            .where(QuestScenario.quest_id == quest.id)
            .order_by(QuestScenario.number)
        )
    )


def requirements(db: Session, quest: Quest) -> list[QuestRequirement]:
    return list(
        db.scalars(
            select(QuestRequirement)
            .where(QuestRequirement.quest_id == quest.id)
            .order_by(QuestRequirement.position, QuestRequirement.created_at)
        )
    )


def members(db: Session, quest: Quest) -> list[tuple[QuestMember, Character]]:
    return [
        (m, c)
        for m, c in db.execute(
            select(QuestMember, Character)
            .join(Character, QuestMember.character_id == Character.id)
            .where(QuestMember.quest_id == quest.id)
            .order_by(QuestMember.created_at)
        )
    ]


def party(db: Session, quest: Quest) -> list[Character]:
    """The leader, then those who joined."""
    leader = db.get(Character, quest.leader_id) if quest.leader_id else None
    joined = [c for m, c in members(db, quest) if m.status == "joined"]
    return [leader, *joined] if leader is not None else joined


def check_leader(db: Session, troupe: Troupe, leader_id: uuid.UUID | None) -> None:
    if leader_id is None:
        return
    leader = db.get(Character, leader_id)
    if leader is None or not in_troupe(db, troupe.id, leader):
        raise unprocessable("The leader must be a character in this troupe.")


@dataclass
class QuestFields:
    name: str
    objective: str = ""
    category: Category = "simple"
    difficulty: int = 1
    downtime_only: bool = False
    staff_notes: str = ""
    leader_id: uuid.UUID | None = None
    offer: Literal["character", "chosen", "unlocked", "troupe"] = "character"
    unlock_quest_id: uuid.UUID | None = None
    unlock_scenario: int | None = None


def check_offer(db: Session, troupe: Troupe, quest: Quest | None, fields: QuestFields) -> None:
    if fields.offer == "unlocked":
        unlock = db.get(Quest, fields.unlock_quest_id) if fields.unlock_quest_id else None
        if unlock is None or unlock.troupe_id != troupe.id or (quest and unlock.id == quest.id):
            raise unprocessable("Choose another quest of this troupe to unlock it.")
        if not fields.unlock_scenario or fields.unlock_scenario < 1:
            raise unprocessable("Choose the scenario that unlocks it.")
    else:
        fields.unlock_quest_id = None
        fields.unlock_scenario = None


def create(
    db: Session,
    staff: User,
    troupe: Troupe,
    fields: QuestFields,
    *,
    request: QuestRequest | None = None,
    scenario_texts: Sequence[tuple[str, str]] = (),
) -> Quest:
    """A new quest, in draft. Built from a request, it is for the request's character
    and starts with its words, and takes on its assignment."""
    if request is not None:
        if request.status in ("answered", "withdrawn") or request.quest_id is not None:
            raise conflict("This request is already answered.")
        fields.leader_id = request.character_id
        fields.objective = fields.objective.strip() or request.objective
    if not fields.name.strip():
        raise unprocessable("Give the quest a name.")
    check_leader(db, troupe, fields.leader_id)
    check_offer(db, troupe, None, fields)
    quest = Quest(
        troupe_id=troupe.id,
        name=fields.name.strip(),
        objective=fields.objective.strip(),
        category=fields.category,
        difficulty=fields.difficulty,
        downtime_only=fields.downtime_only,
        staff_notes=fields.staff_notes,
        leader_id=fields.leader_id,
        offer=fields.offer,
        unlock_quest_id=fields.unlock_quest_id,
        unlock_scenario=fields.unlock_scenario,
        created_by=staff.id,
    )
    if request is not None:
        quest.assigned_to_user_id = request.assigned_to_user_id
        quest.assigned_to_any_narrator = request.assigned_to_any_narrator
        quest.assigned_by = request.assigned_by
    db.add(quest)
    db.flush()
    texts = list(scenario_texts) or [("", "")] * guidance(quest.category, quest.difficulty)[1]
    for number, (success, fail) in enumerate(texts, start=1):
        db.add(
            QuestScenario(quest_id=quest.id, number=number, success_text=success, fail_text=fail)
        )
    if request is not None:
        request.quest_id = quest.id
        request.status = "working"
    log(db, quest, staff, "built it" + (" from a request" if request else ""))
    db.flush()
    audit.record(db, staff, "quest.built", troupe_id=troupe.id, quest=quest.name)
    return quest


def ensure_open(quest: Quest) -> None:
    if quest.status in ("completed", "failed", "closed"):
        raise conflict(f"This quest is {quest.status}.")


def change(
    db: Session,
    staff: User,
    troupe: Troupe,
    quest: Quest,
    fields: QuestFields,
    scenario_texts: Sequence[tuple[str, str]] | None,
) -> None:
    ensure_open(quest)
    if not fields.name.strip():
        raise unprocessable("Give the quest a name.")
    check_leader(db, troupe, fields.leader_id)
    check_offer(db, troupe, quest, fields)
    if quest.leader_id != fields.leader_id and fields.leader_id is not None:
        # The new leader leaves the members' list, where it may have been.
        for member, _ in members(db, quest):
            if member.character_id == fields.leader_id:
                db.delete(member)
    quest.name = fields.name.strip()
    quest.objective = fields.objective.strip()
    quest.category = fields.category
    quest.difficulty = fields.difficulty
    quest.downtime_only = fields.downtime_only
    quest.staff_notes = fields.staff_notes
    quest.leader_id = fields.leader_id
    quest.offer = fields.offer
    quest.unlock_quest_id = fields.unlock_quest_id
    quest.unlock_scenario = fields.unlock_scenario
    if scenario_texts is not None:
        set_scenarios(db, quest, scenario_texts)
    db.flush()


def set_scenarios(db: Session, quest: Quest, texts: Sequence[tuple[str, str]]) -> None:
    """Number them 1 to n; one with a result already sent cannot be taken away."""
    if not texts:
        raise unprocessable("A quest has at least one scenario.")
    found = {s.number: s for s in scenarios(db, quest)}
    for number, scenario in found.items():
        if number > len(texts):
            if scenario.result is not None:
                raise conflict(f"Scenario {number}'s result is sent; it cannot be removed.")
            db.delete(scenario)
    for number, (success, fail) in enumerate(texts, start=1):
        scenario = found.get(number)
        if scenario is None:
            db.add(
                QuestScenario(
                    quest_id=quest.id, number=number, success_text=success, fail_text=fail
                )
            )
        else:
            scenario.success_text = success
            scenario.fail_text = fail
    db.flush()


# --- requirements --------------------------------------------------------------------------


def add_requirement(
    db: Session, staff: User, quest: Quest, options: Sequence[Option]
) -> QuestRequirement:
    ensure_open(quest)
    if not options:
        raise unprocessable("A requirement has at least one alternative.")
    position = 1 + max((r.position for r in requirements(db, quest)), default=0)
    requirement = QuestRequirement(
        quest_id=quest.id, position=position, options=quest_requirements.dump(options)
    )
    db.add(requirement)
    log(db, quest, staff, f"added the requirement {quest_requirements.requirement_label(options)}")
    db.flush()
    return requirement


def change_requirement(
    db: Session, staff: User, quest: Quest, requirement: QuestRequirement, options: Sequence[Option]
) -> None:
    ensure_open(quest)
    if requirement.met_at is not None:
        raise conflict("This requirement is met; unmark it before changing it.")
    if not options:
        raise unprocessable("A requirement has at least one alternative.")
    requirement.options = quest_requirements.dump(options)
    log(
        db,
        quest,
        staff,
        f"changed a requirement to {quest_requirements.requirement_label(options)}",
    )
    db.flush()


def remove_requirement(
    db: Session, staff: User, quest: Quest, requirement: QuestRequirement
) -> None:
    ensure_open(quest)
    if requirement.met_at is not None:
        raise conflict("This requirement is met; unmark it before removing it.")
    label = quest_requirements.requirement_label(quest_requirements.parse(requirement.options))
    db.delete(requirement)
    log(db, quest, staff, f"removed the requirement {label}")
    db.flush()


def log_cycle(db: Session, troupe: Troupe) -> DowntimeCycle | None:
    """The cycle an influence action spent now applies to: the open one, else the
    next, else the last."""
    return request_cycle(db, troupe) or db.scalar(
        select(DowntimeCycle)
        .where(DowntimeCycle.troupe_id == troupe.id)
        .order_by(DowntimeCycle.closes_at.desc())
        .limit(1)
    )


def spent_text(spent: dict[str, Any] | None) -> str:
    if not spent:
        return ""
    if "entry" in spent:
        return f"logged as {spent['entry']}"
    if "tap" in spent:
        return "taken off on the Play View"
    if "status" in spent:
        return f"spent {spent['status']['name']}"
    if "owed_action_id" in spent:
        return "owed from the next downtime"
    return "recorded on the quest"


def meet(
    db: Session,
    staff: User,
    troupe: Troupe,
    quest: Quest,
    requirement: QuestRequirement,
    character: Character,
    option_index: int,
) -> None:
    """Mark a requirement met by one character, with one of its alternatives, and
    spend what that alternative expends. One outside the party is a patron."""
    ensure_open(quest)
    if requirement.met_at is not None:
        raise conflict("This requirement is already met.")
    options = quest_requirements.parse(requirement.options)
    if not 0 <= option_index < len(options):
        raise unprocessable("Choose one of the requirement's alternatives.")
    if not in_troupe(db, troupe.id, character):
        raise unprocessable("Choose a character in this troupe.")
    option = options[option_index]
    spent = quest_requirements.spend(
        db,
        staff,
        troupe,
        character,
        option,
        purpose=f"For the quest {quest.name}",
        cycle_id=cycle.id if (cycle := log_cycle(db, troupe)) else None,
    )
    requirement.met_by_character_id = character.id
    requirement.met_by_name = character.name
    requirement.met_option = option_index
    requirement.met_patron = character.id not in {c.id for c in party(db, quest)}
    requirement.met_at = now()
    requirement.met_marked_by = staff.id
    requirement.spent = spent
    what = quest_requirements.label(option)
    spent_words = spent_text(spent)
    log(
        db,
        quest,
        staff,
        f"marked {what} met by {character.name}"
        + (" as a patron" if requirement.met_patron else "")
        + (f" ({spent_words})" if spent_words else ""),
    )
    db.flush()


def unmeet(db: Session, staff: User, quest: Quest, requirement: QuestRequirement) -> None:
    """Take back a requirement met, giving back what it spent where it still can."""
    ensure_open(quest)
    if requirement.met_at is None:
        raise conflict("This requirement is not met.")
    if requirement.spent:
        character = (
            db.get(Character, requirement.met_by_character_id)
            if requirement.met_by_character_id
            else None
        )
        quest_requirements.give_back(db, staff, character, requirement.spent)
    log(db, quest, staff, f"unmarked a requirement met by {requirement.met_by_name}")
    requirement.met_by_character_id = None
    requirement.met_by_name = ""
    requirement.met_option = None
    requirement.met_patron = False
    requirement.met_at = None
    requirement.met_marked_by = None
    requirement.spent = None
    db.flush()


def checks(
    db: Session, quest: Quest, requirement: QuestRequirement
) -> list[tuple[Character, list[bool | None]]]:
    """For each of the party, whether its sheet meets each alternative now."""
    options = quest_requirements.parse(requirement.options)
    return [(c, [quest_requirements.meets(db, c, o) for o in options]) for c in party(db, quest)]


# --- what players see, and sharing and joining ---------------------------------------------

Role_ = Literal["leader", "joined", "invited", "offered", "left"]


def unlocked_for(db: Session, quest: Quest) -> set[str]:
    """Who passed the scenario that unlocks the quest: its party then."""
    if quest.unlock_quest_id is None or quest.unlock_scenario is None:
        return set()
    scenario = db.scalar(
        select(QuestScenario).where(
            QuestScenario.quest_id == quest.unlock_quest_id,
            QuestScenario.number == quest.unlock_scenario,
            QuestScenario.result == "passed",
        )
    )
    return set(scenario.party) if scenario else set()


def role_of(db: Session, quest: Quest, character: Character) -> Role_ | None:
    """How the character stands with a quest it may see, or None if it may not.
    Nothing shows until its requirements are sent."""
    if quest.sent_at is None:
        return None
    if quest.leader_id == character.id:
        return "leader"
    member = db.scalar(
        select(QuestMember).where(
            QuestMember.quest_id == quest.id, QuestMember.character_id == character.id
        )
    )
    if member is not None:
        return member.status  # type: ignore[return-value]  # checked by the database
    if quest.status != "active":
        return None
    if quest.offer == "troupe" and in_troupe(db, quest.troupe_id, character):
        return "offered"
    if quest.offer == "unlocked" and str(character.id) in unlocked_for(db, quest):
        return "offered"
    return None


def visible_quests(db: Session, character: Character) -> list[tuple[Quest, Role_]]:
    """The quests the character may see, newest first."""
    member_of = select(QuestMember.quest_id).where(QuestMember.character_id == character.id)
    troupes = select(TroupeMembership.troupe_id).where(
        TroupeMembership.character_id == character.id, TroupeMembership.left_at.is_(None)
    )
    candidates = db.scalars(
        select(Quest)
        .join(Troupe, Quest.troupe_id == Troupe.id)
        .where(
            Quest.sent_at.is_not(None),
            Troupe.quests_enabled,
            or_(
                Quest.leader_id == character.id,
                Quest.id.in_(member_of),
                (Quest.status == "active")
                & Quest.offer.in_(("troupe", "unlocked"))
                & Quest.troupe_id.in_(troupes),
            ),
        )
        .order_by(Quest.sent_at.desc())
    )
    found: list[tuple[Quest, Role_]] = []
    for quest in candidates:
        role = role_of(db, quest, character)
        if role is not None:
            found.append((quest, role))
    return found


def ensure_active(quest: Quest) -> None:
    if quest.status != "active":
        raise conflict(
            "This quest is not under way."
            if quest.status == "draft"
            else f"This quest is {quest.status}."
        )


def tell(
    db: Session,
    staff: User | None,
    quest: Quest,
    characters: Sequence[Character],
    kind: str,
    summary: str,
    *,
    subject: str | None = None,
    full_text: str = "",
) -> None:
    """A notification for each character's player and, when `subject` is given, a
    post on the troupe's connectors (horatio.delivery)."""
    for character in characters:
        if character.kind != "pc":
            continue
        notify(
            db,
            [character.player_id],
            kind,
            summary.format(character=character.name),
            f"/characters/{character.id}/quests/{quest.id}",
            troupe_id=quest.troupe_id,
            character_id=character.id,
        )
        if subject is not None and staff is not None:
            delivery.queue_quest(
                db, staff, quest.troupe_id, quest.id, character, subject, full_text
            )


def requirements_text(db: Session, quest: Quest) -> str:
    lines = [f"**{quest.name}**", "", quest.objective, "", "Requirements:"]
    for r in requirements(db, quest):
        lines.append(
            f"- {quest_requirements.requirement_label(quest_requirements.parse(r.options))}"
        )
    return "\n".join(lines).strip()


def send(db: Session, staff: User, quest: Quest) -> None:
    """Send the requirements: the quest is under way, and its leader and those it is
    offered to by name hear of it."""
    if quest.status != "draft":
        raise conflict("This quest's requirements are already sent.")
    if quest.offer == "character" and quest.leader_id is None:
        raise unprocessable("Choose the character it is for, or offer it more widely.")
    if not requirements(db, quest):
        raise unprocessable("Give the quest its requirements before sending them.")
    quest.status = "active"
    quest.sent_at = now()
    quest.sent_by = staff.id
    log(db, quest, staff, "sent its requirements")
    db.flush()
    request = request_of(db, quest)
    if request is not None and request.status != "answered":
        finish_request(db, staff, request, "quest")
    leader = db.get(Character, quest.leader_id) if quest.leader_id else None
    named = [
        *([leader] if leader else []),
        *(c for m, c in members(db, quest) if m.status != "left"),
    ]
    tell(
        db,
        staff,
        quest,
        named,
        "quest.sent",
        f"The quest {quest.name} for {{character}}: its requirements are here",
        subject=f"Quest: {quest.name}",
        full_text=requirements_text(db, quest),
    )
    audit.record(db, staff, "quest.sent", troupe_id=quest.troupe_id, quest=quest.name)


def result_news(quest: Quest, scenario: QuestScenario, ended: str | None) -> tuple[str, str, str]:
    """A scenario's result as its party is told it: the notification's summary (with
    {character} to fill), the connectors' subject, and the whole of it."""
    said = "passed" if scenario.result == "passed" else "failed"
    summary = f"{{character}}'s quest {quest.name}: scenario {scenario.number} {said}" + (
        f"; the quest is {ended}" if ended else ""
    )
    full_text = f"**{quest.name}**, scenario {scenario.number}: {said}\n\n{scenario.result_text}"
    return summary, f"Quest: {quest.name}, scenario {scenario.number}", full_text.strip()


def send_result(
    db: Session,
    staff: User,
    quest: Quest,
    scenario: QuestScenario,
    result: Literal["passed", "failed"],
    text: str | None,
    *,
    ends: bool,
    cycle: DowntimeCycle | None = None,
) -> None:
    """Record a scenario's result for the party: its success or fail text. A passed
    last scenario completes the quest; a failed one may end it as failed, or be tried
    again. Recorded at a game it goes out at once; recorded through a downtime
    cycle's Quest actions (horatio.quest_actions), it waits for that cycle's delivery.
    A Downtime Only quest's results are recorded only through a downtime."""
    ensure_active(quest)
    if cycle is None and quest.downtime_only:
        raise conflict(
            "This quest is downtime only: its results are recorded from a Quest action "
            "in a downtime cycle."
        )
    if scenario.result == "passed":
        raise conflict(f"Scenario {scenario.number} is already passed.")
    all_scenarios = scenarios(db, quest)
    earlier = [s for s in all_scenarios if s.number < scenario.number and s.result != "passed"]
    if earlier:
        raise conflict(f"Scenario {earlier[0].number} comes first.")
    if text is not None:
        if result == "passed":
            scenario.success_text = text
        else:
            scenario.fail_text = text
    members_now = party(db, quest)
    scenario.result = result
    scenario.result_text = scenario.success_text if result == "passed" else scenario.fail_text
    scenario.sent_at = now() if cycle is None else None
    scenario.sent_by = staff.id
    scenario.cycle_id = cycle.id if cycle is not None else None
    if result == "passed":
        scenario.party = [str(c.id) for c in members_now]
    if cycle is None:
        log(db, quest, staff, f"sent scenario {scenario.number}: {result}")
    else:
        log(
            db,
            quest,
            staff,
            f"recorded scenario {scenario.number}: {result}, in {cycle.name}; "
            "it goes out with that cycle's delivery",
        )
    last = scenario.number == max(s.number for s in all_scenarios)
    ended = None
    if result == "passed" and last:
        ended = "completed"
    elif result == "failed" and ends:
        ended = "failed"
    if ended is not None:
        quest.status = ended
        quest.ended_on = today()
        quest.ended_by = staff.id
        quest.finished_by = [{"id": str(c.id), "name": c.name} for c in members_now]
        log(db, quest, staff, f"marked it {ended}")
    db.flush()
    if ended == "completed" and quest.location_id is not None:
        # A location quest changes its location (horatio.location_quests).
        from horatio import location_quests

        location_quests.complete(db, staff, quest)
    if ended is not None:
        # One answering a merit or flaw request decides it (horatio.merit_requests).
        from horatio import merit_requests

        merit_requests.quest_ended(db, staff, quest, ended == "completed")
    if cycle is None:
        summary, subject, full_text = result_news(quest, scenario, ended)
        tell(
            db,
            staff,
            quest,
            members_now,
            "quest.result",
            summary,
            subject=subject,
            full_text=full_text,
        )
    audit.record(
        db,
        staff,
        "quest.result" if cycle is None else "quest.result_recorded",
        troupe_id=quest.troupe_id,
        quest=quest.name,
        scenario=scenario.number,
        result=result,
        cycle=cycle.name if cycle is not None else None,
    )


def awaiting_delivery(scenario: QuestScenario) -> bool:
    """A result recorded through a downtime cycle that has not gone out yet."""
    return scenario.result is not None and scenario.sent_at is None


def current_scenario(db: Session, quest: Quest) -> QuestScenario | None:
    """The scenario the party faces next: the first not passed."""
    return next((s for s in scenarios(db, quest) if s.result != "passed"), None)


def close(db: Session, staff: User, quest: Quest, note: str) -> None:
    ensure_open(quest)
    note = note.strip()
    if not note:
        raise unprocessable("Say why it is closed.")
    was_sent = quest.sent_at is not None
    quest.status = "closed"
    quest.closed_at = now()
    quest.closed_by = staff.id
    quest.close_note = note
    log(db, quest, staff, f"closed it: {note}")
    db.flush()
    request = request_of(db, quest)
    if request is not None and request.status not in ("answered", "withdrawn"):
        finish_request(db, staff, request, "refused", note)
    from horatio import merit_requests  # imports this module

    said = f"The quest {quest.name} was closed: {note}"
    merit_requests.quest_ended(db, staff, quest, False, said)
    if was_sent:
        leader = db.get(Character, quest.leader_id) if quest.leader_id else None
        seen = [*([leader] if leader else []), *(c for _, c in members(db, quest))]
        tell(
            db,
            None,
            quest,
            seen,
            "quest.closed",
            f"{{character}}'s quest {quest.name} is closed: {note}",
        )
    audit.record(db, staff, "quest.closed", troupe_id=quest.troupe_id, quest=quest.name, note=note)


def add_members(
    db: Session, actor: User, quest: Quest, characters: Sequence[Character], *, joined: bool
) -> None:
    """Share or offer a quest with characters (invited), or put them in its party
    (joined). The leader is never a member; a joined member stays joined."""
    ensure_open(quest)
    found = {m.character_id: m for m, _ in members(db, quest)}
    added: list[Character] = []
    for character in characters:
        if character.id == quest.leader_id:
            continue
        if not in_troupe(db, quest.troupe_id, character):
            raise unprocessable(f"{character.name} is not in this troupe.")
        member = found.get(character.id)
        if joined and quest.leader_id is None:
            quest.leader_id = character.id
            if member is not None:
                db.delete(member)
            continue
        if member is None:
            member = QuestMember(quest_id=quest.id, character_id=character.id, added_by=actor.id)
            db.add(member)
            added.append(character)
        if joined and member.status != "joined":
            member.status = "joined"
            member.joined_at = now()
    db.flush()
    names = ", ".join(c.name for c in characters)
    log(db, quest, actor, f"{'added' if joined else 'shared it with'} {names}")
    if quest.sent_at is not None and added and not joined:
        tell(
            db, None, quest, added, "quest.shared", f"{{character}} can join the quest {quest.name}"
        )


def remove_member(db: Session, staff: User, quest: Quest, character: Character) -> None:
    member = db.scalar(
        select(QuestMember).where(
            QuestMember.quest_id == quest.id, QuestMember.character_id == character.id
        )
    )
    if member is None:
        raise conflict(f"{character.name} is not one of this quest's characters.")
    db.delete(member)
    log(db, quest, staff, f"took {character.name} off it")
    db.flush()


def join(db: Session, user: User, quest: Quest, character: Character) -> None:
    """The character joins the party; with no leader yet, it leads."""
    ensure_active(quest)
    role = role_of(db, quest, character)
    if role not in ("invited", "offered"):
        raise conflict(
            f"{character.name} is already in the party."
            if role in ("leader", "joined")
            else f"{character.name} cannot join this quest."
        )
    if quest.leader_id is None:
        quest.leader_id = character.id
        member = db.scalar(
            select(QuestMember).where(
                QuestMember.quest_id == quest.id, QuestMember.character_id == character.id
            )
        )
        if member is not None:
            db.delete(member)
        log(db, quest, user, f"joined it with {character.name}, who leads it")
    else:
        member = db.scalar(
            select(QuestMember).where(
                QuestMember.quest_id == quest.id, QuestMember.character_id == character.id
            )
        )
        if member is None:
            member = QuestMember(quest_id=quest.id, character_id=character.id, added_by=user.id)
            db.add(member)
        member.status = "joined"
        member.joined_at = now()
        log(db, quest, user, f"joined it with {character.name}")
    db.flush()
    audit.record(
        db,
        user,
        "quest.joined",
        troupe_id=quest.troupe_id,
        character_id=character.id,
        quest=quest.name,
    )


def write_tale(
    db: Session, user: User, quest: Quest, tale: str, *, staff: bool, approve: bool
) -> None:
    """The leader's player writes what happened once the quest ends; staff edit it and
    approve it as the official account, after which only staff change it."""
    if quest.status not in ("completed", "failed"):
        raise conflict("The tale is told once the quest ends.")
    if not staff and quest.tale_approved_at is not None:
        raise conflict("The storytellers have approved the tale; it is the official account now.")
    quest.tale = tale.strip()
    quest.tale_by = user.id
    quest.tale_at = now()
    if staff and approve:
        if not quest.tale:
            raise unprocessable("There is no tale to approve yet.")
        quest.tale_approved_by = user.id
        quest.tale_approved_at = now()
        log(db, quest, user, "approved the tale")
        leader = db.get(Character, quest.leader_id) if quest.leader_id else None
        if leader is not None:
            tell(db, None, quest, [leader], "quest.tale", f"The tale of {quest.name} is approved")
    elif staff:
        quest.tale_approved_by = None
        quest.tale_approved_at = None
        log(db, quest, user, "edited the tale")
    db.flush()


# --- the staff's queue ---------------------------------------------------------------------

Show = Literal["open", "new", "mine", "any_narrator", "to_send", "answered"]


def queue(db: Session, user: User, troupe: Troupe, show: Show) -> list[QuestRequest]:
    """The troupe's requests, oldest first. A narrator sees only those assigned to them
    or to any narrator."""
    query = select(QuestRequest).where(QuestRequest.troupe_id == troupe.id)
    open_ = QuestRequest.status.in_(("new", "working"))
    if show == "open":
        query = query.where(open_)
    elif show == "new":
        query = query.where(QuestRequest.status == "new")
    elif show == "mine":
        query = query.where(open_, QuestRequest.assigned_to_user_id == user.id)
    elif show == "any_narrator":
        query = query.where(open_, QuestRequest.assigned_to_any_narrator)
    elif show == "to_send":
        drafts = select(Quest.id).where(Quest.status == "draft")
        query = query.where(open_, QuestRequest.quest_id.in_(drafts))
    else:
        query = query.where(QuestRequest.status.in_(("answered", "withdrawn")))
    found = list(db.scalars(query.order_by(QuestRequest.created_at)))
    if not is_running(db, user, troupe):
        found = [r for r in found if narrator_may_see(user, r)]
    return found
