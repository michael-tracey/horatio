"""equipment: archaic ranged weapons (a bow, a crossbow), which may shoot with Athletics

Revision ID: 0102
Revises: 0101
Create Date: 2026-10-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0102"
down_revision: str | None = "0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The book's Bow is marked when the rules are loaded (python -m horatio.rules).
    for table in ("equipment_items", "equipment_templates"):
        op.add_column(
            table, sa.Column("archaic", sa.Boolean(), server_default="false", nullable=False)
        )


def downgrade() -> None:
    for table in ("equipment_items", "equipment_templates"):
        op.drop_column(table, "archaic")
