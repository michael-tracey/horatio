"""A delivery can be cancelled (#1134): one waiting to go to a character's own Discord
channel when its player turns that channel off.

Revision ID: 0265
Revises: 0259
Create Date: 2026-11-21 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0265"
down_revision: str | None = "0259"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_deliveries_status"), "deliveries", type_="check")
    op.create_check_constraint(
        op.f("ck_deliveries_status"),
        "deliveries",
        "status in ('pending', 'sent', 'failed', 'cancelled')",
    )


def downgrade() -> None:
    # A cancelled delivery was never sent: it reads as given up on.
    op.execute("update deliveries set status = 'failed' where status = 'cancelled'")
    op.drop_constraint(op.f("ck_deliveries_status"), "deliveries", type_="check")
    op.create_check_constraint(
        op.f("ck_deliveries_status"), "deliveries", "status in ('pending', 'sent', 'failed')"
    )
