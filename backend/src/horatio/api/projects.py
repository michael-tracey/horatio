"""Projects that span several downtime cycles, such as a Path change
(horatio.projects): for a character's player, and its home troupe's storytellers
and assistant storytellers."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from horatio import projects, quests
from horatio.api.downtimes import staff_cycle
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import Character, DowntimeCycle, Project, ProjectCycle, Troupe, User
from horatio.permissions import TroupeAction, allows, troupe_role, visible_character
from horatio.rules.store import read_troupe_rules

router = APIRouter(tags=["projects"])

Kind = Literal["path_change", "research", "other"]


class ProjectIn(BaseModel):
    kind: Kind
    name: str = Field(default="", max_length=200)
    # Not for a Path change, which takes the book's numbers.
    target: int | None = Field(default=None, ge=1, le=100)
    monthly_minimum: int | None = Field(default=None, ge=1, le=100)
    path: str = Field(default="", max_length=200)
    with_teacher: bool = False


class ProjectCycleOut(BaseModel):
    cycle_name: str
    spent: int
    started_over: bool
    progress: int


class ProjectOut(BaseModel):
    id: uuid.UUID
    character_id: uuid.UUID
    character_name: str
    name: str
    kind: Kind
    target: int
    monthly_minimum: int | None
    progress: int
    # proposed | active | finished | dropped
    status: str
    path: str
    with_teacher: bool
    restarts: int
    finished_at: datetime | None
    # A finished Path change still to go on the sheet.
    sheet_change_due: bool
    # In a cycle not yet complete: actions toward it in submitted downtimes so far,
    # and whether it starts over when the cycle completes.
    this_cycle: int | None = None
    starts_over: bool = False
    history: list[ProjectCycleOut] = []


class CharacterProjectsOut(BaseModel):
    projects: list[ProjectOut]
    # The Paths a Path change can be to.
    paths: list[str]
    # The viewer is its home troupe's staff, who start, confirm and stop projects.
    staff: bool
    # Its home troupe, and whether it runs quests: a goal with things to gather and
    # tests to pass is a quest to ask for, not a project.
    troupe_id: uuid.UUID | None = None
    quests: bool = False


def project_out(
    db: DbSession,
    project: Project,
    character: Character,
    history: list[ProjectCycle] | None = None,
    standing: projects.Standing | None = None,
) -> ProjectOut:
    rows = history if history is not None else projects.history(db, [project.id])[project.id]
    names = (
        {
            c.id: c.name
            for c in db.scalars(
                select(DowntimeCycle).where(DowntimeCycle.id.in_({r.cycle_id for r in rows}))
            )
        }
        if rows
        else {}
    )
    return ProjectOut(
        id=project.id,
        character_id=character.id,
        character_name=character.name,
        name=project.name,
        kind=project.kind,  # type: ignore[arg-type]
        target=project.target,
        monthly_minimum=project.monthly_minimum,
        progress=project.progress,
        status=project.status,
        path=project.path,
        with_teacher=project.with_teacher,
        restarts=project.restarts,
        finished_at=project.finished_at,
        sheet_change_due=project.kind == "path_change"
        and project.status == "finished"
        and project.sheet_changed_by is None,
        this_cycle=standing.spent if standing else None,
        starts_over=standing.starts_over if standing else False,
        history=[
            ProjectCycleOut(
                cycle_name=names.get(r.cycle_id, "?"),
                spent=r.spent,
                started_over=r.started_over,
                progress=r.progress,
            )
            for r in rows
        ],
    )


def is_staff(db: DbSession, user: User, troupe_id: uuid.UUID | None) -> bool:
    if user.is_custodian:
        return True
    troupe = db.get(Troupe, troupe_id) if troupe_id else None
    return troupe is not None and allows(troupe_role(db, user, troupe), TroupeAction.MANAGE_CYCLES)


def character_access(db: DbSession, user: User, character_id: uuid.UUID) -> tuple[Character, bool]:
    """The character, and whether `user` is its home troupe's staff rather than its
    player. Anyone else is refused."""
    character = visible_character(db, user, character_id)
    if character.kind != "pc":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "An NPC has no projects.")
    staff = is_staff(db, user, character.home_troupe_id)
    if not staff and character.player_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only its player and its staff see this.")
    return character, staff


def a_project(db: DbSession, user: User, project_id: uuid.UUID) -> tuple[Project, Character, bool]:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such project.")
    character = db.get_one(Character, project.character_id)
    staff = is_staff(db, user, project.troupe_id)
    if not staff and not (character.kind == "pc" and character.player_id == user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such project.")
    return project, character, staff


def paths_for(db: DbSession, character: Character) -> list[str]:
    rules = read_troupe_rules(db, character.splat, character.home_troupe_id)
    return sorted(name for category, name in rules.rule_set.traits if category == "paths")


@router.get("/characters/{character_id}/projects")
def character_projects(
    character_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> CharacterProjectsOut:
    character, staff = character_access(db, user, character_id)
    found = projects.of_character(db, character)
    history = projects.history(db, [p.id for p in found])
    troupe = quests.home_troupe(db, character)
    return CharacterProjectsOut(
        projects=[project_out(db, p, character, history[p.id]) for p in found],
        paths=paths_for(db, character),
        staff=staff,
        troupe_id=character.home_troupe_id,
        quests=troupe is not None and troupe.quests_enabled,
    )


@router.post("/characters/{character_id}/projects", status_code=status.HTTP_201_CREATED)
def start_project(
    character_id: uuid.UUID, body: ProjectIn, db: DbSession, user: CurrentUser
) -> ProjectOut:
    """Staff start a project; its player proposes one, for staff to confirm."""
    character, staff = character_access(db, user, character_id)
    project = projects.start(
        db, user, character, projects.Draft(**body.model_dump()), as_staff=staff
    )
    db.commit()
    return project_out(db, project, character)


@router.get("/cycles/{cycle_id}/projects")
def cycle_projects(cycle_id: uuid.UUID, db: DbSession, user: CurrentUser) -> list[ProjectOut]:
    """The troupe's projects, by character, with what the cycle has spent on each so
    far and which start over when it completes."""
    cycle, troupe = staff_cycle(db, user, cycle_id)
    found = projects.of_troupe(db, troupe.id)
    history = projects.history(db, [p.id for p, _ in found])
    standings = projects.standings(db, cycle)
    return [
        project_out(db, p, c, history[p.id], standings.get(p.id))
        for p, c in found
        if p.status != "dropped"
    ]


@router.post("/projects/{project_id}/confirm")
def confirm(project_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ProjectOut:
    project, character, staff = a_project(db, user, project_id)
    if not staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only staff confirm a project.")
    projects.confirm(db, user, project)
    db.commit()
    return project_out(db, project, character)


@router.post("/projects/{project_id}/drop")
def drop(project_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ProjectOut:
    """Staff decline or stop a project; its player withdraws one they proposed."""
    project, character, staff = a_project(db, user, project_id)
    projects.drop(db, user, project, as_staff=staff)
    db.commit()
    return project_out(db, project, character)


@router.post("/projects/{project_id}/quest-request")
def to_quest_request(project_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ProjectOut:
    """Staff decline a proposed Research or Other project and make a quest request of
    it for the character, its name the objective."""
    project, character, staff = a_project(db, user, project_id)
    if not staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only staff make a quest request of it.")
    projects.to_quest_request(db, user, project)
    db.commit()
    return project_out(db, project, character)


@router.post("/projects/{project_id}/sheet-changed")
def sheet_changed(project_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ProjectOut:
    """Staff have changed the sheet's Morality to the finished Path change's Path."""
    project, character, staff = a_project(db, user, project_id)
    if not staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only staff change the sheet.")
    projects.sheet_changed(db, user, project)
    db.commit()
    return project_out(db, project, character)
