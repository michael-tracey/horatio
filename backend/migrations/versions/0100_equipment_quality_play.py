"""equipment qualities: what each does at the table, in a few words, for the Play View

Revision ID: 0100
Revises: 0092
Create Date: 2026-10-27 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0100"
down_revision: str | None = "0092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Filled when the rules are loaded (python -m horatio.rules).
    op.add_column(
        "equipment_qualities",
        sa.Column("play", sa.String(), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("equipment_qualities", "play")
