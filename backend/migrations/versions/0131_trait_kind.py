"""A troupe's category for a merit or flaw (issue #436): its catalogue type in the
troupe, such as General for a sect flaw; null keeps the book's.

Revision ID: 0131
Revises: 0130
Create Date: 2026-11-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0131"
down_revision: str | None = "0130"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trait_overrides", sa.Column("kind", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("trait_overrides", "kind")
