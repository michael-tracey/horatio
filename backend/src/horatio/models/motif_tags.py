import uuid

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class MotifTag(Record):
    """A scene or a quest tagged with one of the troupe's themes or moods
    (ChronicleMotif), so its staff see which the chronicle touches (issue #880,
    horatio.motif_tags). For staff only. It goes with its theme or mood, and with
    its scene or quest."""

    __tablename__ = "motif_tags"
    __table_args__ = (
        CheckConstraint("num_nonnulls(scene_id, quest_id) = 1", name="one_tagged"),
        UniqueConstraint("motif_id", "scene_id", name="uq_motif_tags_scene"),
        UniqueConstraint("motif_id", "quest_id", name="uq_motif_tags_quest"),
    )

    motif_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chronicle_motifs.id", ondelete="CASCADE"), index=True
    )
    # What it tags: a scene or a quest, never both.
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    quest_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quests.id", ondelete="CASCADE"), index=True
    )
