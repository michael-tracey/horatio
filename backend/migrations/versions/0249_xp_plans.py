"""A character's plan of XP purchases to come, its player's own (issue #1052).

Revision ID: 0249
Revises: 0247
Create Date: 2026-11-20 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0249"
down_revision: str | None = "0247"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "xp_plans",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column(
            "lines",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("shared", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_xp_plans_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_xp_plans")),
        sa.UniqueConstraint("character_id", name=op.f("uq_xp_plans_character_id")),
    )


def downgrade() -> None:
    op.drop_table("xp_plans")
