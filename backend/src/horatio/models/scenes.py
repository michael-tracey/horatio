import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Scene(Record):
    """A named scene a troupe's running staff keep for a game: which of its
    characters are on one page of the Scene view, in order (issue #231). Any of
    them can open it and pin or unpin; its maker or the lead storyteller renames
    or removes it. Removing one never touches its characters or their play."""

    __tablename__ = "scenes"
    __table_args__ = (CheckConstraint("char_length(name) between 1 and 80", name="name_length"),)

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # When someone last opened it or changed it.
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SceneCharacter(Record):
    """A character pinned to a scene, at its place on the page."""

    __tablename__ = "scene_characters"
    __table_args__ = (UniqueConstraint("scene_id", "character_id"),)

    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    # A deleted character (an NPC its troupe deleted) leaves every scene.
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    # From 0, left to right; a gap is harmless.
    position: Mapped[int]
