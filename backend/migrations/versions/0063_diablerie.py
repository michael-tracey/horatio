"""diablerie: an approval kind, the record of one, Beast traits for the next game, and a troupe setting

Revision ID: 0063
Revises: 0060
Create Date: 2026-10-25 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0063"
down_revision: str | None = "0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'sheet_change', 'home_troupe_change', 'discipline', 'review', 'exception'"


def upgrade() -> None:
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint("kind", "approvals", f"kind in ({KINDS}, 'diablerie')")
    op.create_table(
        "diableries",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("committed_on", sa.Date(), nullable=False),
        sa.Column("victim", sa.String(), server_default="", nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "outcome",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
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
            ["approval_id"], ["approvals.id"], name=op.f("fk_diableries_approval_id_approvals")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"], ["characters.id"], name=op.f("fk_diableries_character_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_diableries_recorded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_diableries_requested_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_diableries_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diableries")),
        sa.UniqueConstraint("approval_id", name=op.f("uq_diableries_approval_id")),
    )
    op.create_index(op.f("ix_diableries_character_id"), "diableries", ["character_id"])
    op.add_column(
        "characters", sa.Column("beast_next_game", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "play_games", sa.Column("beast_start", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "troupes",
        sa.Column("diablerie_flaws", sa.String(), server_default="leave", nullable=False),
    )
    op.create_check_constraint(
        "diablerie_flaws", "troupes", "diablerie_flaws in ('leave', 'remove', 'keep_xp')"
    )


def downgrade() -> None:
    op.drop_constraint("diablerie_flaws", "troupes", type_="check")
    op.drop_column("troupes", "diablerie_flaws")
    op.drop_column("play_games", "beast_start")
    op.drop_column("characters", "beast_next_game")
    op.drop_index(op.f("ix_diableries_character_id"), table_name="diableries")
    op.drop_table("diableries")
    op.execute("delete from approvals where kind = 'diablerie'")
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint("kind", "approvals", f"kind in ({KINDS})")
