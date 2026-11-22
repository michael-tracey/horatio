"""Everyone hears of a new blog article on the bell (#1165): when each article's notices
went out. Those already published count as told, so none of them is sent now.

Revision ID: 0280
Revises: 0279
Create Date: 2026-11-21 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0280"
down_revision: str | None = "0279"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "blog_posts", sa.Column("everyone_told_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "update blog_posts set everyone_told_at = published_at where published_at is not null"
    )


def downgrade() -> None:
    op.drop_column("blog_posts", "everyone_told_at")
