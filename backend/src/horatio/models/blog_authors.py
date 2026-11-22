import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class BlogAuthor(Record):
    """A person's public profile as a writer for the game developer blog (#1159):
    made when they first save it, and separate from their player profile, which is
    only for people signed in (horatio.api.blog_authors)."""

    __tablename__ = "blog_authors"
    __table_args__ = (
        # Their address on the blog, /blog/authors/<handle>: unique regardless of case.
        Index("uq_blog_authors_handle_lower", text("lower(handle)"), unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    display_name: Mapped[str]
    # Kept as they typed it, as a Horatio handle is.
    handle: Mapped[str]
    # Short Markdown, shown under each of their articles and on their page.
    bio: Mapped[str] = mapped_column(Text, default="", server_default="")
    # [{"label": "Bluesky", "url": "https://bsky.app/profile/..."}], as a player's are.
    links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # Its picture: squares cut as a troupe's portrait is, the crop as fractions.
    picture_id: Mapped[uuid.UUID | None]
    picture_crop: Mapped[dict[str, float] | None] = mapped_column(JSONB)
