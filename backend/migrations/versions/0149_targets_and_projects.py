"""downtime actions aimed at characters, and projects that span several cycles, such
as a Path change (issue #507)

Revision ID: 0149
Revises: 0148
Create Date: 2026-11-07 12:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0149"
down_revision: str | None = "0148"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def record_columns() -> list[sa.Column[Any]]:
    return [
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
    ]


def upgrade() -> None:
    op.add_column(
        "answers", sa.Column("not_against", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("answers", sa.Column("paired_answer_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_answers_paired_answer_id_answers"),
        "answers",
        "answers",
        ["paired_answer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_answers_paired_answer_id"), "answers", ["paired_answer_id"])

    op.create_table(
        "projects",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("monthly_minimum", sa.Integer(), nullable=True),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(), server_default="proposed", nullable=False),
        sa.Column("path", sa.String(), server_default="", nullable=False),
        sa.Column("with_teacher", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("restarts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_by", sa.Uuid(), nullable=False),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sheet_changed_by", sa.Uuid(), nullable=True),
        *record_columns(),
        sa.CheckConstraint(
            "kind in ('path_change', 'research', 'other')", name=op.f("ck_projects_kind")
        ),
        sa.CheckConstraint(
            "status in ('proposed', 'active', 'finished', 'dropped')",
            name=op.f("ck_projects_status"),
        ),
        sa.CheckConstraint("target >= 1", name=op.f("ck_projects_target")),
        sa.CheckConstraint(
            "monthly_minimum is null or monthly_minimum >= 1",
            name=op.f("ck_projects_monthly_minimum"),
        ),
        sa.CheckConstraint("progress >= 0", name=op.f("ck_projects_progress")),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_projects_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_projects_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["started_by"], ["users.id"], name=op.f("fk_projects_started_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"], ["users.id"], name=op.f("fk_projects_confirmed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["sheet_changed_by"], ["users.id"], name=op.f("fk_projects_sheet_changed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_character_id"), "projects", ["character_id"])
    op.create_index(op.f("ix_projects_troupe_id"), "projects", ["troupe_id"])

    op.create_table(
        "project_cycles",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("spent", sa.Integer(), nullable=False),
        sa.Column("started_over", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        *record_columns(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_cycles_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["downtime_cycles.id"],
            name=op.f("fk_project_cycles_cycle_id_downtime_cycles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_cycles")),
        sa.UniqueConstraint("project_id", "cycle_id", name=op.f("uq_project_cycles_project_id")),
    )
    op.create_index(op.f("ix_project_cycles_project_id"), "project_cycles", ["project_id"])
    op.create_index(op.f("ix_project_cycles_cycle_id"), "project_cycles", ["cycle_id"])


def downgrade() -> None:
    op.drop_table("project_cycles")
    op.drop_table("projects")
    op.drop_index(op.f("ix_answers_paired_answer_id"), table_name="answers")
    op.drop_constraint(op.f("fk_answers_paired_answer_id_answers"), "answers", type_="foreignkey")
    op.drop_column("answers", "paired_answer_id")
    op.drop_column("answers", "not_against")
