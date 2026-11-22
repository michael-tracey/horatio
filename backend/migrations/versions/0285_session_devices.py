"""Where someone is signed in (#1193): each sign-in session keeps the browser it was
started from (its User-Agent), the address, only while the custodian records them
with sign-in events, and when it was last used, for Account › Sign-in.

Revision ID: 0285
Revises: 0283
Create Date: 2026-11-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0285"
down_revision: str | None = "0283"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("user_agent", sa.String(length=512), nullable=True))
    op.add_column("sessions", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column(
        "sessions", sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sessions", "last_active_at")
    op.drop_column("sessions", "ip_address")
    op.drop_column("sessions", "user_agent")
