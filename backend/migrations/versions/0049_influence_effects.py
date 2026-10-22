"""targeted influence actions: their targets, and the effects they make

Revision ID: 0049
Revises: 0045
Create Date: 2026-10-21 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("influence_entries", sa.Column("target_character_id", sa.Uuid(), nullable=True))
    op.add_column(
        "influence_entries",
        sa.Column("target_name", sa.String(), server_default="", nullable=False),
    )
    op.add_column("influence_entries", sa.Column("target_entry_id", sa.Uuid(), nullable=True))
    op.add_column("influence_entries", sa.Column("target_type", sa.String(), nullable=True))
    op.add_column(
        "influence_entries",
        sa.Column("target_activity", sa.String(), server_default="", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_influence_entries_target_type"),
        "influence_entries",
        "target_type in ('elite', 'underworld')",
    )
    op.create_index(
        op.f("ix_influence_entries_target_character_id"),
        "influence_entries",
        ["target_character_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_influence_entries_target_character_id_characters"),
        "influence_entries",
        "characters",
        ["target_character_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_influence_entries_target_entry_id_influence_entries"),
        "influence_entries",
        "influence_entries",
        ["target_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "influence_effects",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), server_default="", nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=True),
        sa.Column("levels", sa.Integer(), nullable=False),
        sa.Column("defended", sa.Integer(), server_default="0", nullable=False),
        sa.Column("activity", sa.String(), server_default="", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("games", sa.Integer(), server_default="0", nullable=False),
        sa.Column("owed_action_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
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
            "kind in ('attack', 'boost', 'block')", name=op.f("ck_influence_effects_kind")
        ),
        sa.CheckConstraint(
            "type in ('elite', 'underworld')", name=op.f("ck_influence_effects_type")
        ),
        sa.CheckConstraint(
            "levels >= 0 and defended >= 0 and games >= 0",
            name=op.f("ck_influence_effects_counts"),
        ),
        sa.CheckConstraint(
            "ends_at > starts_at", name=op.f("ck_influence_effects_ends_after_start")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_influence_effects_character_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["influence_entries.id"],
            name=op.f("fk_influence_effects_entry_id_influence_entries"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owed_action_id"],
            ["owed_actions.id"],
            name=op.f("fk_influence_effects_owed_action_id_owed_actions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_influence_effects_recorded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_influence_effects_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_influence_effects")),
        sa.UniqueConstraint("entry_id", name=op.f("uq_influence_effects_entry_id")),
    )
    op.create_index(
        op.f("ix_influence_effects_character_id"),
        "influence_effects",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_influence_effects_troupe_id"), "influence_effects", ["troupe_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_influence_effects_troupe_id"), table_name="influence_effects")
    op.drop_index(op.f("ix_influence_effects_character_id"), table_name="influence_effects")
    op.drop_table("influence_effects")
    op.drop_constraint(
        op.f("fk_influence_entries_target_entry_id_influence_entries"),
        "influence_entries",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_influence_entries_target_character_id_characters"),
        "influence_entries",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_influence_entries_target_character_id"), table_name="influence_entries")
    op.drop_constraint(op.f("ck_influence_entries_target_type"), "influence_entries", type_="check")
    op.drop_column("influence_entries", "target_activity")
    op.drop_column("influence_entries", "target_type")
    op.drop_column("influence_entries", "target_entry_id")
    op.drop_column("influence_entries", "target_name")
    op.drop_column("influence_entries", "target_character_id")
