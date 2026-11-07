"""Projects: work a character does over several downtime cycles (#507; CONTEXT.md:
Project), such as changing its Path (MET: VTM p. 306).

A project belongs to a character, and its home troupe's storytellers and assistant
storytellers keep it. It has a name, a kind (Path change, Research or Other), a
target number of actions and, if it has one, a least number to spend on it each
cycle or start over. Staff start one, or its player proposes one for staff to
confirm.

**Spending on it.** An action answer counts toward one of the character's active
projects (`project_id` in its `structured`). When a cycle completes, each active
project of the cycle's participants goes up by the actions their submitted answers
spent on it. One given fewer than its least that cycle starts over, back to none;
staff see beforehand which will. A character not taking part in a cycle neither
spends on its projects nor loses them then.

**A Path change** takes 9 actions studying the Path with a teacher, or 18 without,
at least 1 each month (p. 306). When it finishes, staff are asked to change the
sheet's Morality to the new Path through the usual sheet change, which lowers
Morality by 1 (p. 306), and to say when they have.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, notifications
from horatio.models import (
    Answer,
    Character,
    CycleParticipant,
    DowntimeCycle,
    Project,
    ProjectCycle,
    Question,
    Submission,
    Troupe,
    User,
)
from horatio.permissions import TroupeAction
from horatio.sheets import conflict, unprocessable

KINDS = {"path_change": "Path change", "research": "Research", "other": "Other"}
PROJECT_ID = "project_id"
# A Path change (p. 306): actions with a teacher and without, and at least this many a month.
PATH_WITH_TEACHER = 9
PATH_WITHOUT_TEACHER = 18
PATH_MONTHLY = 1
# Still to do: proposed by the player, or under way.
OPEN = ("proposed", "active")


def now() -> datetime:
    return datetime.now(UTC)


def project_id_of(structured: Mapping[str, Any]) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(structured[PROJECT_ID]))
    except (KeyError, ValueError):
        return None


def without_project(structured: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in structured.items() if k != PROJECT_ID}


@dataclass
class Draft:
    """A project as its player or staff describe it."""

    kind: str
    name: str = ""
    target: int | None = None
    monthly_minimum: int | None = None
    # A Path change: the Path it changes to, and whether a teacher has it.
    path: str = ""
    with_teacher: bool = False


def shaped(draft: Draft) -> Draft:
    """The draft as it is kept: a Path change takes the book's numbers."""
    if draft.kind not in KINDS:
        raise unprocessable(f"Unknown kind of project {draft.kind!r}.")
    name = draft.name.strip()
    if draft.kind == "path_change":
        path = draft.path.strip()
        if not path:
            raise unprocessable("Choose the Path it changes to.")
        return Draft(
            kind=draft.kind,
            name=name or f"Path change: {path}",
            target=PATH_WITH_TEACHER if draft.with_teacher else PATH_WITHOUT_TEACHER,
            monthly_minimum=PATH_MONTHLY,
            path=path,
            with_teacher=draft.with_teacher,
        )
    if not name:
        raise unprocessable("Give the project a name.")
    if draft.target is None or draft.target < 1:
        raise unprocessable("A project needs at least 1 action.")
    if draft.monthly_minimum is not None and not 1 <= draft.monthly_minimum <= draft.target:
        raise unprocessable("The least a month is from 1 to the actions it needs.")
    return Draft(
        kind=draft.kind,
        name=name,
        target=draft.target,
        monthly_minimum=draft.monthly_minimum,
    )


