"""claim links for sheeted NPCs: whoever opens one and claims is given the NPC as
their own character (issue #481)

Revision ID: 0147
Revises: 0144
Create Date: 2026-11-06 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0147"
down_revision: str | None = "0144"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "npc_claims",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("carried_xp", sa.Integer(), server_default="0", nullable=False),
        sa.Column("carried_reason", sa.String(), server_default="", nullable=False),
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
        sa.CheckConstraint("carried_xp >= 0", name=op.f("ck_npc_claims_carried_xp")),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_npc_claims_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_npc_claims_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_npc_claims")),
        sa.UniqueConstraint("character_id", name=op.f("uq_npc_claims_character_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_npc_claims_token_hash")),
    )


def downgrade() -> None:
    op.drop_table("npc_claims")
