"""Boons judge the ban (issue #692): whether a troupe that keeps a boon ledger judges
the Camarilla's lesser status ban on no boons registered with the Harpy (MET: VTM
p. 403) from it. Off by default, so switching boons on doesn't put the whole court
under the ban before the ledger holds every boon.

Revision ID: 0219
Revises: 0218
Create Date: 2026-11-12 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0219"
down_revision: str | None = "0218"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("boons_judge_ban", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("troupes", "boons_judge_ban")
