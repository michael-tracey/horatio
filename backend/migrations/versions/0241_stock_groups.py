"""A group of Stock NPCs as one (issue #1056): how many members a Stock NPC stands
for, 1 for every one so far, and which member carries each of its items (by the
item's id), the rest carried by the group as a whole.

Revision ID: 0241
Revises: 0239
Create Date: 2026-11-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0241"
down_revision: str | None = "0239"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stock_npcs", sa.Column("count", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_check_constraint(op.f("ck_stock_npcs_count"), "stock_npcs", "count >= 1")
    op.add_column(
        "stock_npcs",
        sa.Column(
            "item_members",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("stock_npcs", "item_members")
    op.drop_constraint(op.f("ck_stock_npcs_count"), "stock_npcs", type_="check")
    op.drop_column("stock_npcs", "count")
