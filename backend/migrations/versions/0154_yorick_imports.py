"""yorick imports: a troupe's import from Yorick, run by the custodian in the app
(issue #518)

Revision ID: 0154
Revises: 0153
Create Date: 2026-11-07 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0154"
down_revision: str | None = "0153"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "yorick_imports",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("page_name", sa.String(), nullable=True),
        sa.Column("page_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("page_by", sa.Uuid(), nullable=True),
        sa.Column(
            "names", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "by_hand", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "decisions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("job", sa.String(), nullable=True),
        sa.Column("job_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_by", sa.Uuid(), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("report_text", sa.Text(), nullable=True),
        sa.Column("report_kind", sa.String(), nullable=True),
        sa.Column("report_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_stale", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("error", sa.String(), nullable=True),
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
        sa.CheckConstraint("job in ('dry_run', 'import')", name=op.f("ck_yorick_imports_job")),
        sa.CheckConstraint(
            "report_kind in ('dry_run', 'import')", name=op.f("ck_yorick_imports_report_kind")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"],
            ["troupes.id"],
            name=op.f("fk_yorick_imports_troupe_id_troupes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"], ["users.id"], name=op.f("fk_yorick_imports_staff_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["page_by"], ["users.id"], name=op.f("fk_yorick_imports_page_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["job_by"], ["users.id"], name=op.f("fk_yorick_imports_job_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_yorick_imports")),
        sa.UniqueConstraint("troupe_id", name=op.f("uq_yorick_imports_troupe_id")),
    )


def downgrade() -> None:
    op.drop_table("yorick_imports")
