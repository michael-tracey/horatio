"""house titles: their sect and the abiding status they give

Revision ID: 0081
Revises: 0080
Create Date: 2026-10-27 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0081"
down_revision: str | None = "0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("troupe_titles", sa.Column("sect", sa.String(), nullable=True))
    op.add_column(
        "troupe_titles",
        sa.Column(
            "status",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("troupe_titles", "status")
    op.drop_column("troupe_titles", "sect")
