"""throw images: a troupe's own rock, paper and scissors pictures for the Play
View's Throws tab (issue #670)

Revision ID: 0169
Revises: 0165
Create Date: 2026-11-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0169"
down_revision: str | None = "0165"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # None yet: every troupe throws with Horatio's own.
    op.add_column(
        "troupes",
        sa.Column("throw_images", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("troupes", "throw_images")
