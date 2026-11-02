"""Game XP charts (issue #438): a troupe's game XP settings (a chart of XP by
earned-XP band and attendance kind, adjustments, the monthly cap and absentee
games), and what each character got for a game's XP. The attendance kind for
absentee games is 0135_free_changes' column.

Revision ID: 0136
Revises: 0135
Create Date: 2026-11-01 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0136"
down_revision: str | None = "0135"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column(
            "game_xp",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.create_table(
        "game_xp_awards",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("band", sa.String(), nullable=True),
        sa.Column("figure", sa.Integer(), nullable=False),
        sa.Column(
            "adjustments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("capped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("override", sa.Integer(), nullable=True),
        sa.Column("override_reason", sa.String(), server_default="", nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("xp_entry_id", sa.Uuid(), nullable=True),
        sa.Column("awarded_by", sa.Uuid(), nullable=False),
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
            ["game_id"],
            ["scheduled_games.id"],
            name=op.f("fk_game_xp_awards_game_id_scheduled_games"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_game_xp_awards_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["xp_entry_id"],
            ["xp_entries.id"],
            name=op.f("fk_game_xp_awards_xp_entry_id_xp_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["awarded_by"], ["users.id"], name=op.f("fk_game_xp_awards_awarded_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_xp_awards")),
        sa.UniqueConstraint("game_id", "character_id", name=op.f("uq_game_xp_awards_game_id")),
    )
    op.create_index(op.f("ix_game_xp_awards_character_id"), "game_xp_awards", ["character_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_game_xp_awards_character_id"), table_name="game_xp_awards")
    op.drop_table("game_xp_awards")
    op.drop_column("troupes", "game_xp")
