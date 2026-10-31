"""merit and flaw approvals: an approval kind for a merit or flaw added or removed
once the character is accepted, the free traits chosen with a merit asked for, and
the quest staff answered a request with (horatio.merit_requests)

Revision ID: 0116
Revises: 0115
Create Date: 2026-10-31 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0116"
down_revision: str | None = "0115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'sheet_change', 'home_troupe_change', 'discipline', 'review', 'exception', 'diablerie'"


def one_pending(apart: str) -> None:
    op.drop_index("uq_approvals_one_pending", table_name="approvals")
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text(f"status = 'pending' and kind not in ({apart})"),
    )


def upgrade() -> None:
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint("kind", "approvals", f"kind in ({KINDS}, 'merit_flaw')")
    one_pending("'discipline', 'review', 'exception', 'merit_flaw'")
    op.add_column(
        "approvals",
        sa.Column(
            "quest_id",
            sa.Uuid(),
            sa.ForeignKey(
                "quests.id", name=op.f("fk_approvals_quest_id_quests"), ondelete="SET NULL"
            ),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_approvals_quest_id"), "approvals", ["quest_id"])
    op.add_column(
        "discipline_purchases",
        sa.Column(
            "choices",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("discipline_purchases", "choices")
    op.drop_index(op.f("ix_approvals_quest_id"), table_name="approvals")
    op.drop_column("approvals", "quest_id")
    op.execute(
        "delete from discipline_purchases where approval_id in "
        "(select id from approvals where kind = 'merit_flaw')"
    )
    op.execute("delete from approvals where kind = 'merit_flaw'")
    one_pending("'discipline', 'review', 'exception'")
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint("kind", "approvals", f"kind in ({KINDS})")
