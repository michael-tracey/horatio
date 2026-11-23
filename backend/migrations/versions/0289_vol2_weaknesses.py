"""Which weakness a troupe plays for a clan whose default is the core book's (#1197):
the clans it plays by Volume 2's reading instead. Only the Brujah have one, Lash Out's
(Vol. 2, p. 121). Empty for every troupe, so each keeps the core book's Brujah
weakness, as Horatio showed before.

Revision ID: 0289
Revises: 0290
Create Date: 2026-11-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0289"
down_revision: str | None = "0290"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column(
            "vol2_weaknesses",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("troupes", "vol2_weaknesses")
