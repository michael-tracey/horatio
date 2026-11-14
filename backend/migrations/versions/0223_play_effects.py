"""A power's effect that lasts until undone, kept through Reset and paused in a
transformed form (issue #822): one row per effect on a character, from itself or,
later, from another character in its troupe (issue #823).

Revision ID: 0223
Revises: 0222
Create Date: 2026-11-13 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0223"
down_revision: str | None = "0222"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "play_effects",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("source_character_id", sa.Uuid(), nullable=True),
        sa.Column("source_name", sa.String(), server_default="", nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "amounts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("state", sa.String(), server_default="active", nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("ended_event_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_by_id", sa.Uuid(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispute_note", sa.String(), server_default="", nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by_id", sa.Uuid(), nullable=True),
        sa.Column("ended_how", sa.String(), server_default="", nullable=False),
        sa.Column("replaced_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "state in ('offered', 'active', 'declined', 'ended')",
            name=op.f("ck_play_effects_state"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_play_effects_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["source_character_id"],
            ["characters.id"],
            name=op.f("fk_play_effects_source_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["play_events.id"], name=op.f("fk_play_effects_event_id_play_events")
        ),
        sa.ForeignKeyConstraint(
            ["ended_event_id"],
            ["play_events.id"],
            name=op.f("fk_play_effects_ended_event_id_play_events"),
        ),
        sa.ForeignKeyConstraint(
            ["started_by_id"], ["users.id"], name=op.f("fk_play_effects_started_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_id"], ["users.id"], name=op.f("fk_play_effects_ended_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["replaced_id"],
            ["play_effects.id"],
            name=op.f("fk_play_effects_replaced_id_play_effects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_play_effects")),
        sa.UniqueConstraint("client_id", name=op.f("uq_play_effects_client_id")),
    )
    op.create_index(op.f("ix_play_effects_character_id"), "play_effects", ["character_id"])
    op.create_index(
        op.f("ix_play_effects_source_character_id"), "play_effects", ["source_character_id"]
    )
    op.create_index(
        "uq_play_effects_active",
        "play_effects",
        ["character_id", "key"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_play_effects_active", table_name="play_effects")
    op.drop_index(op.f("ix_play_effects_source_character_id"), table_name="play_effects")
    op.drop_index(op.f("ix_play_effects_character_id"), table_name="play_effects")
    op.drop_table("play_effects")
