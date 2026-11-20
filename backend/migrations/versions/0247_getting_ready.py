"""Getting your troupe ready (issue #1049): whether a troupe's storytellers hid the
card from its Overview. Troupes that have already opened a downtime cycle are well
under way, so they start with it hidden; their storytellers can bring it back from
Customise › Setup.

Revision ID: 0247
Revises: 0241
Create Date: 2026-11-20 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0247"
down_revision: str | None = "0241"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("getting_ready_hidden", sa.Boolean(), server_default="false", nullable=False),
    )
    op.execute(
        "update troupes set getting_ready_hidden = true"
        " where exists (select 1 from downtime_cycles c where c.troupe_id = troupes.id)"
    )


def downgrade() -> None:
    op.drop_column("troupes", "getting_ready_hidden")
