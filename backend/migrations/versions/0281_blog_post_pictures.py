"""Blog articles' pictures (#1163): the pictures in an article's words, as against its
hero picture, each kept with the article it was uploaded for.

Revision ID: 0281
Revises: 0280
Create Date: 2026-11-21 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0281"
down_revision: str | None = "0280"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blog_post_pictures",
        sa.Column("post_id", sa.Uuid(), nullable=False),
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
            name=op.f("fk_blog_post_pictures_post_id_blog_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_post_pictures")),
    )
    op.create_index(
        op.f("ix_blog_post_pictures_post_id"), "blog_post_pictures", ["post_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_blog_post_pictures_post_id"), table_name="blog_post_pictures")
    op.drop_table("blog_post_pictures")
