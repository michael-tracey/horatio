"""derived categories

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-14 17:31:43.857742
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trait_categories",
        sa.Column("derived", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("trait_categories", "derived")
