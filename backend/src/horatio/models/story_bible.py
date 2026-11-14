import uuid

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class StoryBibleNote(Record):
    """A note in a troupe's story bible (horatio.story_bible): what its running staff
    keep for themselves beside the Setting Style Document. Players never read it.
    Deleted outright: nothing holds it."""

    __tablename__ = "story_bible_notes"
    __table_args__ = (
        # One note at each place. Checked at commit, so a reorder can swap two places.
        UniqueConstraint(
            "troupe_id",
            "position",
            name="uq_story_bible_notes_place",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    # Its heading ("The Prince's secret").
    title: Mapped[str]
    # Markdown: the note itself.
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Its place in the bible, from 1.
    position: Mapped[int]
