"""play tabs: a troupe switches each of the Play View's tabs on or off for its
players, all on by default; with every one off it doesn't use the Play View
(issue #673)

Revision ID: 0163
Revises: 0162
Create Date: 2026-11-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0163"
down_revision: str | None = "0162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The tabs switched off: none, so every troupe keeps every tab.
    op.add_column(
        "troupes",
        sa.Column("play_tabs_off", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("troupes", "play_tabs_off")