def of_character(db: Session, character: Character) -> list[Project]:
    """The character's projects in its home troupe, those still to do first, then
    newest first."""
    found = db.scalars(
        select(Project)
        .where(Project.character_id == character.id)
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    return sorted(found, key=lambda p: p.status not in OPEN)


def of_troupe(db: Session, troupe_id: uuid.UUID) -> list[tuple[Project, Character]]:
    """The troupe's projects, by character name, those still to do first."""
    rows = db.execute(
        select(Project, Character)
        .join(Character, Project.character_id == Character.id)
        .where(Project.troupe_id == troupe_id)
        .order_by(Character.name, Project.created_at.desc(), Project.id.desc())
    )
    found = [(p, c) for p, c in rows]
    return sorted(found, key=lambda pc: pc[0].status not in OPEN)


def staff_ids(db: Session, troupe_id: uuid.UUID) -> list[uuid.UUID]:
    return notifications.staff_for(db, db.get_one(Troupe, troupe_id), TroupeAction.MANAGE_CYCLES)


def start(
    db: Session, user: User, character: Character, draft: Draft, *, as_staff: bool
) -> Project:
    """Start a project for the character: under way at once when staff start it, or
    proposed, for staff to confirm, when its player does."""
    if character.kind != "pc" or character.home_troupe_id is None:
        raise conflict("Only a character with a home troupe has projects.")
    if character.status != "active":
        raise conflict("A retired character starts no projects.")
    draft = shaped(draft)
    assert draft.target is not None
    project = Project(
        character_id=character.id,
        troupe_id=character.home_troupe_id,
        name=draft.name,
        kind=draft.kind,
        target=draft.target,
        monthly_minimum=draft.monthly_minimum,
        path=draft.path,
        with_teacher=draft.with_teacher,
        status="active" if as_staff else "proposed",
        started_by=user.id,
        confirmed_by=user.id if as_staff else None,
    )
    db.add(project)
    db.flush()
    audit.record(
        db,
        user,
        "project.started" if as_staff else "project.proposed",
        troupe_id=project.troupe_id,
        character_id=character.id,
        name=project.name,
    )
    if not as_staff:
        notifications.notify(
            db,
            staff_ids(db, project.troupe_id),
            "project.proposed",
            f"{character.name}'s player proposes a project: {project.name}.",
            f"/characters/{character.id}/projects",
            troupe_id=project.troupe_id,
            character_id=character.id,
        )
    return project


def confirm(db: Session, staff: User, project: Project) -> None:
    if project.status != "proposed":
        raise conflict("Only a proposed project is confirmed.")
    project.status = "active"
    project.confirmed_by = staff.id
    db.flush()
    character = db.get_one(Character, project.character_id)
    audit.record(
        db,
        staff,
        "project.confirmed",
        troupe_id=project.troupe_id,
        character_id=character.id,
        name=project.name,
    )
    notifications.notify(
        db,
        [character.player_id],
        "project.confirmed",
        f"{character.name}'s project {project.name} is under way.",
        f"/characters/{character.id}/downtime",
        troupe_id=project.troupe_id,
        character_id=character.id,
    )


def drop(db: Session, user: User, project: Project, *, as_staff: bool) -> None:
    """Staff decline a proposed project or stop one under way; its player can
    withdraw one they proposed."""
    if project.status not in OPEN:
        raise conflict(f"This project is already {project.status}.")
    if not as_staff and project.status != "proposed":
        raise conflict("Only staff stop a project under way.")
    project.status = "dropped"
    db.flush()
    audit.record(
        db,
        user,
        "project.dropped",
        troupe_id=project.troupe_id,
        character_id=project.character_id,
        name=project.name,
    )


def sheet_changed(db: Session, staff: User, project: Project) -> None:
    """Staff say the finished Path change is on the sheet."""
    if project.kind != "path_change" or project.status != "finished":
        raise conflict("Only a finished Path change waits on the sheet.")
    project.sheet_changed_by = staff.id
    db.flush()
    audit.record(
        db,
        staff,
        "project.sheet_changed",
        troupe_id=project.troupe_id,
        character_id=project.character_id,
        name=project.name,
        path=project.path,
    )


def check_answer(
    db: Session,
    character: Character,
    cycle: DowntimeCycle,
    question: Question,
    structured: Mapping[str, Any],
    before: Answer | None,
) -> dict[str, Any]:
    """An answer's `structured` with the project it counts toward, as it is kept: an
    action, toward one of the character's projects under way in this troupe. One it
    counted toward before stays, though it has finished since."""
    if PROJECT_ID not in structured or structured[PROJECT_ID] in (None, ""):
        return without_project(structured)
    project_id = project_id_of(structured)
    if question.kind != "action":
        raise unprocessable(f"{question.prompt!r} can't count toward a project.")
    if project_id is None:
        raise unprocessable(f"{question.prompt!r}: choose one of the character's projects.")
    if before is None or project_id_of(before.structured) != project_id:
        project = db.get(Project, project_id)
        if (
            project is None
            or project.character_id != character.id
            or project.troupe_id != cycle.troupe_id
            or project.status != "active"
        ):
            raise unprocessable(
                f"{question.prompt!r}: choose one of the character's projects under way."
            )
    return without_project(structured) | {PROJECT_ID: str(project_id)}


def spent_in(db: Session, cycle: DowntimeCycle) -> dict[uuid.UUID, int]:
    """Actions toward each project in the cycle's submitted downtimes."""
    found: dict[uuid.UUID, int] = {}
    for structured in db.scalars(
        select(Answer.structured)
        .join(Submission, Answer.submission_id == Submission.id)
        .join(CycleParticipant, Submission.participant_id == CycleParticipant.id)
        .where(
            CycleParticipant.cycle_id == cycle.id,
            CycleParticipant.removed_at.is_(None),
            Submission.status == "submitted",
            Answer.structured.has_key(PROJECT_ID),
        )
    ):
        project_id = project_id_of(structured)
        if project_id is not None:
            found[project_id] = found.get(project_id, 0) + 1
    return found


def taking_part(db: Session, cycle: DowntimeCycle) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(CycleParticipant.character_id).where(
                CycleParticipant.cycle_id == cycle.id, CycleParticipant.removed_at.is_(None)
            )
        )
    )


