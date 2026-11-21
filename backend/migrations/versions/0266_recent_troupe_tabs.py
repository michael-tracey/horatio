"""The tabs of a troupe's page each person opened last there (#1048), kept on their
account for the top of the phone's tab list.

Revision ID: 0266
Revises: 0259
Create Date: 2026-11-21 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0266"
down_revision: str | None = "0259"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recent_troupe_tabs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column(
            "tabs", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recent_troupe_tabs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"],
            ["troupes.id"],
            name=op.f("fk_recent_troupe_tabs_troupe_id_troupes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recent_troupe_tabs")),
        sa.UniqueConstraint("user_id", "troupe_id", name="uq_recent_troupe_tabs_one"),
    )
    op.create_index(op.f("ix_recent_troupe_tabs_troupe_id"), "recent_troupe_tabs", ["troupe_id"])


def downgrade() -> None:
    op.drop_table("recent_troupe_tabs")
