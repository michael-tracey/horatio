"""status at a game: each Play View game keeps the character's status choices and the
titles it held as the game began; a tap spending a fleeting status keeps its record, so
Undo gives it back; and staff can suppress a character's fleeting status for a while

Revision ID: 0083
Revises: 0082
Create Date: 2026-10-27 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0083"
down_revision: str | None = "0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "play_games",
        sa.Column(
            "status",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "play_events",
        sa.Column("held_status", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "status_suppressions",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("given_on", sa.Date(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=True),
        sa.Column("added_by", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "kind in ('game', 'commander')", name=op.f("ck_status_suppressions_kind")
        ),
        sa.ForeignKeyConstraint(
            ["added_by"], ["users.id"], name=op.f("fk_status_suppressions_added_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_status_suppressions_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["play_games.id"],
            name=op.f("fk_status_suppressions_game_id_play_games"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_status_suppressions")),
    )
    op.create_index(
        op.f("ix_status_suppressions_character_id"), "status_suppressions", ["character_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_status_suppressions_character_id"), table_name="status_suppressions")
    op.drop_table("status_suppressions")
    op.drop_column("play_events", "held_status")
    op.drop_column("play_games", "status")
