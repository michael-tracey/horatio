"""influence spent at games: owed actions linked to the tap, and to what they took off

Revision ID: 0047
Revises: 0044
Create Date: 2026-10-21 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("owed_actions", sa.Column("play_event_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_owed_actions_play_event_id"), "owed_actions", ["play_event_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_owed_actions_play_event_id_play_events"),
        "owed_actions",
        "play_events",
        ["play_event_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column("allowance_adjustments", sa.Column("owed_action_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_allowance_adjustments_owed_action_id"),
        "allowance_adjustments",
        ["owed_action_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_allowance_adjustments_owed_action_id_owed_actions"),
        "allowance_adjustments",
        "owed_actions",
        ["owed_action_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_allowance_adjustments_owed_action_id_owed_actions"),
        "allowance_adjustments",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_allowance_adjustments_owed_action_id"), table_name="allowance_adjustments"
    )
    op.drop_column("allowance_adjustments", "owed_action_id")
    op.drop_constraint(
        op.f("fk_owed_actions_play_event_id_play_events"), "owed_actions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_owed_actions_play_event_id"), table_name="owed_actions")
    op.drop_column("owed_actions", "play_event_id")
