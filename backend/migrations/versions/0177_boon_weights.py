"""boon weights: what each kind of boon weighs in a troupe's boon standings, set
per troupe, the defaults where it sets none (issue #691)

Revision ID: 0177
Revises: 0172
Create Date: 2026-11-12 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0177"
down_revision: str | None = "0172"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # None set: every troupe weighs boons by the defaults (horatio.boon_standings).
    op.add_column(
        "troupes",
        sa.Column("boon_weights", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("troupes", "boon_weights")
