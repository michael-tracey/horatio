"""Choosing the night's status at check-in (issue #441): a troupe's optional setting
that each character's source of abiding status is chosen as it checks in to a game,
and fixed for that game. The choice itself is kept with the night's other status
choices (PlayGame.status).

Revision ID: 0141
Revises: 0136
Create Date: 2026-11-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0141"
down_revision: str | None = "0136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("status_at_checkin", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "status_at_checkin")
