"""A troupe's own wording on a book trait (issue #433): its text, in Markdown, added
to the book's summary or in place of it.

Revision ID: 0130
Revises: 0129
Create Date: 2026-11-01 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0130"
down_revision: str | None = "0129"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trait_overrides", sa.Column("wording", sa.String(), server_default="", nullable=False)
    )
    op.add_column(
        "trait_overrides",
        sa.Column("wording_mode", sa.String(), server_default="added", nullable=False),
    )
    op.create_check_constraint(
        "wording_mode", "trait_overrides", "wording_mode in ('added', 'replaces')"
    )


def downgrade() -> None:
    op.drop_constraint("wording_mode", "trait_overrides", type_="check")
    op.drop_column("trait_overrides", "wording_mode")
    op.drop_column("trait_overrides", "wording")
