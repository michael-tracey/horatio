"""The custodian keeps the blog's tags (#1161): a tag can be retired, staying on the
articles that have it but no longer chosen, and no two tags share a name whatever
the case.

Revision ID: 0279
Revises: 0275
Create Date: 2026-11-21 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0279"
down_revision: str | None = "0275"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("blog_tags", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("uq_blog_tags_name", "blog_tags", type_="unique")
    op.create_index(
        "uq_blog_tags_name_lower", "blog_tags", [sa.literal_column("lower(name)")], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_blog_tags_name_lower", table_name="blog_tags")
    op.create_unique_constraint("uq_blog_tags_name", "blog_tags", ["name"])
    op.drop_column("blog_tags", "retired_at")
