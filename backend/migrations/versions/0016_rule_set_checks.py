"""rule set checks

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-14 14:49:41.148057
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rule_sets",
        sa.Column(
            "checks", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("rule_sets", "checks")
