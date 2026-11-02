"""Game XP charts (issue #438): a troupe's game XP settings (a chart of XP by
earned-XP band and attendance kind, adjustments, the monthly cap and absentee
games), an attendance kind for absentee games, and what each character got for a
game's XP.

Revision ID: 0136
Revises: 0127
Create Date: 2026-11-01 23:00:00.000000
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0136"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def attendance_kind_exists() -> bool:
    columns = sa.inspect(op.get_bind()).get_columns("game_attendances")
    return any(c["name"] == "kind" for c in columns)


def added_by_0135() -> bool:
    from alembic import context
    from alembic.script import ScriptDirectory

    revisions = ScriptDirectory.from_config(context.config).walk_revisions()
    return any(
        r.revision == "0135" and '"game_attendances"' in Path(r.path).read_text() for r in revisions
    )


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
    # The attendance kind is the one #439's migration (0135_free_changes) adds, with the
    # same name, default and constraint; added here only when that hasn't run yet.
    if not attendance_kind_exists():
        op.add_column(
            "game_attendances",
            sa.Column("kind", sa.String(), server_default="attended", nullable=False),
        )
        op.create_check_constraint(
            op.f("ck_game_attendances_kind"),
            "game_attendances",
            "kind in ('attended', 'absentee')",
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
    # When 0135_free_changes is in the chain, the attendance kind is its to drop.
    if not added_by_0135():
        op.drop_constraint(op.f("ck_game_attendances_kind"), "game_attendances", type_="check")
        op.drop_column("game_attendances", "kind")
    op.drop_column("troupes", "game_xp")
