"""A troupe's teacher rules (issue #440): which traits need a teacher, for whom and
when, what the teacher must hold, and what learning costs besides; and the teaching
each purchase asked for, with the teacher's Willpower

Revision ID: 0140
Revises: 0132
Create Date: 2026-11-02 09:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0140"
down_revision: str | None = "0132"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "teacher_rules",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("splat", sa.String(), server_default="vampire", nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column(
            "names",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("name_prefix", sa.String(), nullable=True),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("always", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("holds", sa.String(), server_default="same", nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("actions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("willpower", sa.Integer(), server_default="0", nullable=False),
        sa.Column("games", sa.Integer(), server_default="0", nullable=False),
        *timestamps(),
        sa.CheckConstraint("holds in ('same', 'rating')", name=op.f("ck_teacher_rules_holds")),
        sa.CheckConstraint(
            "holds = 'same' or rating is not null", name=op.f("ck_teacher_rules_rating")
        ),
        sa.CheckConstraint("willpower = 0 or games > 0", name=op.f("ck_teacher_rules_games")),
        sa.CheckConstraint(
            "jsonb_array_length(names) = 0 or name_prefix is null",
            name=op.f("ck_teacher_rules_subject"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_teacher_rules_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teacher_rules")),
    )
    op.create_index(
        op.f("ix_teacher_rules_troupe_id"), "teacher_rules", ["troupe_id"], unique=False
    )
    op.create_table(
        "teachings",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=False),
        sa.Column("detail", sa.String(), server_default="", nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=True),
        sa.Column("teacher_name", sa.String(), nullable=False),
        sa.Column("actions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("willpower", sa.Integer(), server_default="0", nullable=False),
        sa.Column("games", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(), server_default="not_needed", nullable=False),
        sa.Column("answered_by", sa.Uuid(), nullable=True),
        sa.Column("spent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("spent_game_id", sa.Uuid(), nullable=True),
        sa.Column("tap_id", sa.Uuid(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status in ('not_needed', 'asked', 'spent', 'refused', 'given_back')",
            name=op.f("ck_teachings_status"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"], ["characters.id"], name=op.f("fk_teachings_character_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_teachings_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"], ["approvals.id"], name=op.f("fk_teachings_approval_id_approvals")
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["teacher_rules.id"],
            name=op.f("fk_teachings_rule_id_teacher_rules"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_teachings_trait_definition_id_trait_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"], ["characters.id"], name=op.f("fk_teachings_teacher_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["answered_by"], ["users.id"], name=op.f("fk_teachings_answered_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["spent_game_id"],
            ["play_games.id"],
            name=op.f("fk_teachings_spent_game_id_play_games"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teachings")),
        sa.UniqueConstraint("approval_id", name=op.f("uq_teachings_approval_id")),
    )
    op.create_index(op.f("ix_teachings_character_id"), "teachings", ["character_id"], unique=False)
    op.create_index(op.f("ix_teachings_teacher_id"), "teachings", ["teacher_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_teachings_teacher_id"), table_name="teachings")
    op.drop_index(op.f("ix_teachings_character_id"), table_name="teachings")
    op.drop_table("teachings")
    op.drop_index(op.f("ix_teacher_rules_troupe_id"), table_name="teacher_rules")
    op.drop_table("teacher_rules")
