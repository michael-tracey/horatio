"""responses deliveries random tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14 00:51:11.925257
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "random_tables",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "entries", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
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
            ["troupe_id"], ["troupes.id"], name=op.f("fk_random_tables_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_random_tables")),
        sa.UniqueConstraint("troupe_id", "name", name=op.f("uq_random_tables_troupe_id")),
    )
    op.create_index(
        op.f("ix_random_tables_troupe_id"), "random_tables", ["troupe_id"], unique=False
    )
    op.create_table(
        "deliveries",
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("test_mode", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("sent_by", sa.Uuid(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "external_ids",
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
        sa.CheckConstraint(
            "channel in ('horatio', 'discord', 'email')", name=op.f("ck_deliveries_channel")
        ),
        sa.CheckConstraint(
            "status in ('pending', 'sent', 'failed')", name=op.f("ck_deliveries_status")
        ),
        sa.ForeignKeyConstraint(
            ["sent_by"], ["users.id"], name=op.f("fk_deliveries_sent_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_deliveries_submission_id_submissions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deliveries")),
    )
    op.create_index(
        op.f("ix_deliveries_submission_id"), "deliveries", ["submission_id"], unique=False
    )
    op.create_index(
        "uq_deliveries_sent_once",
        "deliveries",
        ["submission_id", "channel"],
        unique=True,
        postgresql_where=sa.text("status = 'sent' and not test_mode"),
    )
    op.create_table(
        "responses",
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.String(), server_default="", nullable=False),
        sa.Column("status", sa.String(), server_default="unassigned", nullable=False),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_any_narrator", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column("written_by", sa.Uuid(), nullable=True),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=True),
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
            "status in ('unassigned', 'assigned', 'written')", name=op.f("ck_responses_status")
        ),
        sa.CheckConstraint(
            "not (assigned_to_any_narrator and assigned_to_user_id is not null)",
            name=op.f("ck_responses_one_assignee"),
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"], ["answers.id"], name=op.f("fk_responses_answer_id_answers")
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"], ["users.id"], name=op.f("fk_responses_assigned_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_user_id"],
            ["users.id"],
            name=op.f("fk_responses_assigned_to_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["written_by"], ["users.id"], name=op.f("fk_responses_written_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_responses")),
        sa.UniqueConstraint("answer_id", name=op.f("uq_responses_answer_id")),
    )
    op.create_index(
        op.f("ix_responses_assigned_to_user_id"), "responses", ["assigned_to_user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_responses_assigned_to_user_id"), table_name="responses")
    op.drop_table("responses")
    op.drop_index(
        "uq_deliveries_sent_once",
        table_name="deliveries",
        postgresql_where=sa.text("status = 'sent' and not test_mode"),
    )
    op.drop_index(op.f("ix_deliveries_submission_id"), table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_index(op.f("ix_random_tables_troupe_id"), table_name="random_tables")
    op.drop_table("random_tables")
