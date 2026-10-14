"""category points limit

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-14 14:39:29.205879
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trait_categories", sa.Column("points_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("trait_categories", "points_limit")
