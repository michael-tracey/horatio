"""downtimes

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14 00:44:51.929075
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_kinds",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "fields", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
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
            ["rule_set_id"], ["rule_sets.id"], name=op.f("fk_action_kinds_rule_set_id_rule_sets")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_action_kinds_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_kinds")),
        sa.UniqueConstraint(
            "rule_set_id",
            "troupe_id",
            "key",
            name=op.f("uq_action_kinds_rule_set_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_action_kinds_rule_set_id"), "action_kinds", ["rule_set_id"], unique=False
    )
    op.create_index(op.f("ix_action_kinds_troupe_id"), "action_kinds", ["troupe_id"], unique=False)
    op.create_table(
        "downtime_cycles",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status in ('draft', 'open', 'closed', 'complete')",
            name=op.f("ck_downtime_cycles_status"),
        ),
        sa.CheckConstraint(
            "grace_ends_at >= closes_at", name=op.f("ck_downtime_cycles_grace_after_close")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_downtime_cycles_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_downtime_cycles")),
    )
    op.create_index(
        op.f("ix_downtime_cycles_troupe_id"), "downtime_cycles", ["troupe_id"], unique=False
    )
    op.create_index(
        "uq_downtime_cycles_one_open",
        "downtime_cycles",
        ["troupe_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "allowance_rules",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("action_kind", sa.String(), nullable=False),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=True),
        sa.Column("min_rating", sa.Integer(), server_default="1", nullable=False),
        sa.Column("scheme", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "scheme in ('fixed', 'per_dot')", name=op.f("ck_allowance_rules_scheme")
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"], ["rule_sets.id"], name=op.f("fk_allowance_rules_rule_set_id_rule_sets")
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_allowance_rules_trait_definition_id_trait_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_allowance_rules_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allowance_rules")),
    )
    op.create_index(
        op.f("ix_allowance_rules_rule_set_id"), "allowance_rules", ["rule_set_id"], unique=False
    )
    op.create_index(
        op.f("ix_allowance_rules_troupe_id"), "allowance_rules", ["troupe_id"], unique=False
    )
    op.create_table(
        "cycle_participants",
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("allowance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowance_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by", sa.Uuid(), nullable=True),
        sa.Column("late_accepted_by", sa.Uuid(), nullable=True),
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
            ["added_by"], ["users.id"], name=op.f("fk_cycle_participants_added_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_cycle_participants_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["downtime_cycles.id"],
            name=op.f("fk_cycle_participants_cycle_id_downtime_cycles"),
        ),
        sa.ForeignKeyConstraint(
            ["late_accepted_by"],
            ["users.id"],
            name=op.f("fk_cycle_participants_late_accepted_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["removed_by"], ["users.id"], name=op.f("fk_cycle_participants_removed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cycle_participants")),
        sa.UniqueConstraint(
            "cycle_id", "character_id", name=op.f("uq_cycle_participants_cycle_id")
        ),
    )
    op.create_index(
        op.f("ix_cycle_participants_character_id"),
        "cycle_participants",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cycle_participants_cycle_id"), "cycle_participants", ["cycle_id"], unique=False
    )
    op.create_table(
        "questions",
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("action_kind", sa.String(), nullable=True),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("help_text", sa.String(), server_default="", nullable=False),
        sa.Column("answer_type", sa.String(), server_default="long_text", nullable=False),
        sa.Column(
            "options", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("max_answers", sa.Integer(), nullable=True),
        sa.Column("visible_to", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.CheckConstraint(
            "(kind = 'action') = (action_kind is not null)",
            name=op.f("ck_questions_action_has_kind"),
        ),
        sa.CheckConstraint(
            "answer_type in ('long_text', 'short_text', 'choice', 'number', 'yes_no')",
            name=op.f("ck_questions_answer_type"),
        ),
        sa.CheckConstraint("kind in ('action', 'custom')", name=op.f("ck_questions_kind")),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["downtime_cycles.id"], name=op.f("fk_questions_cycle_id_downtime_cycles")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    op.create_index(op.f("ix_questions_cycle_id"), "questions", ["cycle_id"], unique=False)
    op.create_table(
        "allowance_adjustments",
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("action_kind", sa.String(), nullable=False),
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
            ["adjusted_by"], ["users.id"], name=op.f("fk_allowance_adjustments_adjusted_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["cycle_participants.id"],
            name=op.f("fk_allowance_adjustments_participant_id_cycle_participants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allowance_adjustments")),
    )
    op.create_index(
        op.f("ix_allowance_adjustments_participant_id"),
        "allowance_adjustments",
        ["participant_id"],
        unique=False,
    )
    op.create_table(
        "submissions",
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("late", sa.Boolean(), server_default="false", nullable=False),
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
        sa.CheckConstraint("status in ('draft', 'submitted')", name=op.f("ck_submissions_status")),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["cycle_participants.id"],
            name=op.f("fk_submissions_participant_id_cycle_participants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
        sa.UniqueConstraint("participant_id", name=op.f("uq_submissions_participant_id")),
    )
    op.create_table(
        "answers",
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.Integer(), server_default="1", nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column(
            "structured",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
            ["question_id"], ["questions.id"], name=op.f("fk_answers_question_id_questions")
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submissions.id"], name=op.f("fk_answers_submission_id_submissions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answers")),
        sa.UniqueConstraint(
            "submission_id", "question_id", "slot", name=op.f("uq_answers_submission_id")
        ),
    )
    op.create_index(op.f("ix_answers_question_id"), "answers", ["question_id"], unique=False)
    op.create_index(op.f("ix_answers_submission_id"), "answers", ["submission_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_answers_submission_id"), table_name="answers")
    op.drop_index(op.f("ix_answers_question_id"), table_name="answers")
    op.drop_table("answers")
    op.drop_table("submissions")
    op.drop_index(
        op.f("ix_allowance_adjustments_participant_id"), table_name="allowance_adjustments"
    )
    op.drop_table("allowance_adjustments")
    op.drop_index(op.f("ix_questions_cycle_id"), table_name="questions")
    op.drop_table("questions")
    op.drop_index(op.f("ix_cycle_participants_cycle_id"), table_name="cycle_participants")
    op.drop_index(op.f("ix_cycle_participants_character_id"), table_name="cycle_participants")
    op.drop_table("cycle_participants")
    op.drop_index(op.f("ix_allowance_rules_troupe_id"), table_name="allowance_rules")
    op.drop_index(op.f("ix_allowance_rules_rule_set_id"), table_name="allowance_rules")
    op.drop_table("allowance_rules")
    op.drop_index(
        "uq_downtime_cycles_one_open",
        table_name="downtime_cycles",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index(op.f("ix_downtime_cycles_troupe_id"), table_name="downtime_cycles")
    op.drop_table("downtime_cycles")
    op.drop_index(op.f("ix_action_kinds_troupe_id"), table_name="action_kinds")
    op.drop_index(op.f("ix_action_kinds_rule_set_id"), table_name="action_kinds")
    op.drop_table("action_kinds")
