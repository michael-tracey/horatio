"""The game developer blog's articles, its tags and their tagging (issue #1156): staff
of any troupe write articles, and the custodian publishes them. The tags are a list
the custodian keeps, seeded here with some obvious ones.

Revision ID: 0274
Revises: 0272
Create Date: 2026-11-21 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0274"
down_revision: str | None = "0272"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TAGS = (
    ("How to play", "how-to-play"),
    ("Storytelling", "storytelling"),
    ("Running a game", "running-a-game"),
    ("New players", "new-players"),
    ("Tips and tricks", "tips-and-tricks"),
    ("Downtimes", "downtimes"),
    ("Politics and boons", "politics-and-boons"),
    ("Combat and challenges", "combat-and-challenges"),
    ("Setting and lore", "setting-and-lore"),
    ("Safety and consent", "safety-and-consent"),
    ("Using Horatio", "using-horatio"),
    ("Community", "community"),
)


def record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "blog_posts",
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("slug_chosen", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("summary", sa.String(), server_default="", nullable=False),
        sa.Column("body", sa.String(), server_default="", nullable=False),
        sa.Column("picture_id", sa.Uuid(), nullable=True),
        sa.Column("featured", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("revised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unpublished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("revision_submitted_at", sa.DateTime(timezone=True), nullable=True),
        *record_columns(),
        sa.CheckConstraint(
            "status in ('draft', 'submitted', 'published', 'unpublished')",
            name=op.f("ck_blog_posts_status"),
        ),
        sa.CheckConstraint(
            "status <> 'published' or published_at is not null",
            name=op.f("ck_blog_posts_published"),
        ),
        sa.CheckConstraint(
            "status <> 'submitted' or submitted_at is not null",
            name=op.f("ck_blog_posts_submitted"),
        ),
        sa.CheckConstraint(
            "revision is null or status = 'published'", name=op.f("ck_blog_posts_revision")
        ),
        sa.CheckConstraint(
            "revision_submitted_at is null or revision is not null",
            name=op.f("ck_blog_posts_revision_submitted"),
        ),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_blog_posts_slug")),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_blog_posts_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_blog_posts_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["published_by"], ["users.id"], name=op.f("fk_blog_posts_published_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_posts")),
        sa.UniqueConstraint("slug", name=op.f("uq_blog_posts_slug")),
    )
    op.create_index(op.f("ix_blog_posts_author_id"), "blog_posts", ["author_id"])
    op.create_index(op.f("ix_blog_posts_troupe_id"), "blog_posts", ["troupe_id"])

    tags = op.create_table(
        "blog_tags",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        *record_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_blog_tags_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_blog_tags_slug")),
    )
    assert tags is not None
    op.bulk_insert(
        tags,
        [{"name": name, "slug": slug, "position": n} for n, (name, slug) in enumerate(TAGS)],
    )

    op.create_table(
        "blog_post_tags",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        *record_columns(),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["blog_posts.id"],
            name=op.f("fk_blog_post_tags_post_id_blog_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["blog_tags.id"],
            name=op.f("fk_blog_post_tags_tag_id_blog_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_post_tags")),
        sa.UniqueConstraint("post_id", "tag_id", name="uq_blog_post_tags_tag"),
    )
    op.create_index(op.f("ix_blog_post_tags_post_id"), "blog_post_tags", ["post_id"])
    op.create_index(op.f("ix_blog_post_tags_tag_id"), "blog_post_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_table("blog_post_tags")
    op.drop_table("blog_tags")
    op.drop_table("blog_posts")
