"""What a troupe calls the clan stored as "Assamite" (issue #430): Banu Haqim or
Assamite. Troupes made before this keep Assamite, the name they have always seen;
new troupes start with Banu Haqim.

Revision ID: 0128
Revises: 0127
Create Date: 2026-11-01 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0128"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every troupe there already is gets Assamite, then new ones default to Banu Haqim.
    op.add_column(
        "troupes",
        sa.Column("assamite_name", sa.String(), server_default="Assamite", nullable=False),
    )
    op.alter_column("troupes", "assamite_name", server_default="Banu Haqim")
    op.create_check_constraint(
        "assamite_name", "troupes", "assamite_name in ('Banu Haqim', 'Assamite')"
    )


def downgrade() -> None:
    op.drop_constraint("assamite_name", "troupes", type_="check")
    op.drop_column("troupes", "assamite_name")
