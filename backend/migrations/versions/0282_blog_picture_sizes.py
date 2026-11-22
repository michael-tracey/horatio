"""Blog pictures' sizes (#1183): each copy's width and height, for the pictures in an
article's words and for hero pictures, so a page keeps their room before they load.

Pictures uploaded before this have none here. They get them the first time they are
shown, read from their files (horatio.blog_pictures): this migration can't read them,
as it runs in a container the uploads aren't mounted in (deploy/playbook.yml).

Revision ID: 0282
Revises: 0281
Create Date: 2026-11-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0282"
down_revision: str | None = "0281"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "blog_post_pictures",
        sa.Column("sizes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "blog_hero_pictures",
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("sizes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["blog_posts.id"],
            name=op.f("fk_blog_hero_pictures_post_id_blog_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_hero_pictures")),
    )
    op.create_index(
        op.f("ix_blog_hero_pictures_post_id"), "blog_hero_pictures", ["post_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_blog_hero_pictures_post_id"), table_name="blog_hero_pictures")
    op.drop_table("blog_hero_pictures")
    op.drop_column("blog_post_pictures", "sizes")
