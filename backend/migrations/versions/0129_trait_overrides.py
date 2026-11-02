"""A troupe's own changes to book traits (issue #431): one row per troupe and trait,
starting with a ban and the reason its players see.

Revision ID: 0129
Revises: 0127
Create Date: 2026-11-01 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0129"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trait_overrides",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=False),
        sa.Column("banned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ban_reason", sa.String(), server_default="", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_trait_overrides_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_trait_overrides_trait_definition_id_trait_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trait_overrides")),
        sa.UniqueConstraint(
            "troupe_id", "trait_definition_id", name=op.f("uq_trait_overrides_troupe_id")
        ),
    )
    op.create_index(
        op.f("ix_trait_overrides_troupe_id"), "trait_overrides", ["troupe_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trait_overrides_troupe_id"), table_name="trait_overrides")
    op.drop_table("trait_overrides")
