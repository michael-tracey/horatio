"""Creation XP lost on a first acceptance is a kind of its own, "lost", rather than a
fee (issue #369): it was never spent, so the sheet no longer counts it as Spent.

Revision ID: 0121
Revises: 0120
Create Date: 2026-10-31 20:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0121"
down_revision: str | None = "0120"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = (
    "'award', 'purchase', 'settlement', 'fee', 'correction', 'self_entered', 'cap', 'reprice',"
    " 'debt'"
)
OLD_REASON = "Unspent creation XP past the bank is lost on acceptance"
REASON = "Creation XP over what can be kept, lost when the first home troupe accepted it"


def upgrade() -> None:
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS}, 'lost')")
    op.execute(
        f"update xp_entries set kind = 'lost', reason = '{REASON}'"
        f" where kind = 'fee' and reason = '{OLD_REASON}'"
    )


def downgrade() -> None:
    op.execute(f"update xp_entries set kind = 'fee', reason = '{OLD_REASON}' where kind = 'lost'")
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS})")
