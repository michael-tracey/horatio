"""A backstory's draft (issue #426): its writer's text, saved as they type, until
they submit it as the next version; and the version it was started from.

Revision ID: 0127
Revises: 0126
Create Date: 2026-11-01 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0127"
down_revision: str | None = "0126"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("backstories", sa.Column("draft_text", sa.Text(), nullable=True))
    op.add_column("backstories", sa.Column("draft_version", sa.Integer(), nullable=True))
    op.add_column("backstories", sa.Column("draft_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("backstories", "draft_at")
    op.drop_column("backstories", "draft_version")
    op.drop_column("backstories", "draft_text")
