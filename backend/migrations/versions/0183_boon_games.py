"""boon games: the game a boon was registered at, optional, so the boon statistics
can show each game's activity (issue #702)

Revision ID: 0183
Revises: 0177
Create Date: 2026-11-12 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0183"
down_revision: str | None = "0177"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # None: registered away from a game, or before boons kept one; the statistics
    # then go by the day it was entered (horatio.boon_statistics).
    op.add_column(
        "boons",
        sa.Column(
            "game_id",
            sa.Uuid(),
            sa.ForeignKey("scheduled_games.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_boons_game_id", "boons", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_boons_game_id", table_name="boons")
    op.drop_column("boons", "game_id")
