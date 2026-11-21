"""Which weakness a troupe plays for a clan whose weakness a later book replaced
(#1127): the clans it plays by the core book's. Empty for every troupe, so each keeps
Volume 2's Tremere weakness, as before.

Revision ID: 0263
Revises: 0259
Create Date: 2026-11-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0263"
down_revision: str | None = "0259"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column(
            "core_weaknesses",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("troupes", "core_weaknesses")
