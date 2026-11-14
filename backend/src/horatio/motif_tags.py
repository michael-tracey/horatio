"""Theme and mood tags on scenes and quests (issue #880).

A troupe's running staff tag its scenes and quests with the themes and moods of its
Setting Style Document (horatio.setting_style), and see which of them the chronicle
touches, and how often, beside those nothing has touched yet. Tags are for staff:
players never see them. They are not part of the document, so tagging changes
nothing players read. Removing a theme or mood removes its tags; so does removing a
scene.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import case, delete, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from horatio.models import ChronicleMotif, MotifTag, Quest, Scene

# What may be a tag: not the storyteller notes.
TAGGABLE = ("theme", "mood")

# What a tag is on.
On = Literal["scene", "quest"]


class TagError(ValueError):
    """A tag the troupe has no theme or mood for."""


def in_order() -> tuple[Any, ...]:
    """Themes before moods, each in the order staff put them."""
    return (
        case((ChronicleMotif.kind == "theme", 0), else_=1),
        ChronicleMotif.position,
        ChronicleMotif.id,
    )


def taggable(db: Session, troupe_id: uuid.UUID) -> list[ChronicleMotif]:
    """The troupe's themes, then its moods."""
    return list(
        db.scalars(
            select(ChronicleMotif)
            .where(ChronicleMotif.troupe_id == troupe_id, ChronicleMotif.kind.in_(TAGGABLE))
            .order_by(*in_order())
        )
    )


def column_of(on: On) -> InstrumentedAttribute[uuid.UUID | None]:
    return MotifTag.scene_id if on == "scene" else MotifTag.quest_id


def tagged(db: Session, on: On, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[ChronicleMotif]]:
    """Each scene's or quest's tags, themes before moods."""
    column = column_of(on)
    found: dict[uuid.UUID, list[ChronicleMotif]] = {}
    if not ids:
        return found
    for tagged_id, motif in db.execute(
        select(column, ChronicleMotif)
        .join(ChronicleMotif, MotifTag.motif_id == ChronicleMotif.id)
        .where(column.in_(ids))
        .order_by(*in_order())
    ):
        if tagged_id is not None:
            found.setdefault(tagged_id, []).append(motif)
    return found


def of_scene(db: Session, scene_id: uuid.UUID) -> list[ChronicleMotif]:
    return tagged(db, "scene", [scene_id]).get(scene_id, [])


def of_quest(db: Session, quest_id: uuid.UUID) -> list[ChronicleMotif]:
    return tagged(db, "quest", [quest_id]).get(quest_id, [])


def retag(
    db: Session,
    troupe_id: uuid.UUID,
    on: On,
    tagged_id: uuid.UUID,
    ids: Sequence[uuid.UUID],
) -> list[ChronicleMotif] | None:
    """Tag a scene or quest with these of the troupe's themes and moods, and no
    others. Its tags now, or None if nothing changed."""
    column = column_of(on)
    choices = {m.id: m for m in taggable(db, troupe_id)}
    wanted = list(dict.fromkeys(ids))
    if any(i not in choices for i in wanted):
        raise TagError("Tag it with the troupe's own themes and moods.")
    had = set(db.scalars(select(MotifTag.motif_id).where(column == tagged_id)))
    if had == set(wanted):
        return None
    db.execute(
        delete(MotifTag).where(column == tagged_id, MotifTag.motif_id.not_in(wanted)),
        execution_options={"synchronize_session": False},
    )
    for motif_id in wanted:
        if motif_id not in had:
            tag = MotifTag(motif_id=motif_id)
            if on == "scene":
                tag.scene_id = tagged_id
            else:
                tag.quest_id = tagged_id
            db.add(tag)
    db.flush()
    return [m for m in choices.values() if m.id in set(wanted)]


@dataclass
class Touch:
    """A theme or mood, and the scenes and quests tagged with it."""

    motif: ChronicleMotif
    scenes: list[Scene] = field(default_factory=list[Scene])
    quests: list[Quest] = field(default_factory=list[Quest])


def touched(db: Session, troupe_id: uuid.UUID) -> list[Touch]:
    """Every theme, then every mood, of the troupe, each with what is tagged with it:
    those nothing has touched yet too."""
    touches = {m.id: Touch(m) for m in taggable(db, troupe_id)}
    for motif_id, scene in db.execute(
        select(MotifTag.motif_id, Scene)
        .join(Scene, MotifTag.scene_id == Scene.id)
        .where(MotifTag.motif_id.in_(touches))
        .order_by(Scene.name, Scene.id)
    ):
        touches[motif_id].scenes.append(scene)
    for motif_id, quest in db.execute(
        select(MotifTag.motif_id, Quest)
        .join(Quest, MotifTag.quest_id == Quest.id)
        .where(MotifTag.motif_id.in_(touches))
        .order_by(Quest.name, Quest.id)
    ):
        touches[motif_id].quests.append(quest)
    return list(touches.values())
