"""The Tremere weakness the troupe played on each drink of a blood bond (#1145):
Volume 2's cap at one drink for a Tremere regnant's vampire thrall, or the core
book's first drink counting as two for a Tremere thrall. Empty for every drink
recorded before, so no bond already standing changes.

Revision ID: 0272
Revises: 0270
Create Date: 2026-11-21 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0272"
down_revision: str | None = "0270"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bond_entries",
        sa.Column("weakness", sa.String(), server_default="", nullable=False),
    )
    op.create_check_constraint("weakness", "bond_entries", "weakness in ('', 'capped', 'doubled')")
    op.create_check_constraint("weakness_drink", "bond_entries", "kind = 'drink' or weakness = ''")


def downgrade() -> None:
    op.drop_constraint("weakness_drink", "bond_entries", type_="check")
    op.drop_constraint("weakness", "bond_entries", type_="check")
    op.drop_column("bond_entries", "weakness")
