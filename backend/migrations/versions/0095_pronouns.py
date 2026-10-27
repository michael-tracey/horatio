"""pronouns: a character's and a player's, and whether a troupe's badges print the
character's

Revision ID: 0095
Revises: 0094
Create Date: 2026-10-27 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0095"
down_revision: str | None = "0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("pronouns", sa.String(), nullable=True))
    op.add_column("users", sa.Column("pronouns", sa.String(), nullable=True))
    op.add_column(
        "troupes",
        sa.Column("badge_pronouns", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "badge_pronouns")
    op.drop_column("users", "pronouns")
    op.drop_column("characters", "pronouns")
