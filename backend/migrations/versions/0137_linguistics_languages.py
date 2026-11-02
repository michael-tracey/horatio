"""How many languages Linguistics gives in a troupe (issue #437): the book's one per
dot, the accelerated chart or the troupe's own, and whether Natural Linguist
doubles it. Every troupe starts on the book's.

Revision ID: 0137
Revises: 0134
Create Date: 2026-11-01 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0137"
down_revision: str | None = "0134"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("languages", sa.String(), server_default="book", nullable=False)
    )
    op.create_check_constraint(
        "languages", "troupes", "languages in ('book', 'accelerated', 'custom')"
    )
    op.add_column("troupes", sa.Column("languages_table", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column(
        "troupes",
        sa.Column("natural_linguist_doubles", sa.Boolean(), server_default="true", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "natural_linguist_doubles")
    op.drop_column("troupes", "languages_table")
    op.drop_constraint("languages", "troupes", type_="check")
    op.drop_column("troupes", "languages")
