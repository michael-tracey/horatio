"""title one holder: the book's titles a troupe holds to one holder at a time, as a
house rule (issue #551). Off for every troupe's book titles to begin with; its own
titles keep their `unique`

Revision ID: 0157
Revises: 0156
Create Date: 2026-11-08 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0157"
down_revision: str | None = "0156"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("one_holder_titles", JSONB(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "one_holder_titles")
