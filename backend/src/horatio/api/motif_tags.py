"""Theme and mood tags on scenes and quests (horatio.motif_tags): what the troupe's
running staff see of them all together. Scenes and quests are tagged where they are
kept (horatio.api.scenes, horatio.api.quests). Players never see tags."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from horatio import motif_tags
from horatio.api.downtimes import staff_troupe
from horatio.auth.deps import CurrentUser, DbSession
from horatio.models import ChronicleMotif
from horatio.motif_tags import TagError
from horatio.permissions import TroupeAction

router = APIRouter(prefix="/troupes/{troupe_id}", tags=["setting style"])

Taggable = Literal["theme", "mood"]


class MotifTagsIn(BaseModel):
    # The troupe's themes and moods to tag it with: all of them, replacing any others.
    ids: list[uuid.UUID] = Field(max_length=200)


class MotifTagOut(BaseModel):
    """A theme or mood a scene or quest is tagged with."""

    id: uuid.UUID
    kind: Taggable
    name: str


class TaggedSceneOut(BaseModel):
    id: uuid.UUID
    name: str


class TaggedQuestOut(BaseModel):
    id: uuid.UUID
    name: str
    # draft | active | completed | failed | closed
    status: str


class MotifTouchedOut(MotifTagOut):
    """A theme or mood, with the scenes and quests tagged with it: none for one
    nothing has touched yet."""

    scenes: list[TaggedSceneOut]
    quests: list[TaggedQuestOut]


def tag_out(motif: ChronicleMotif) -> MotifTagOut:
    return MotifTagOut(id=motif.id, kind=motif.kind, name=motif.name)  # type: ignore[arg-type]  # checked by the database


def tags_out(motifs: list[ChronicleMotif]) -> list[MotifTagOut]:
    return [tag_out(m) for m in motifs]


def refused(error: TagError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


@router.get("/setting/tags")
def read_motif_tags(
    troupe_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[MotifTouchedOut]:
    """For running staff: every theme, then every mood, of the troupe's Setting Style
    Document, each with the scenes and quests tagged with it."""
    troupe = staff_troupe(db, user, troupe_id, TroupeAction.WRITE_SETTING)
    return [
        MotifTouchedOut(
            **tag_out(t.motif).model_dump(),
            scenes=[TaggedSceneOut(id=s.id, name=s.name) for s in t.scenes],
            quests=[TaggedQuestOut(id=q.id, name=q.name, status=q.status) for q in t.quests],
        )
        for t in motif_tags.touched(db, troupe.id)
    ]
