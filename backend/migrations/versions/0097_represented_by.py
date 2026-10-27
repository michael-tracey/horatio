"""represented by: which clans have a seat at a troupe's court, and who speaks for a
character of a clan without one

Revision ID: 0097
Revises: 0087
Create Date: 2026-10-27 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0097"
down_revision: str | None = "0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Null until staff choose: the clans whose Primogen is held there have a seat.
    op.add_column("troupes", sa.Column("seated_clans", JSONB(), nullable=True))
    op.add_column("troupe_memberships", sa.Column("represented_by", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("troupe_memberships", "represented_by")
    op.drop_column("troupes", "seated_clans")
