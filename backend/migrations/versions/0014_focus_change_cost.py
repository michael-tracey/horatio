"""focus change cost

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-14 14:30:53.222299
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint(
        "kind", "xp_entries", "kind in ('award', 'purchase', 'settlement', 'fee')"
    )
    op.add_column("trait_categories", sa.Column("change_cost", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.execute("delete from xp_entries where kind = 'fee'")
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", "kind in ('award', 'purchase', 'settlement')")
    op.drop_column("trait_categories", "change_cost")
