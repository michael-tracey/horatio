"""grants

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-14 15:25:54.930191
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "character_traits",
        sa.Column("granted_rating", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "rule_sets",
        sa.Column(
            "grants", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
    )
    op.add_column("trait_categories", sa.Column("usual_max", sa.Integer(), nullable=True))
    op.add_column("trait_categories", sa.Column("max_held", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("trait_categories", "max_held")
    op.drop_column("trait_categories", "usual_max")
    op.drop_column("rule_sets", "grants")
    op.drop_column("character_traits", "granted_rating")
