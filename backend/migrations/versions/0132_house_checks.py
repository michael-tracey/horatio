"""A troupe's own checks (issue #432): a subject, a condition it requires or forbids,
a strength, the message the player sees, and an optional creation step

Revision ID: 0132
Revises: 0127
Create Date: 2026-11-01 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0132"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "house_checks",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("splat", sa.String(), server_default="vampire", nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("name_prefix", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("strength", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("step", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("mode in ('requires', 'forbids')", name=op.f("ck_house_checks_mode")),
        sa.CheckConstraint(
            "strength in ('refuse', 'complete', 'review', 'note')",
            name=op.f("ck_house_checks_strength"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(name, name_prefix, kind) <= 1", name=op.f("ck_house_checks_subject")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_house_checks_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_house_checks")),
    )
    op.create_index(op.f("ix_house_checks_troupe_id"), "house_checks", ["troupe_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_house_checks_troupe_id"), table_name="house_checks")
    op.drop_table("house_checks")
