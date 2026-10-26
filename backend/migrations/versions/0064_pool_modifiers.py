"""pool modifiers: a player's own bonuses and penalties to a character's test pools

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-25 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pool_modifiers",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("pools", sa.String(), nullable=False),
        sa.Column("when", sa.String(), server_default="", nullable=False),
        sa.Column("on", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("amount <> 0", name=op.f("ck_pool_modifiers_amount_not_zero")),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_pool_modifiers_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_pool_modifiers_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pool_modifiers")),
    )
    op.create_index(
        op.f("ix_pool_modifiers_character_id"), "pool_modifiers", ["character_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pool_modifiers_character_id"), table_name="pool_modifiers")
    op.drop_table("pool_modifiers")
