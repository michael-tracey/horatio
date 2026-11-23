"""A troupe's own time zone (#1211), from the IANA list: where its games' days and its
NPCs' days fall. None for every troupe there is, which goes on using its lead
storyteller's, then UTC, as before. A request for a troupe keeps the zone of whoever
asked, for the troupe approving it makes.

Revision ID: 0288
Revises: 0287
Create Date: 2026-11-22 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0288"
down_revision: str | None = "0287"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("troupes", sa.Column("time_zone", sa.String(64), nullable=True))
    op.add_column("troupe_requests", sa.Column("time_zone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("troupe_requests", "time_zone")
    op.drop_column("troupes", "time_zone")
