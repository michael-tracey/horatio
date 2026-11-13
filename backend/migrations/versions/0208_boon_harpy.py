"""The Harpy's access to the boon ledger (issue #688): none, receives submissions, or
the full ledger.

Revision ID: 0208
Revises: 0207
Create Date: 2026-11-12 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0208"
down_revision: str | None = "0207"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("boon_harpy", sa.String(), server_default="none", nullable=False),
    )
    op.create_check_constraint(
        "boon_harpy", "troupes", "boon_harpy in ('none', 'submissions', 'full')"
    )


def downgrade() -> None:
    op.drop_constraint("boon_harpy", "troupes", type_="check")
    op.drop_column("troupes", "boon_harpy")
