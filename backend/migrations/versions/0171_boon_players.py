"""What players see of a troupe's boon ledger in the Play View's Boons tab, and
whether a boon's creditor's player may mark it settled (issue #686).

Revision ID: 0171
Revises: 0168
Create Date: 2026-11-12 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0171"
down_revision: str | None = "0168"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("boon_players_see", sa.String(), server_default="intake", nullable=False),
    )
    op.create_check_constraint(
        "boon_players_see", "troupes", "boon_players_see in ('intake', 'owes', 'owed')"
    )
    op.add_column(
        "troupes",
        sa.Column("boon_players_settle", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "boon_players_settle")
    op.drop_constraint("boon_players_see", "troupes", type_="check")
    op.drop_column("troupes", "boon_players_see")
