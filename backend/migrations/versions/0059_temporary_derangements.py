"""temporary derangements added on the Play View

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "play_derangements",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), server_default="", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_play_derangements_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_play_derangements_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_play_derangements")),
    )
    op.create_index(
        op.f("ix_play_derangements_character_id"),
        "play_derangements",
        ["character_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_play_derangements_character_id"), table_name="play_derangements")
    op.drop_table("play_derangements")
