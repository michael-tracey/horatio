"""A downtime's results can be delivered again as an update (issue #355): each
delivery of a submission on a channel has a revision, 1 for the first, and the
"sent once" rule holds per revision.

Revision ID: 0120
Revises: 0119
Create Date: 2026-10-31 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0120"
down_revision: str | None = "0119"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SENT = sa.text("status = 'sent' and not test_mode")


def upgrade() -> None:
    op.add_column(
        "deliveries", sa.Column("revision", sa.Integer(), server_default="1", nullable=False)
    )
    op.drop_index("uq_deliveries_sent_once", table_name="deliveries", postgresql_where=SENT)
    op.create_index(
        "uq_deliveries_sent_once",
        "deliveries",
        ["submission_id", "channel", "revision"],
        unique=True,
        postgresql_where=SENT,
    )


def downgrade() -> None:
    # Only first deliveries fit the old rule; updates go.
    op.execute("delete from deliveries where revision > 1")
    op.drop_index("uq_deliveries_sent_once", table_name="deliveries", postgresql_where=SENT)
    op.create_index(
        "uq_deliveries_sent_once",
        "deliveries",
        ["submission_id", "channel"],
        unique=True,
        postgresql_where=SENT,
    )
    op.drop_column("deliveries", "revision")
