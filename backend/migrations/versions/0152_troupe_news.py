"""troupe news: news agencies, their stories, who has read each, and stories'
deliveries to Discord (issue #510)

Revision ID: 0152
Revises: 0151
Create Date: 2026-11-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0152"
down_revision: str | None = "0151"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def stamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


OLD_ONE_SUBJECT = (
    "(submission_id is not null and quest_id is null and character_id is null)"
    " or (submission_id is null and quest_id is not null and character_id is not null)"
)
ONE_SUBJECT = (
    "(submission_id is not null and quest_id is null and character_id is null"
    " and post_id is null)"
    " or (submission_id is null and quest_id is not null and character_id is not null"
    " and post_id is null)"
    " or (submission_id is null and quest_id is null and character_id is null"
    " and post_id is not null)"
)


def upgrade() -> None:
    op.create_table(
        "news_agencies",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), server_default="", nullable=False),
        sa.Column("colour", sa.String(), server_default="#8b1e1e", nullable=False),
        sa.Column("picture_id", sa.Uuid(), nullable=True),
        sa.Column("discord_channel", sa.String(), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        *stamps(),
        sa.CheckConstraint("colour ~ '^#[0-9a-f]{6}$'", name=op.f("ck_news_agencies_colour")),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_news_agencies_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_agencies")),
        sa.UniqueConstraint("troupe_id", "name", name=op.f("uq_news_agencies_troupe_id")),
    )
    op.create_index(
        op.f("ix_news_agencies_troupe_id"), "news_agencies", ["troupe_id"], unique=False
    )

    op.create_table(
        "posts",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column("agency_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.String(), server_default="", nullable=False),
        sa.Column("dateline", sa.String(), server_default="", nullable=False),
        sa.Column("picture_id", sa.Uuid(), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_by", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column(
            "discord",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        *stamps(),
        sa.CheckConstraint("kind in ('news')", name=op.f("ck_posts_kind")),
        sa.CheckConstraint(
            "status in ('draft', 'proposed', 'scheduled', 'published', 'declined')",
            name=op.f("ck_posts_status"),
        ),
        sa.CheckConstraint("kind <> 'news' or agency_id is not null", name=op.f("ck_posts_agency")),
        sa.CheckConstraint(
            "status <> 'scheduled' or publish_at is not null", name=op.f("ck_posts_scheduled")
        ),
        sa.CheckConstraint(
            "status <> 'published' or published_at is not null", name=op.f("ck_posts_published")
        ),
        sa.ForeignKeyConstraint(
            ["agency_id"], ["news_agencies.id"], name=op.f("fk_posts_agency_id_news_agencies")
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name=op.f("fk_posts_author_id_users")),
        sa.ForeignKeyConstraint(
            ["proposed_by"], ["users.id"], name=op.f("fk_posts_proposed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["published_by"], ["users.id"], name=op.f("fk_posts_published_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_posts_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
    )
    op.create_index(op.f("ix_posts_troupe_id"), "posts", ["troupe_id"], unique=False)
    op.create_index(
        "ix_posts_published", "posts", ["troupe_id", "kind", "published_at"], unique=False
    )

    op.create_table(
        "post_reads",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *stamps(),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"], name=op.f("fk_post_reads_post_id_posts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_post_reads_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_reads")),
        sa.UniqueConstraint("post_id", "user_id", name=op.f("uq_post_reads_post_id")),
    )
    op.create_index(op.f("ix_post_reads_user_id"), "post_reads", ["user_id"], unique=False)

    op.add_column("deliveries", sa.Column("post_id", sa.Uuid(), nullable=True))
    op.add_column("deliveries", sa.Column("action", sa.String(), nullable=True))
    op.create_index(op.f("ix_deliveries_post_id"), "deliveries", ["post_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_deliveries_post_id_posts"),
        "deliveries",
        "posts",
        ["post_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f("ck_deliveries_one_subject"), "deliveries", type_="check")
    op.create_check_constraint(op.f("ck_deliveries_one_subject"), "deliveries", ONE_SUBJECT)
    op.create_check_constraint(
        op.f("ck_deliveries_action"),
        "deliveries",
        "(post_id is null) = (action is null) and action in ('sync', 'delete')",
    )


def downgrade() -> None:
    op.execute("delete from deliveries where post_id is not null")
    op.drop_constraint(op.f("ck_deliveries_action"), "deliveries", type_="check")
    op.drop_constraint(op.f("ck_deliveries_one_subject"), "deliveries", type_="check")
    op.create_check_constraint(op.f("ck_deliveries_one_subject"), "deliveries", OLD_ONE_SUBJECT)
    op.drop_constraint(op.f("fk_deliveries_post_id_posts"), "deliveries", type_="foreignkey")
    op.drop_index(op.f("ix_deliveries_post_id"), table_name="deliveries")
    op.drop_column("deliveries", "action")
    op.drop_column("deliveries", "post_id")
    op.drop_index(op.f("ix_post_reads_user_id"), table_name="post_reads")
    op.drop_table("post_reads")
    op.drop_index("ix_posts_published", table_name="posts")
    op.drop_index(op.f("ix_posts_troupe_id"), table_name="posts")
    op.drop_table("posts")
    op.drop_index(op.f("ix_news_agencies_troupe_id"), table_name="news_agencies")
    op.drop_table("news_agencies")
