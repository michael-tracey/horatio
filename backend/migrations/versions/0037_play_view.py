"""the play view: games, their taps, custom counters and the starting blood house rule

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-20 02:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def record_columns() -> list[sa.Column[Any]]:
    """The id and timestamps every table has (horatio.models.base.Record)."""
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
    op.add_column("troupes", sa.Column("starting_blood", sa.Integer(), nullable=True))

    op.create_table(
        "play_games",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        *record_columns(),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_play_games_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_id"], ["users.id"], name=op.f("fk_play_games_ended_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_play_games")),
        sa.UniqueConstraint("character_id", "number", name=op.f("uq_play_games_character_id")),
    )
    op.create_index(
        op.f("ix_play_games_character_id"), "play_games", ["character_id"], unique=False
    )
    op.create_index(
        "uq_play_games_open",
        "play_games",
        ["character_id"],
        unique=True,
        postgresql_where=sa.text("ended_at is null"),
    )

    op.create_table(
        "play_counters",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("uses", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by_id", sa.Uuid(), nullable=True),
        *record_columns(),
        sa.CheckConstraint("uses > 0", name=op.f("ck_play_counters_uses_positive")),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_play_counters_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_play_counters_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["removed_by_id"], ["users.id"], name=op.f("fk_play_counters_removed_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_play_counters")),
    )
    op.create_index(
        op.f("ix_play_counters_character_id"), "play_counters", ["character_id"], unique=False
    )

    op.create_table(
        "play_events",
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("happened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tracker", sa.String(), server_default="", nullable=False),
        sa.Column("amount", sa.Integer(), server_default="0", nullable=False),
        sa.Column("damage", sa.String(), nullable=True),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("undoes_id", sa.Uuid(), nullable=True),
        sa.Column("before", sa.Integer(), nullable=True),
        sa.Column("after", sa.Integer(), nullable=True),
        *record_columns(),
        sa.CheckConstraint("kind in ('change', 'note', 'undo')", name=op.f("ck_play_events_kind")),
        sa.CheckConstraint(
            "damage is null or damage in ('normal', 'aggravated')",
            name=op.f("ck_play_events_damage"),
        ),
        sa.CheckConstraint(
            "kind <> 'undo' or undoes_id is not null", name=op.f("ck_play_events_undo_names_a_tap")
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["play_games.id"], name=op.f("fk_play_events_game_id_play_games")
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_play_events_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["undoes_id"], ["play_events.id"], name=op.f("fk_play_events_undoes_id_play_events")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_play_events")),
        sa.UniqueConstraint("client_id", name=op.f("uq_play_events_client_id")),
    )
    op.create_index(op.f("ix_play_events_game_id"), "play_events", ["game_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_play_events_game_id"), table_name="play_events")
    op.drop_table("play_events")
    op.drop_index(op.f("ix_play_counters_character_id"), table_name="play_counters")
    op.drop_table("play_counters")
    op.drop_index("uq_play_games_open", table_name="play_games")
    op.drop_index(op.f("ix_play_games_character_id"), table_name="play_games")
    op.drop_table("play_games")
    op.drop_column("troupes", "starting_blood")
