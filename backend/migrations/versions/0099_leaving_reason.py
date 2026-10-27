"""why a character left: a reason at retirement, and whether the Who's Who lists it

Revision ID: 0099
Revises: 0087
Create Date: 2026-10-27 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0099"
down_revision: str | None = "0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Characters retired before this have no reason, and are not listed.
    op.add_column("characters", sa.Column("left_reason", sa.String(), nullable=True))
    op.create_check_constraint(
        "left_reason", "characters", "left_reason in ('final_death', 'off_field', 'inactive')"
    )
    op.add_column(
        "characters",
        sa.Column("left_listed", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("characters", "left_listed")
    op.drop_constraint("left_reason", "characters", type_="check")
    op.drop_column("characters", "left_reason")
