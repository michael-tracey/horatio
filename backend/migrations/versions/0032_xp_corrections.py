"""xp corrections

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-19 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("xp_entries", sa.Column("corrects_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_xp_entries_corrects_id_xp_entries"),
        "xp_entries",
        "xp_entries",
        ["corrects_id"],
        ["id"],
    )
    op.create_index(op.f("ix_xp_entries_corrects_id"), "xp_entries", ["corrects_id"], unique=False)
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint(
        "kind", "xp_entries", "kind in ('award', 'purchase', 'settlement', 'fee', 'correction')"
    )
    op.create_check_constraint(
        "correction_names_its_award",
        "xp_entries",
        "kind <> 'correction' or corrects_id is not null",
    )


def downgrade() -> None:
    op.execute("delete from xp_entries where kind = 'correction'")
    op.drop_constraint("correction_names_its_award", "xp_entries", type_="check")
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint(
        "kind", "xp_entries", "kind in ('award', 'purchase', 'settlement', 'fee')"
    )
    op.drop_index(op.f("ix_xp_entries_corrects_id"), table_name="xp_entries")
    op.drop_constraint(
        op.f("fk_xp_entries_corrects_id_xp_entries"), "xp_entries", type_="foreignkey"
    )
    op.drop_column("xp_entries", "corrects_id")
