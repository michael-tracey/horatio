"""Blood bonds fading with time (issue #665): a full bond drops to two drinks after
three months without drinking, a two-drink bond ends after six months apart, and a
one-drink bond after a year (MET: VTM p. 296). A bond's log gains two kinds of line:
the drop, which sets its level as a bond entered does, with when the thrall's player
was told of it; and a meeting, which keeps a lesser bond from ending. A drink a player
reports can now be a meeting instead. Each troupe keeps the day its bonds' clocks
start from, so bonds kept before this don't all fade at once.

Revision ID: 0195
Revises: 0193
Create Date: 2026-11-12 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0195"
down_revision: str | None = "0193"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("kind", "bond_entries", type_="check")
    op.create_check_constraint(
        "kind", "bond_entries", "kind in ('drink', 'entered', 'dropped', 'meeting')"
    )
    op.drop_constraint("entered_level", "bond_entries", type_="check")
    op.create_check_constraint(
        "entered_level", "bond_entries", "(kind in ('entered', 'dropped')) = (level is not null)"
    )
    op.add_column(
        "bond_entries", sa.Column("thrall_told_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "bond_reports", sa.Column("kind", sa.String(), nullable=False, server_default="drink")
    )
    op.create_check_constraint("kind", "bond_reports", "kind in ('drink', 'meeting')")
    op.add_column(
        "troupes",
        sa.Column(
            "bond_clock_from", sa.Date(), nullable=False, server_default=sa.text("current_date")
        ),
    )


def downgrade() -> None:
    op.drop_column("troupes", "bond_clock_from")
    op.drop_constraint("kind", "bond_reports", type_="check")
    op.drop_column("bond_reports", "kind")
    op.drop_column("bond_entries", "thrall_told_at")
    op.execute("delete from bond_entries where kind in ('dropped', 'meeting')")
    op.drop_constraint("entered_level", "bond_entries", type_="check")
    op.create_check_constraint(
        "entered_level", "bond_entries", "(kind = 'entered') = (level is not null)"
    )
    op.drop_constraint("kind", "bond_entries", type_="check")
    op.create_check_constraint("kind", "bond_entries", "kind in ('drink', 'entered')")
