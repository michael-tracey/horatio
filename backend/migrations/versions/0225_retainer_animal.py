"""Whether a Retainer is an animal (issue #854): Beast's Vigor moves damage onto an
animal ghoul Retainer only (Vol. 2 Issue 1 pp. 58-59). Set beside `ghoul`; the
Retainers a merit gives as an animal (Ardent Companion's ghouled animal, Vol. 2
Issue 1 p. 39) start as animals.

Revision ID: 0225
Revises: 0224
Create Date: 2026-11-14 06:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0225"
down_revision: str | None = "0224"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The merits whose `retainer` grant gives an animal (bns_met_vampire_grants.toml).
ANIMAL_MERITS = ("Ardent Companion",)


def upgrade() -> None:
    op.add_column(
        "retainers",
        sa.Column("animal", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    retainers = sa.table(
        "retainers", sa.column("from_merit", sa.String()), sa.column("animal", sa.Boolean())
    )
    op.execute(
        retainers.update()
        .where(retainers.c.from_merit.in_(ANIMAL_MERITS))
        .values(animal=sa.true())
    )


def downgrade() -> None:
    op.drop_column("retainers", "animal")
