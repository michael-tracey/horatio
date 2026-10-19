"""troupe xp defaults and xp for completing a downtime

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-20 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("session_xp", sa.Integer(), server_default="8", nullable=False)
    )
    op.add_column(
        "troupes", sa.Column("downtime_xp", sa.Integer(), server_default="2", nullable=False)
    )
    op.add_column(
        "downtime_cycles",
        sa.Column("completion_xp", sa.Integer(), server_default="2", nullable=False),
    )
    op.add_column(
        "cycle_participants", sa.Column("completion_xp_entry_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_cycle_participants_completion_xp_entry_id_xp_entries"),
        "cycle_participants",
        "xp_entries",
        ["completion_xp_entry_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_cycle_participants_completion_xp_entry_id_xp_entries"),
        "cycle_participants",
        type_="foreignkey",
    )
    op.drop_column("cycle_participants", "completion_xp_entry_id")
    op.drop_column("downtime_cycles", "completion_xp")
    op.drop_column("troupes", "downtime_xp")
    op.drop_column("troupes", "session_xp")
