"""Game-night check-in (issue #421): who came to each scheduled game, the door's
short code while check-in is open, the game's XP once awarded, and the Willpower a
Play View game starts with when the character had no full day's rest.

Revision ID: 0126
Revises: 0125
Create Date: 2026-11-01 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0126"
down_revision: str | None = "0125"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scheduled_games", sa.Column("checkin_code", sa.String(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_scheduled_games_checkin_code"), "scheduled_games", ["checkin_code"]
    )
    op.add_column("scheduled_games", sa.Column("xp_awarded", sa.Integer(), nullable=True))
    op.add_column(
        "scheduled_games",
        sa.Column("xp_awarded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("scheduled_games", sa.Column("xp_awarded_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_scheduled_games_xp_awarded_by_users"),
        "scheduled_games",
        "users",
        ["xp_awarded_by"],
        ["id"],
    )
    op.add_column("play_games", sa.Column("willpower_start", sa.Integer(), nullable=True))

    op.create_table(
        "game_attendances",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("checked_in_by", sa.Uuid(), nullable=False),
        sa.Column("by_staff", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("play_game_id", sa.Uuid(), nullable=True),
        sa.Column("rested", sa.Boolean(), nullable=True),
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
            name=op.f("fk_game_attendances_game_id_scheduled_games"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_game_attendances_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["checked_in_by"], ["users.id"], name=op.f("fk_game_attendances_checked_in_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["play_game_id"],
            ["play_games.id"],
            name=op.f("fk_game_attendances_play_game_id_play_games"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_attendances")),
        sa.UniqueConstraint("game_id", "character_id", name=op.f("uq_game_attendances_game_id")),
    )
    op.create_index(op.f("ix_game_attendances_character_id"), "game_attendances", ["character_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_game_attendances_character_id"), table_name="game_attendances")
    op.drop_table("game_attendances")
    op.drop_column("play_games", "willpower_start")
    op.drop_constraint(
        op.f("fk_scheduled_games_xp_awarded_by_users"), "scheduled_games", type_="foreignkey"
    )
    op.drop_column("scheduled_games", "xp_awarded_by")
    op.drop_column("scheduled_games", "xp_awarded_at")
    op.drop_column("scheduled_games", "xp_awarded")
    op.drop_constraint(op.f("uq_scheduled_games_checkin_code"), "scheduled_games", type_="unique")
    op.drop_column("scheduled_games", "checkin_code")
