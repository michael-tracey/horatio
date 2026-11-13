"""chronicle players: whether a troupe's players see its chronicle timeline, its
public history (issue #711)

Revision ID: 0218
Revises: 0217
Create Date: 2026-11-13 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0218"
down_revision: str | None = "0217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("chronicle_players", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "chronicle_players")
