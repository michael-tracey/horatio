"""A troupe's own default bloodlines (issue #435): for each clan, the bloodline its
setting plays as the clan, or the plain clan, over the book's default for the sect.

Revision ID: 0134
Revises: 0127
Create Date: 2026-11-02 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0134"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("default_bloodlines", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("troupes", "default_bloodlines")
