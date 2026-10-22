"""how far back influence lookups look, and the discovery blocks on log entries

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-21 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("influence_lookback_days", sa.Integer(), server_default="90", nullable=False),
    )
    op.create_table(
        "influence_blocks",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("response_id", sa.Uuid(), nullable=True),
        sa.Column("added_by", sa.Uuid(), nullable=False),
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
            ["added_by"], ["users.id"], name=op.f("fk_influence_blocks_added_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["influence_entries.id"],
            name=op.f("fk_influence_blocks_entry_id_influence_entries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["responses.id"],
            name=op.f("fk_influence_blocks_response_id_responses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_influence_blocks")),
        sa.UniqueConstraint("response_id", name=op.f("uq_influence_blocks_response_id")),
    )
    op.create_index(
        op.f("ix_influence_blocks_entry_id"), "influence_blocks", ["entry_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_influence_blocks_entry_id"), table_name="influence_blocks")
    op.drop_table("influence_blocks")
    op.drop_column("troupes", "influence_lookback_days")
