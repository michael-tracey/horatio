"""Blog authors (#1159): each person's public profile as a writer for the game
developer blog, apart from their player profile: a display name, a handle for its
address, a short bio, links and a picture. Made when they first save it.

Revision ID: 0275
Revises: 0274
Create Date: 2026-11-21 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0275"
down_revision: str | None = "0274"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blog_authors",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("handle", sa.String(), nullable=False),
        sa.Column("bio", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "links", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("picture_id", sa.Uuid(), nullable=True),
        sa.Column("picture_crop", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_blog_authors_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_authors")),
        sa.UniqueConstraint("user_id", name=op.f("uq_blog_authors_user_id")),
    )
    op.create_index(
        "uq_blog_authors_handle_lower",
        "blog_authors",
        [sa.text("lower(handle)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("blog_authors")
