"""A troupe's abbreviation (#1153), as its lead sets it: unique whatever the case. None
for every troupe now, each going by the one made from its name until one is set, which
is never stored, so there is nothing to fill in.

Revision ID: 0273
Revises: 0272
Create Date: 2026-11-21 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0273"
down_revision: str | None = "0272"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("troupes", sa.Column("abbreviation", sa.String(), nullable=True))
    op.create_index(
        "uq_troupes_abbreviation_lower",
        "troupes",
        [sa.literal_column("lower(abbreviation)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_troupes_abbreviation_lower", table_name="troupes")
    op.drop_column("troupes", "abbreviation")
