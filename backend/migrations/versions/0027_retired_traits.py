"""retired traits

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-14 23:10:07.316143
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trait_definitions",
        sa.Column("retired", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("trait_definitions", "retired")
