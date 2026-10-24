"""xp entries: a reprice, naming the purchase whose price changed with Generation

Revision ID: 0060
Revises: 0058
Create Date: 2026-10-24 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0060"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'award', 'purchase', 'settlement', 'fee', 'correction', 'self_entered', 'cap'"


def upgrade() -> None:
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS}, 'reprice')")
    op.create_check_constraint(
        "reprice_names_its_purchase", "xp_entries", "kind <> 'reprice' or corrects_id is not null"
    )


def downgrade() -> None:
    op.drop_constraint("reprice_names_its_purchase", "xp_entries", type_="check")
    op.execute("delete from xp_entries where kind = 'reprice'")
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS})")
