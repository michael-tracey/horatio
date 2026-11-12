"""boon gallant: a boon's log records Gallant given, or not, when a boon is
repaid (issue #693; MET: VTM pp. 402, 405)

Revision ID: 0199
Revises: 0193
Create Date: 2026-11-12 23:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0199"
down_revision: str | None = "0193"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = "kind in ('registered', 'edited', 'traded', 'passed_on', 'settled', 'voided', 'reopened')"
AFTER = (
    "kind in ('registered', 'edited', 'traded', 'passed_on', 'settled', 'voided', 'reopened',"
    " 'gallant_given', 'gallant_declined')"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_boon_events_kind"), "boon_events", type_="check")
    op.create_check_constraint(op.f("ck_boon_events_kind"), "boon_events", AFTER)


def downgrade() -> None:
    op.execute("delete from boon_events where kind in ('gallant_given', 'gallant_declined')")
    op.drop_constraint(op.f("ck_boon_events_kind"), "boon_events", type_="check")
    op.create_check_constraint(op.f("ck_boon_events_kind"), "boon_events", BEFORE)
