"""A troupe's written house rules (issue #434): rules in words alone, which its
players read, by section; and whether its profile shows them.

Revision ID: 0133
Revises: 0127
Create Date: 2026-11-02 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0133"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "written_rules",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("section", sa.String(), server_default="", nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=True),
        sa.Column("page", sa.String(), nullable=True),
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
            ["troupe_id"], ["troupes.id"], name=op.f("fk_written_rules_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_written_rules_trait_definition_id_trait_definitions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_written_rules")),
    )
    op.create_index(op.f("ix_written_rules_troupe_id"), "written_rules", ["troupe_id"])
    op.create_index(
        op.f("ix_written_rules_trait_definition_id"), "written_rules", ["trait_definition_id"]
    )
    op.add_column(
        "troupes",
        sa.Column("written_rules_public", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "written_rules_public")
    op.drop_index(op.f("ix_written_rules_trait_definition_id"), table_name="written_rules")
    op.drop_index(op.f("ix_written_rules_troupe_id"), table_name="written_rules")
    op.drop_table("written_rules")
