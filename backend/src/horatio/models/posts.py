import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class NewsAgency(Record):
    """One of a troupe's in-world news agencies, such as a newspaper or a rumour
    sheet, whose stories its storytellers write (horatio.posts)."""

    __tablename__ = "news_agencies"
    __table_args__ = (
        UniqueConstraint("troupe_id", "name"),
        CheckConstraint("colour ~ '^#[0-9a-f]{6}$'", name="colour"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(default="", server_default="")
    # The masthead: its colour, always, and a picture to show in place of the name.
    colour: Mapped[str] = mapped_column(default="#8b1e1e", server_default="#8b1e1e")
    picture_id: Mapped[uuid.UUID | None]
    # Its own Discord channel; None posts to the troupe's news channel.
    discord_channel: Mapped[str | None]
    # A retired agency takes no new stories; its old ones stay.
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Post(Record):
    """A troupe's news story (horatio.posts): written, perhaps scheduled, then
    published to every member in the app and to Discord."""

    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint("kind in ('news')", name="kind"),
        CheckConstraint(
            "status in ('draft', 'proposed', 'scheduled', 'published', 'declined')",
            name="status",
        ),
        CheckConstraint("kind <> 'news' or agency_id is not null", name="agency"),
        CheckConstraint("status <> 'scheduled' or publish_at is not null", name="scheduled"),
        CheckConstraint("status <> 'published' or published_at is not null", name="published"),
        Index("ix_posts_published", "troupe_id", "kind", "published_at"),
    )

    troupe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("troupes.id"), index=True)
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default="draft", server_default="draft")
    agency_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("news_agencies.id"))
    # A story's headline.
    title: Mapped[str]
    # Markdown, from the rich text editor.
    body: Mapped[str] = mapped_column(default="", server_default="")
    # An in-world date or place shown above a story, as written.
    dateline: Mapped[str] = mapped_column(default="", server_default="")
    picture_id: Mapped[uuid.UUID | None]
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # The narrator who proposed it, kept once it is accepted, to tell them how it went.
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # A storyteller's note to the narrator, when declining or publishing their proposal.
    note: Mapped[str] = mapped_column(default="", server_default="")
    # When a scheduled post goes out; the delivery worker publishes it then.
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # Where it is on Discord while published: {"channel": id, "message_ids": [...]}.
    discord: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class PostRead(Record):
    """Someone has read a published post: it has no unread dot for them."""

    __tablename__ = "post_reads"
    __table_args__ = (UniqueConstraint("post_id", "user_id"),)

    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
