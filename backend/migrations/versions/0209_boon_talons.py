"""Lesser Harpies, or talons (issue #689): whether the Harpy may give others access to
the boon ledger, what the troupe calls them, and who has what access.

Revision ID: 0209
Revises: 0208
Create Date: 2026-11-13 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0209"
down_revision: str | None = "0208"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("boon_talons", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "troupes",
        sa.Column("boon_talon_word", sa.String(), server_default="Lesser Harpies", nullable=False),
    )
    op.create_check_constraint(
        "boon_talon_word", "troupes", "boon_talon_word in ('Lesser Harpies', 'Talons')"
    )
    op.create_table(
        "boon_talons",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("can_add", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("can_edit", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("can_audit", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("given_by_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_boon_talons_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_boon_talons_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["given_by_id"],
            ["characters.id"],
            name=op.f("fk_boon_talons_given_by_id_characters"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boon_talons")),
        sa.UniqueConstraint("troupe_id", "character_id", name=op.f("uq_boon_talons_troupe_id")),
    )
    op.create_index(op.f("ix_boon_talons_troupe_id"), "boon_talons", ["troupe_id"])
    op.create_index(op.f("ix_boon_talons_character_id"), "boon_talons", ["character_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_boon_talons_character_id"), table_name="boon_talons")
    op.drop_index(op.f("ix_boon_talons_troupe_id"), table_name="boon_talons")
    op.drop_table("boon_talons")
    op.drop_constraint("boon_talon_word", "troupes", type_="check")
    op.drop_column("troupes", "boon_talon_word")
    op.drop_column("troupes", "boon_talons")
