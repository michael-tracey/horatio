"""buy off factor

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-14 17:42:20.591096
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trait_categories", sa.Column("buy_off_factor", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("trait_categories", "buy_off_factor")
