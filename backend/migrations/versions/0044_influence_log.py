"""the troupe's influence log, and the answers logged in it

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-21 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "influence_entries",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("happened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("specialization", sa.String(), server_default="", nullable=False),
        sa.Column("action_key", sa.String(), nullable=True),
        sa.Column("purpose", sa.String(), server_default="", nullable=False),
        sa.Column("times", sa.Integer(), server_default="1", nullable=False),
        sa.Column("blocks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=True),
        sa.Column("play_event_id", sa.Uuid(), nullable=True),
        sa.Column("reference", sa.String(), nullable=True),
        sa.Column("needs_details", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("logged_by", sa.Uuid(), nullable=True),
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
            "type in ('elite', 'underworld')", name=op.f("ck_influence_entries_type")
        ),
        sa.CheckConstraint(
            "source in ('downtime', 'game', 'hand', 'import')",
            name=op.f("ck_influence_entries_source"),
        ),
        sa.CheckConstraint("times >= 1", name=op.f("ck_influence_entries_times")),
        sa.CheckConstraint("blocks >= 0", name=op.f("ck_influence_entries_blocks")),
        sa.CheckConstraint("number >= 1", name=op.f("ck_influence_entries_number")),
        sa.CheckConstraint(
            "action_key is not null or needs_details",
            name=op.f("ck_influence_entries_action_or_details"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_influence_entries_character_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["downtime_cycles.id"],
            name=op.f("fk_influence_entries_cycle_id_downtime_cycles"),
        ),
        sa.ForeignKeyConstraint(
            ["logged_by"], ["users.id"], name=op.f("fk_influence_entries_logged_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["play_event_id"],
            ["play_events.id"],
            name=op.f("fk_influence_entries_play_event_id_play_events"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_influence_entries_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_influence_entries")),
        sa.UniqueConstraint("troupe_id", "type", "number", name="uq_influence_entries_number"),
        sa.UniqueConstraint("troupe_id", "reference", name="uq_influence_entries_reference"),
    )
    op.create_index(
        op.f("ix_influence_entries_character_id"),
        "influence_entries",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_influence_entries_cycle_id"), "influence_entries", ["cycle_id"], unique=False
    )
    op.create_index(
        op.f("ix_influence_entries_play_event_id"),
        "influence_entries",
        ["play_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_influence_entries_troupe_happened",
        "influence_entries",
        ["troupe_id", "happened_at"],
        unique=False,
    )
    op.add_column("responses", sa.Column("influence_entry_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_responses_influence_entry_id"),
        "responses",
        ["influence_entry_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_responses_influence_entry_id_influence_entries"),
        "responses",
        "influence_entries",
        ["influence_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_responses_influence_entry_id_influence_entries"), "responses", type_="foreignkey"
    )
    op.drop_index(op.f("ix_responses_influence_entry_id"), table_name="responses")
    op.drop_column("responses", "influence_entry_id")
    op.drop_index("ix_influence_entries_troupe_happened", table_name="influence_entries")
    op.drop_index(op.f("ix_influence_entries_play_event_id"), table_name="influence_entries")
    op.drop_index(op.f("ix_influence_entries_cycle_id"), table_name="influence_entries")
    op.drop_index(op.f("ix_influence_entries_character_id"), table_name="influence_entries")
    op.drop_table("influence_entries")
