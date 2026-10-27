"""what a troupe's game badges print: its titles, and all, negative or no status

Revision ID: 0084
Revises: 0082
Create Date: 2026-10-27 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0084"
down_revision: str | None = "0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("badge_titles", sa.Boolean(), server_default="true", nullable=False)
    )
    op.add_column(
        "troupes", sa.Column("badge_status", sa.String(), server_default="all", nullable=False)
    )
    op.create_check_constraint(
        "badge_status", "troupes", "badge_status in ('all', 'negative', 'none')"
    )


def downgrade() -> None:
    op.drop_constraint("badge_status", "troupes", type_="check")
    op.drop_column("troupes", "badge_status")
    op.drop_column("troupes", "badge_titles")
