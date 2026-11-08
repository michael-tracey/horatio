"""jyhad card text: the text and flavour line a player writes for their character's
mock VTES card (issue #537)

Revision ID: 0156
Revises: 0155
Create Date: 2026-11-08 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0156"
down_revision: str | None = "0155"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters", sa.Column("card_text", sa.String(), server_default="", nullable=False)
    )
    op.add_column(
        "characters", sa.Column("card_flavour", sa.String(), server_default="", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("characters", "card_flavour")
    op.drop_column("characters", "card_text")
