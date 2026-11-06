import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class Nomination(Record):
    """A Player Nomination (horatio.nominations): a short note in a downtime praising
    someone's roleplaying, read by the troupe's running staff and published to its
    players without its author."""

    __tablename__ = "nominations"
    __table_args__ = (
        CheckConstraint("about_character_id is null or about_user_id is null", name="one_about"),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("downtime_cycles.id"), index=True)
    # Who wrote it: the character, and through it the player, taking part in the
    # cycle. Only running staff ever see it.
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cycle_participants.id"), index=True
    )
    text: Mapped[str]
    # Who it is about, if the player linked it: a character in the troupe, or one of
    # its staff. The text says it either way.
    about_character_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("characters.id"), index=True
    )
    about_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Taken out of what is published, with a reason for staff only; kept, and can be
    # put back.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    removed_reason: Mapped[str] = mapped_column(default="", server_default="")
    # Starred, it rotates in the footer of the troupe's pages once published.
    starred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    starred_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # The last light edit by staff, such as a typo or a real name taken out.
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # When it was published, and its place in its month's shuffled order, fixed then.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shuffle_key: Mapped[float | None]
