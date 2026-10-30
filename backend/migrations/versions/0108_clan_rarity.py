"""clan rarity: each troupe can name how rare a clan is in its setting, which a
character's rarity merit follows while it is built (horatio.clan_merits)

Revision ID: 0108
Revises: 0106
Create Date: 2026-10-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0108"
down_revision: str | None = "0106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("clan_rarity", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("troupes", "clan_rarity")
