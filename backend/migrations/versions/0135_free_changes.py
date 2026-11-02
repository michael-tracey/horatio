"""Free changes for new characters (issue #439): the troupe's setting (none, by date
or by games played, with its excluded traits), when a character's ended, which held
purchases are free changes, and the kind of a game attendance, so that an absentee
game (issue #438) never counts as one attended.

Revision ID: 0135
Revises: 0127
Create Date: 2026-11-01 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0135"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("free_changes", sa.String(), server_default="none", nullable=False)
    )
    op.create_check_constraint(
        "free_changes", "troupes", "free_changes in ('none', 'date', 'games')"
    )
    op.add_column(
        "troupes",
        sa.Column("free_changes_days", sa.Integer(), server_default="30", nullable=False),
    )
    op.add_column(
        "troupes",
        sa.Column("free_changes_games", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "troupes",
        sa.Column("free_changes_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "troupes",
        sa.Column(
            "free_changes_excluded",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "characters",
        sa.Column("free_changes_ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "discipline_purchases",
        sa.Column("free_change", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "game_attendances",
        sa.Column("kind", sa.String(), server_default="attended", nullable=False),
    )
    op.create_check_constraint("kind", "game_attendances", "kind in ('attended', 'absentee')")


def downgrade() -> None:
    op.drop_constraint("kind", "game_attendances", type_="check")
    op.drop_column("game_attendances", "kind")
    op.drop_column("discipline_purchases", "free_change")
    op.drop_column("characters", "free_changes_ended_at")
    op.drop_column("troupes", "free_changes_excluded")
    op.drop_column("troupes", "free_changes_since")
    op.drop_column("troupes", "free_changes_games")
    op.drop_column("troupes", "free_changes_days")
    op.drop_constraint("free_changes", "troupes", type_="check")
    op.drop_column("troupes", "free_changes")
