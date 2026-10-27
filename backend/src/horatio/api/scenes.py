"""A troupe's named scenes for the Scene view, kept on the server (issue #231).

Every running staff member sees all of the troupe's scenes, opens any of them and
pins or unpins in it, so storytellers can share one for a big fight. A scene's
maker, the lead storyteller and the custodian rename or remove it. Removing a
scene only takes it off the list: its characters and their play are untouched.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from horatio import audit
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.auth.viewing import read_only
from horatio.models import (
    Character,
    Scene,
    SceneCharacter,
    StockNpc,
    Troupe,
    TroupeMembership,
    User,
)
from horatio.permissions import TroupeAction, allows, troupe_role

router = APIRouter(prefix="/troupes/{troupe_id}/scenes", tags=["scenes"])

# Opening a scene counts as using it, but the page refreshes every few seconds
# while it is open; once in this long is enough.
USED_EVERY = timedelta(minutes=5)


class SceneName(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def trimmed(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("A scene needs a name.")
        return name


class NewScene(SceneName):
    # Characters to start with, in order, such as a scene kept on a device before
    # scenes were on the server. Any the troupe cannot run in Play are left out.
    characters: list[uuid.UUID] = Field(default_factory=list[uuid.UUID], max_length=200)


class SceneSummary(BaseModel):
    id: uuid.UUID
    name: str
    created_by_id: uuid.UUID
    created_by_name: str
    created_at: datetime
    last_used_at: datetime
    # How many characters are pinned.
    count: int
    # The one asking made it.
    mine: bool
    # The one asking may rename or remove it.
    can_change: bool


class StockPin(BaseModel):
    """A Stock NPC in the scene, whose card is the Stock one (issue #215): its
    trackers come from its Play View, as anyone's do."""

    character_id: uuid.UUID
    name: str
    rating: int


class SceneOut(SceneSummary):
    # The pinned characters, in order.
    characters: list[uuid.UUID]
    # Those of them that are Stock NPCs.
    stock: list[StockPin]


class Cleared(BaseModel):
    removed: int


def may_change(db: Session, user: User, troupe: Troupe, scene: Scene) -> bool:
    return scene.created_by_id == user.id or allows(
        troupe_role(db, user, troupe), TroupeAction.CHANGE_ANY_SCENE, is_custodian=user.is_custodian
    )


def troupe_scene(db: Session, troupe: Troupe, scene_id: uuid.UUID) -> Scene:
    scene = db.get(Scene, scene_id)
    if scene is None or scene.troupe_id != troupe.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such scene.")
    return scene


def changeable_scene(db: Session, user: User, troupe: Troupe, scene_id: uuid.UUID) -> Scene:
    scene = troupe_scene(db, troupe, scene_id)
    if not may_change(db, user, troupe, scene):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only its maker or the lead storyteller can change a scene."
        )
    return scene


def pinned(db: Session, scene_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(SceneCharacter.character_id)
            .where(SceneCharacter.scene_id == scene_id)
            .order_by(SceneCharacter.position, SceneCharacter.created_at)
        )
    )


