"""the Who's Who: the court order of a troupe's own titles, NPCs staff list on it,
and whether it shows negative status

Revision ID: 0087
Revises: 0086
Create Date: 2026-10-27 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0087"
down_revision: str | None = "0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupe_titles", sa.Column("position", sa.Integer(), server_default="0", nullable=False)
    )
    # A troupe's own titles start in the order of their names.
    op.execute(
        """
        update troupe_titles set position = ordered.n
        from (
            select id, row_number() over (partition by troupe_id order by name) as n
            from troupe_titles
        ) as ordered
        where troupe_titles.id = ordered.id
        """
    )
    op.add_column(
        "characters",
        sa.Column("on_whos_who", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "troupes",
        sa.Column("whos_who_negative", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "whos_who_negative")
    op.drop_column("characters", "on_whos_who")
    op.drop_column("troupe_titles", "position")
