"""feeding in downtimes: difficulty by clan, the Feeding section, and half Blood

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rule_sets",
        sa.Column(
            "feeding_modifiers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "downtime_cycles",
        sa.Column(
            "feeding_difficulty",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "cycle_participants",
        sa.Column("feeding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column(
            "feeding",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column("submissions", sa.Column("feeding_result", sa.String(), nullable=True))
    op.add_column(
        "submissions",
        sa.Column("feeding_reply", sa.String(), server_default="", nullable=False),
    )
    op.add_column(
        "submissions",
        sa.Column("feeding_working", sa.String(), server_default="", nullable=False),
    )
    op.add_column("submissions", sa.Column("feeding_answered_by", sa.Uuid(), nullable=True))
    op.add_column(
        "submissions",
        sa.Column("feeding_answered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_submissions_feeding_result"),
        "submissions",
        "feeding_result is null or feeding_result in ('full', 'half', 'other')",
    )
    op.create_foreign_key(
        op.f("fk_submissions_feeding_answered_by_users"),
        "submissions",
        "users",
        ["feeding_answered_by"],
        ["id"],
    )
    op.add_column(
        "characters",
        sa.Column("half_blood_next_game", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "play_games",
        sa.Column("half_blood", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_table(
        "feeding_adjustments",
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("adjusted_by", sa.Uuid(), nullable=False),
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
            ["adjusted_by"], ["users.id"], name=op.f("fk_feeding_adjustments_adjusted_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["cycle_participants.id"],
            name=op.f("fk_feeding_adjustments_participant_id_cycle_participants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feeding_adjustments")),
    )
    op.create_index(
        op.f("ix_feeding_adjustments_participant_id"),
        "feeding_adjustments",
        ["participant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_feeding_adjustments_participant_id"), table_name="feeding_adjustments")
    op.drop_table("feeding_adjustments")
    op.drop_column("play_games", "half_blood")
    op.drop_column("characters", "half_blood_next_game")
    op.drop_constraint(
        op.f("fk_submissions_feeding_answered_by_users"), "submissions", type_="foreignkey"
    )
    op.drop_constraint(op.f("ck_submissions_feeding_result"), "submissions", type_="check")
    op.drop_column("submissions", "feeding_answered_at")
    op.drop_column("submissions", "feeding_answered_by")
    op.drop_column("submissions", "feeding_working")
    op.drop_column("submissions", "feeding_reply")
    op.drop_column("submissions", "feeding_result")
    op.drop_column("submissions", "feeding")
    op.drop_column("cycle_participants", "feeding")
    op.drop_column("downtime_cycles", "feeding_difficulty")
    op.drop_column("rule_sets", "feeding_modifiers")
