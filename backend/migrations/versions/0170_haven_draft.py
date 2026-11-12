"""haven draft: the Haven a player names and gives advantages in creation, kept
with the character until a troupe first accepts it, and then put on that troupe's
list of locations (issue #683)

Revision ID: 0170
Revises: 0166
Create Date: 2026-11-12 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0170"
down_revision: str | None = "0166"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("haven_draft", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("characters", "haven_draft")
