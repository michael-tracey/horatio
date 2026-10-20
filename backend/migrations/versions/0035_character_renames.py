"""when a character's player last renamed it

Revision ID: 0035
Revises: 0033
Create Date: 2026-10-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("renamed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("characters", "renamed_at")
