"""A merged tag's old address leads to the tag it was merged into (#1184): each
address a tag had before a merge is kept, pointing to the tag it now belongs to.

Revision ID: 0283
Revises: 0282
Create Date: 2026-11-22 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0283"
down_revision: str | None = "0282"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blog_tag_aliases",
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["blog_tags.id"],
            name=op.f("fk_blog_tag_aliases_tag_id_blog_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_tag_aliases")),
        sa.UniqueConstraint("slug", name=op.f("uq_blog_tag_aliases_slug")),
    )
    op.create_index(
        op.f("ix_blog_tag_aliases_tag_id"), "blog_tag_aliases", ["tag_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_blog_tag_aliases_tag_id"), table_name="blog_tag_aliases")
    op.drop_table("blog_tag_aliases")