@dataclass(frozen=True)
class Standing:
    """Where a project stands in a cycle not yet complete."""

    # Actions toward it in submitted downtimes so far.
    spent: int
    # Short of its least, so it starts over when the cycle completes, losing progress.
    starts_over: bool


def standings(db: Session, cycle: DowntimeCycle) -> dict[uuid.UUID, Standing]:
    """For each active project of the cycle's participants: what the cycle has spent
    on it so far, and whether it would start over were the cycle completed now."""
    if cycle.status == "complete":
        return {}
    spent = spent_in(db, cycle)
    ids = taking_part(db, cycle)
    found: dict[uuid.UUID, Standing] = {}
    for project in db.scalars(
        select(Project).where(Project.troupe_id == cycle.troupe_id, Project.status == "active")
    ):
        if project.character_id not in ids:
            continue
        n = spent.get(project.id, 0)
        short = project.monthly_minimum is not None and n < project.monthly_minimum
        found[project.id] = Standing(spent=n, starts_over=short and project.progress + n > 0)
    return found


def cycle_completed(db: Session, staff: User, cycle: DowntimeCycle) -> None:
    """Count the cycle's actions toward each active project of its participants: up
    by those spent, or back to none for fewer than its least. A project reaching its
    target finishes."""
    spent = spent_in(db, cycle)
    ids = taking_part(db, cycle)
    done = set(db.scalars(select(ProjectCycle.project_id).where(ProjectCycle.cycle_id == cycle.id)))
    for project in db.scalars(
        select(Project)
        .where(Project.troupe_id == cycle.troupe_id, Project.status == "active")
        .order_by(Project.id)
    ):
        if project.character_id not in ids or project.id in done:
            continue
        n = spent.get(project.id, 0)
        started_over = False
        if project.monthly_minimum is not None and n < project.monthly_minimum:
            started_over = project.progress + n > 0
            project.progress = 0
            project.restarts += started_over
        else:
            project.progress += n
        db.add(
            ProjectCycle(
                project_id=project.id,
                cycle_id=cycle.id,
                spent=n,
                started_over=started_over,
                progress=project.progress,
            )
        )
        character = db.get_one(Character, project.character_id)
        if started_over:
            audit.record(
                db,
                staff,
                "project.started_over",
                troupe_id=project.troupe_id,
                character_id=character.id,
                name=project.name,
                cycle_name=cycle.name,
            )
        if project.progress >= project.target:
            finish(db, staff, project, character)
    db.flush()


def finish(db: Session, staff: User, project: Project, character: Character) -> None:
    project.status = "finished"
    project.finished_at = now()
    audit.record(
        db,
        staff,
        "project.finished",
        troupe_id=project.troupe_id,
        character_id=character.id,
        name=project.name,
    )
    notifications.notify(
        db,
        [character.player_id],
        "project.finished",
        f"{character.name} has finished {project.name}.",
        f"/characters/{character.id}/downtime",
        troupe_id=project.troupe_id,
        character_id=character.id,
    )
    if project.kind == "path_change":
        notifications.notify(
            db,
            staff_ids(db, project.troupe_id),
            "project.path_changed",
            f"{character.name} has finished changing Path to {project.path}: change their "
            "Morality on the sheet.",
            f"/characters/{character.id}/projects",
            troupe_id=project.troupe_id,
            character_id=character.id,
        )


def history(db: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ProjectCycle]]:
    """Each project's completed cycles, oldest first."""
    found: dict[uuid.UUID, list[ProjectCycle]] = {p: [] for p in project_ids}
    for row in db.scalars(
        select(ProjectCycle)
        .where(ProjectCycle.project_id.in_(project_ids))
        .order_by(ProjectCycle.created_at, ProjectCycle.id)
    ):
        found[row.project_id].append(row)
    return found