def runnable(db: Session, troupe_id: uuid.UUID, character_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Those of the characters the troupe can run in Play: the ones in it now, its
    NPCs and the PCs whose home or visiting troupe it is, as on its roster."""
    return set(
        db.scalars(
            select(TroupeMembership.character_id).where(
                TroupeMembership.troupe_id == troupe_id,
                TroupeMembership.left_at.is_(None),
                TroupeMembership.character_id.in_(character_ids),
            )
        )
    )


def summaries(db: Session, user: User, troupe: Troupe, scenes: list[Scene]) -> list[SceneSummary]:
    ids = [s.id for s in scenes]
    counts: dict[uuid.UUID, int] = {
        scene_id: count
        for scene_id, count in db.execute(
            select(SceneCharacter.scene_id, func.count())
            .where(SceneCharacter.scene_id.in_(ids))
            .group_by(SceneCharacter.scene_id)
        )
    }
    makers: dict[uuid.UUID, str] = {
        user_id: name
        for user_id, name in db.execute(
            select(User.id, User.display_name).where(User.id.in_({s.created_by_id for s in scenes}))
        )
    }
    lead = allows(
        troupe_role(db, user, troupe), TroupeAction.CHANGE_ANY_SCENE, is_custodian=user.is_custodian
    )
    return [
        SceneSummary(
            id=s.id,
            name=s.name,
            created_by_id=s.created_by_id,
            created_by_name=makers.get(s.created_by_id, "Someone"),
            created_at=s.created_at,
            last_used_at=s.last_used_at,
            count=counts.get(s.id, 0),
            mine=s.created_by_id == user.id,
            can_change=lead or s.created_by_id == user.id,
        )
        for s in scenes
    ]


def scene_out(db: Session, user: User, troupe: Troupe, scene: Scene) -> SceneOut:
    (summary,) = summaries(db, user, troupe, [scene])
    characters = pinned(db, scene.id)
    stock = [
        StockPin(character_id=character_id, name=name, rating=rating)
        for character_id, name, rating in db.execute(
            select(Character.id, Character.name, StockNpc.rating)
            .join(StockNpc, StockNpc.character_id == Character.id)
            .where(Character.id.in_(characters), Character.npc_form == "stock")
        )
    ]
    return SceneOut(**summary.model_dump(), characters=characters, stock=stock)


def used(scene: Scene) -> None:
    scene.last_used_at = datetime.now(UTC)


@router.get("")
def list_scenes(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser, mine: bool = False
) -> list[SceneSummary]:
    """The troupe's scenes, the most lately used first; with `mine`, only those the
    one asking made."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    query = select(Scene).where(Scene.troupe_id == troupe.id)
    if mine:
        query = query.where(Scene.created_by_id == user.id)
    scenes = list(db.scalars(query.order_by(Scene.last_used_at.desc(), Scene.id.desc())))
    return summaries(db, user, troupe, scenes)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_scene(
    troupe_id: uuid.UUID, body: NewScene, db: DbSession, user: CurrentUser
) -> SceneOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    scene = Scene(troupe_id=troupe.id, name=body.name, created_by_id=user.id)
    db.add(scene)
    db.flush()
    allowed = runnable(db, troupe.id, body.characters)
    wanted = [c for c in dict.fromkeys(body.characters) if c in allowed]
    for position, character_id in enumerate(wanted):
        db.add(SceneCharacter(scene_id=scene.id, character_id=character_id, position=position))
    audit.record(db, user, "scene.created", troupe_id=troupe.id, scene_id=scene.id, name=scene.name)
    db.commit()
    return scene_out(db, user, troupe, scene)


@router.delete("")
def clear_scenes(
    troupe_id: uuid.UUID, unused_since: datetime, db: DbSession, user: CurrentUser
) -> Cleared:
    """Remove every scene in the troupe not used since `unused_since`."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.CHANGE_ANY_SCENE)
    if unused_since.tzinfo is None:
        unused_since = unused_since.replace(tzinfo=UTC)
    removed = db.execute(
        delete(Scene)
        .where(Scene.troupe_id == troupe.id, Scene.last_used_at < unused_since)
        .returning(Scene.id)
    ).all()
    if removed:
        audit.record(
            db,
            user,
            "scene.cleared",
            troupe_id=troupe.id,
            count=len(removed),
            since=unused_since.date().isoformat(),
        )
    db.commit()
    return Cleared(removed=len(removed))


@router.get("/{scene_id}")
def read_scene(
    troupe_id: uuid.UUID, scene_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> SceneOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    scene = troupe_scene(db, troupe, scene_id)
    # Not while the custodian views as someone: that changes nothing (horatio.auth.viewing).
    if datetime.now(UTC) - scene.last_used_at > USED_EVERY and not read_only(db):
        used(scene)
        db.commit()
    return scene_out(db, user, troupe, scene)


@router.patch("/{scene_id}")
def rename_scene(
    troupe_id: uuid.UUID, scene_id: uuid.UUID, body: SceneName, db: DbSession, user: CurrentUser
) -> SceneOut:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    scene = changeable_scene(db, user, troupe, scene_id)
    if body.name != scene.name:
        audit.record(
            db,
            user,
            "scene.renamed",
            troupe_id=troupe.id,
            scene_id=scene.id,
            old=scene.name,
            name=body.name,
        )
        scene.name = body.name
        used(scene)
        db.commit()
    return scene_out(db, user, troupe, scene)


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_scene(
    troupe_id: uuid.UUID, scene_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Response:
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    scene = changeable_scene(db, user, troupe, scene_id)
    audit.record(db, user, "scene.removed", troupe_id=troupe.id, scene_id=scene.id, name=scene.name)
    db.delete(scene)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{scene_id}/characters/{character_id}")
def pin(
    troupe_id: uuid.UUID,
    scene_id: uuid.UUID,
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> SceneOut:
    """Pin a character at the end of the scene; nothing changes if it is there."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    scene = troupe_scene(db, troupe, scene_id)
    if character_id not in runnable(db, troupe.id, [character_id]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character in this troupe.")
    last = db.scalar(
        select(func.max(SceneCharacter.position)).where(SceneCharacter.scene_id == scene.id)
    )
    # Two storytellers pinning the same character at once pin it once.
    db.execute(
        insert(SceneCharacter)
        .values(
            scene_id=scene.id,
            character_id=character_id,
            position=0 if last is None else last + 1,
        )
        .on_conflict_do_nothing(index_elements=["scene_id", "character_id"])
    )
    used(scene)
    db.commit()
    return scene_out(db, user, troupe, scene)


@router.delete("/{scene_id}/characters/{character_id}")
def unpin(
    troupe_id: uuid.UUID,
    scene_id: uuid.UUID,
    character_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> SceneOut:
    """Take a character off the scene. It stays in the troupe, as it was."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    scene = troupe_scene(db, troupe, scene_id)
    db.execute(
        delete(SceneCharacter).where(
            SceneCharacter.scene_id == scene.id, SceneCharacter.character_id == character_id
        )
    )
    used(scene)
    db.commit()
    return scene_out(db, user, troupe, scene)
