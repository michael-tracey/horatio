"""A power used on another character (issue #823): the tap that used it keeps whom
it was used on and what it did there, so Undo takes it back and the log reads it.

Revision ID: 0224
Revises: 0223
Create Date: 2026-11-14 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0224"
down_revision: str | None = "0223"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "play_events",
        sa.Column("on_other", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("play_events", "on_other")
