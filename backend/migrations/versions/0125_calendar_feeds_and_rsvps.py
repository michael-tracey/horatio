"""Calendar links and RSVPs (issue #420): whether each person means to come to a
troupe's scheduled games, and their secret links to a calendar of a troupe's games
and downtime dates, or of every troupe they are in.

Revision ID: 0125
Revises: 0124
Create Date: 2026-11-01 15:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0125"
down_revision: str | None = "0124"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def record_columns() -> list[sa.Column[Any]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "game_rsvps",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("answer", sa.String(), nullable=False),
        *record_columns(),
        sa.CheckConstraint(
            "answer in ('coming', 'maybe', 'not_coming')", name=op.f("ck_game_rsvps_answer")
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["scheduled_games.id"],
            name=op.f("fk_game_rsvps_game_id_scheduled_games"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_game_rsvps_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_rsvps")),
        sa.UniqueConstraint("game_id", "user_id", name=op.f("uq_game_rsvps_game_id")),
    )
    op.create_index(op.f("ix_game_rsvps_user_id"), "game_rsvps", ["user_id"])

    op.create_table(
        "calendar_feeds",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("token", sa.String(), nullable=False),
        *record_columns(),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_calendar_feeds_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_calendar_feeds_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_feeds")),
        sa.UniqueConstraint("token", name=op.f("uq_calendar_feeds_token")),
        # One link per person per troupe, and one of all their troupes (no troupe).
        sa.UniqueConstraint(
            "user_id",
            "troupe_id",
            name=op.f("uq_calendar_feeds_user_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("calendar_feeds")
    op.drop_index(op.f("ix_game_rsvps_user_id"), table_name="game_rsvps")
    op.drop_table("game_rsvps")
