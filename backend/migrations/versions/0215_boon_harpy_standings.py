"""Whether the Harpy with the full boon ledger also reads its standings and statistics
(issue #749).

Revision ID: 0215
Revises: 0208
Create Date: 2026-11-13 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0215"
down_revision: str | None = "0208"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("boon_harpy_standings", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "boon_harpy_standings")
