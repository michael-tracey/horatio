"""merits and flaws on the sheet: what makes a category's dots cost more downtime
actions (Discipline Illiterate), and an allowance rule's note for the character's
downtime (Hunted's actions, and what not spending them does)

Revision ID: 0105
Revises: 0103
Create Date: 2026-10-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0105"
down_revision: str | None = "0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trait_categories",
        sa.Column(
            "downtime_added_by",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "allowance_rules",
        sa.Column("note", sa.String(), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("allowance_rules", "note")
    op.drop_column("trait_categories", "downtime_added_by")
