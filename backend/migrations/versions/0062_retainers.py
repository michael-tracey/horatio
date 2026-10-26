"""retainers: a character's Retainers, each with its dots and perhaps an NPC

Revision ID: 0062
Revises: 0060
Create Date: 2026-10-25 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retainers",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("dots", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), server_default="", nullable=False),
        sa.Column("from_merit", sa.String(), server_default="", nullable=False),
        sa.Column("lost", sa.String(), nullable=True),
        sa.Column("lost_on", sa.Date(), nullable=True),
        sa.Column("npc_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("dots >= 1", name=op.f("ck_retainers_dots")),
        sa.CheckConstraint(
            "lost is null or lost in ('released', 'killed')", name=op.f("ck_retainers_lost")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_retainers_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["npc_id"],
            ["characters.id"],
            name=op.f("fk_retainers_npc_id_characters"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retainers")),
    )
    op.create_index(op.f("ix_retainers_character_id"), "retainers", ["character_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_retainers_character_id"), table_name="retainers")
    op.drop_table("retainers")
