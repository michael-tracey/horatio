"""owed downtime actions

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-14 17:47:16.583073
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owed_actions",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("action_kind", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("owed_by", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_owed_actions_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owed_by"], ["users.id"], name=op.f("fk_owed_actions_owed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["cycle_participants.id"],
            name=op.f("fk_owed_actions_participant_id_cycle_participants"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_owed_actions_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owed_actions")),
    )
    op.create_index(
        op.f("ix_owed_actions_character_id"), "owed_actions", ["character_id"], unique=False
    )
    op.add_column("trait_categories", sa.Column("downtime_actions", sa.Integer(), nullable=True))
    op.add_column(
        "trait_categories",
        sa.Column(
            "downtime_waived_by",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("trait_categories", "downtime_waived_by")
    op.drop_column("trait_categories", "downtime_actions")
    op.drop_index(op.f("ix_owed_actions_character_id"), table_name="owed_actions")
    op.drop_table("owed_actions")
