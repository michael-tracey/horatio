import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from horatio.models.base import Record


class BlogPost(Record):
    """An article for the site-wide game developer blog (issue #1156, horatio.blog):
    written by a member of staff of any troupe, published by the custodian. Not a
    troupe's post (horatio.posts): it belongs to no troupe, though it may name the
    one its author runs."""

    __tablename__ = "blog_posts"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'submitted', 'published', 'unpublished')", name="status"
        ),
        CheckConstraint("status <> 'published' or published_at is not null", name="published"),
        CheckConstraint("status <> 'submitted' or submitted_at is not null", name="submitted"),
        CheckConstraint("revision is null or status = 'published'", name="revision"),
        CheckConstraint(
            "revision_submitted_at is null or revision is not null", name="revision_submitted"
        ),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug"),
    )

    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # The troupe it names, one where the author was on staff when they submitted it;
    # kept if they leave it. None names none.
    troupe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("troupes.id"), index=True)
    status: Mapped[str] = mapped_column(default="draft", server_default="draft")
    title: Mapped[str]
    # Its address on the blog, made from the title; fixed once first published.
    slug: Mapped[str] = mapped_column(unique=True)
    # Set by hand: the title no longer changes it.
    slug_chosen: Mapped[bool] = mapped_column(default=False, server_default="false")
    # A line or two for lists and link previews.
    summary: Mapped[str] = mapped_column(default="", server_default="")
    # Markdown, from the rich text editor.
    body: Mapped[str] = mapped_column(default="", server_default="")
    # Its hero picture (horatio.pictures, "blog"), or None.
    picture_id: Mapped[uuid.UUID | None]
    featured: Mapped[bool] = mapped_column(default=False, server_default="false")
    # The custodian's note to the author: why it came back, or why it was unpublished.
    note: Mapped[str] = mapped_column(default="", server_default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When it was first published: its date on the blog, kept through unpublishing.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # When changes to it were last published.
    revised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unpublished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Changes to a published article, waiting for the custodian while the published
    # version stays up: {"title", "summary", "body", "troupe_id", "picture_id"}.
    revision: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    # When those changes were sent to the custodian; None while still being written.
    revision_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When everyone was told of it on the bell, once, after it was first published
    # (horatio.blog_bell); None until then.
    everyone_told_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BlogTag(Record):
    """One of the blog's tags, a list the custodian keeps (seeded by its migration, kept
    in Custodian › Blog › Tags, horatio.blog_tags)."""

    __tablename__ = "blog_tags"
    # No two tags share a name, whatever the case (#1161).
    __table_args__ = (Index("uq_blog_tags_name_lower", text("lower(name)"), unique=True),)

    name: Mapped[str]
    # Its address on the blog's tag pages, made from its name. It follows the name
    # until a published article carries it, then stays (horatio.blog_tags).
    slug: Mapped[str] = mapped_column(unique=True)
    # Where it comes in the list.
    position: Mapped[int] = mapped_column(default=0, server_default="0")
    # Retired: it stays on the articles that have it, and shows on them, but isn't
    # chosen for any more.
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BlogPostTag(Record):
    """An article tagged with one of the blog's tags."""

    __tablename__ = "blog_post_tags"
    __table_args__ = (UniqueConstraint("post_id", "tag_id", name="uq_blog_post_tags_tag"),)

    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blog_posts.id", ondelete="CASCADE"), index=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blog_tags.id", ondelete="CASCADE"), index=True
    )


class BlogPostPicture(Record):
    """A picture in a blog article's words (#1163), as against its hero picture. Its id
    is the picture's: the article's Markdown names it as `blog-picture:<id>`, and its
    files are under `blog-pictures/<post_id>/<id>` (horatio.pictures). Shown to
    anyone once the published article's words name it, and to its author and the
    custodian before; gone once no version of the article names it."""

    __tablename__ = "blog_post_pictures"

    post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blog_posts.id", ondelete="CASCADE"), index=True
    )
