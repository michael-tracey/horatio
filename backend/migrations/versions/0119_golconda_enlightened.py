"""A troupe's house option that Golconda Seekers hold the innate status Enlightened
(issue #340; MET: VTM Vol. 2, p. 267), off unless the troupe switches it on.

Revision ID: 0119
Revises: 0116
Create Date: 2026-10-31 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0119"
down_revision: str | None = "0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("golconda_enlightened", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "golconda_enlightened")
