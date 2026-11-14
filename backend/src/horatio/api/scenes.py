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

from horatio import audit, motif_tags, play_tabs
from horatio.api.downtimes import staff_troupe
from horatio.api.motif_tags import MotifTagOut, MotifTagsIn, refused, tags_out
from horatio.api.play import PlayReference, PlayView, read_play, read_reference
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
    # The troupe's themes and moods staff tagged it with (horatio.motif_tags).
    tags: list[MotifTagOut] = []


class Cleared(BaseModel):
    removed: int


class KeptCard(BaseModel):
    """One character in the troupe's scenes, with what its card shows."""

    character_id: uuid.UUID
    play: PlayView
    # The Sheet and Pools reference a sheeted card's pools come from; None for a
    # Stock NPC, whose stat block is in its Play View.
    reference: PlayReference | None


class KeptScenes(BaseModel):
    """Every scene of the troupe, with each card's Play View, for a phone to keep for
    a game with no signal (issue #503): one request on weak signal, not one a card."""

    scenes: list[SceneOut]
    cards: list[KeptCard]


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
            .order_by(SceneCharacter.position, SceneCharacter.created_at, SceneCharacter.id)
        )
    )


def pin_at_end(db: Session, scene_id: uuid.UUID, character_id: uuid.UUID) -> None:
    """Put a character after the others in the scene, unless it is there already.
    Holds the scene's row until the commit, so two pins at once take the next places
    one after the other (issue #407): each reading the last place before the other
    was saved, both took the same one, and the scene's order came out either way."""
    db.execute(select(Scene.id).where(Scene.id == scene_id).with_for_update())
    last = db.scalar(
        select(func.max(SceneCharacter.position)).where(SceneCharacter.scene_id == scene_id)
    )
    # Two storytellers pinning the same character at once pin it once.
    db.execute(
        insert(SceneCharacter)
        .values(
            scene_id=scene_id,
            character_id=character_id,
            position=0 if last is None else last + 1,
        )
        .on_conflict_do_nothing(index_elements=["scene_id", "character_id"])
    )


def members(db: Session, troupe_id: uuid.UUID, character_ids: list[uuid.UUID]) -> list[Character]:
    """Those of the characters in the troupe now: its NPCs and the PCs whose home or
    visiting troupe it is, as on its roster."""
    return list(
        db.scalars(
            select(Character)
            .join(TroupeMembership, TroupeMembership.character_id == Character.id)
            .where(
                TroupeMembership.troupe_id == troupe_id,
                TroupeMembership.left_at.is_(None),
                TroupeMembership.character_id.in_(character_ids),
            )
        )
    )


def runnable(db: Session, troupe_id: uuid.UUID, character_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Those of the characters the troupe can run in Play: its members, but no PC whose
    troupe doesn't use the Play View for players, which has none (horatio.play_tabs).
    NPCs always."""
    found = members(db, troupe_id, character_ids)
    without = play_tabs.without_play_view(db, found)
    return {c.id for c in found if c.id not in without}


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
    return SceneOut(
        **summary.model_dump(),
        characters=characters,
        stock=stock,
        tags=tags_out(motif_tags.of_scene(db, scene.id)),
    )


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


@router.get("/kept")
def kept_scenes(troupe_id: uuid.UUID, db: DbSession, user: CurrentUser) -> KeptScenes:
    """The troupe's scenes and their cards, sheeted NPCs, Stock NPCs and PCs alike,
    for its running staff to keep on a phone. Opening them this way doesn't count
    as using them."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    found = list(
        db.scalars(
            select(Scene)
            .where(Scene.troupe_id == troupe.id)
            .order_by(Scene.last_used_at.desc(), Scene.id.desc())
        )
    )
    scenes = [scene_out(db, user, troupe, s) for s in found]
    stock = {p.character_id for s in scenes for p in s.stock}
    cards: list[KeptCard] = []
    for character_id in dict.fromkeys(c for s in scenes for c in s.characters):
        try:
            play = read_play(character_id, db, user)
            reference = None if character_id in stock else read_reference(character_id, db, user)
        except HTTPException:
            continue  # gone from the troupe since it was pinned: its card says so online
        cards.append(KeptCard(character_id=character_id, play=play, reference=reference))
    return KeptScenes(scenes=scenes, cards=cards)


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


@router.put("/{scene_id}/tags")
def tag_scene(
    troupe_id: uuid.UUID, scene_id: uuid.UUID, body: MotifTagsIn, db: DbSession, user: CurrentUser
) -> SceneOut:
    """Tag the scene with these of the troupe's themes and moods, and no others."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.RUN_SCENES)
    scene = troupe_scene(db, troupe, scene_id)
    try:
        tags = motif_tags.retag(db, troupe.id, "scene", scene.id, body.ids)
    except motif_tags.TagError as error:
        raise refused(error) from None
    if tags is not None:
        audit.record(
            db,
            user,
            "scene.tagged",
            troupe_id=troupe.id,
            scene_id=scene.id,
            name=scene.name,
            tags=", ".join(m.name for m in tags) or "no themes or moods",
        )
        used(scene)
        db.commit()
    return scene_out(db, user, troupe, scene)


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
        if members(db, troupe.id, [character_id]):
            raise HTTPException(status.HTTP_409_CONFLICT, play_tabs.NO_PLAY_VIEW)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such character in this troupe.")
    pin_at_end(db, scene.id, character_id)
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
