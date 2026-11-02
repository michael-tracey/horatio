"""Retainer upkeep and growth (issue #442): a troupe's house rules for them, the
day a Retainer was left neglected, what upkeep each Play View night took, the
upkeep a downtime charged to the next game, and the XP each Retainer gained.

Revision ID: 0139
Revises: 0137
Create Date: 2026-11-01 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0139"
down_revision: str | None = "0137"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column(
            "retainer_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column("retainers", sa.Column("neglected_on", sa.Date(), nullable=True))
    op.add_column(
        "characters",
        sa.Column("upkeep_next_game", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "play_games", sa.Column("upkeep", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "play_events", sa.Column("upkeep", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.create_table(
        "retainer_growth",
        sa.Column("retainer_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=True),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("banked", sa.Boolean(), nullable=False),
        sa.Column("npc_id", sa.Uuid(), nullable=True),
        sa.Column("xp_entry_id", sa.Uuid(), nullable=True),
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
            ["retainer_id"],
            ["retainers.id"],
            name=op.f("fk_retainer_growth_retainer_id_retainers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["downtime_cycles.id"],
            name=op.f("fk_retainer_growth_cycle_id_downtime_cycles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["npc_id"],
            ["characters.id"],
            name=op.f("fk_retainer_growth_npc_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["xp_entry_id"],
            ["xp_entries.id"],
            name=op.f("fk_retainer_growth_xp_entry_id_xp_entries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retainer_growth")),
    )
    op.create_index(
        op.f("ix_retainer_growth_retainer_id"), "retainer_growth", ["retainer_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_retainer_growth_retainer_id"), table_name="retainer_growth")
    op.drop_table("retainer_growth")
    op.drop_column("play_events", "upkeep")
    op.drop_column("play_games", "upkeep")
    op.drop_column("characters", "upkeep_next_game")
    op.drop_column("retainers", "neglected_on")
    op.drop_column("troupes", "retainer_rules")
