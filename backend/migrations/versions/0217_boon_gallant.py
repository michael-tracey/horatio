"""boon gallant: a boon's log records Gallant given, or not, when a boon is
repaid (issue #693; MET: VTM pp. 402, 405)

Revision ID: 0217
Revises: 0216
Create Date: 2026-11-12 23:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0217"
down_revision: str | None = "0216"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# As 0207_boon_review left them.
BEFORE = (
    "kind in ('registered', 'edited', 'traded', 'passed_on', 'settled', 'voided',"
    " 'reopened', 'submitted', 'accepted', 'rejected', 'flagged', 'flag_cleared', 'linked')"
)
AFTER = (
    "kind in ('registered', 'edited', 'traded', 'passed_on', 'settled', 'voided',"
    " 'reopened', 'submitted', 'accepted', 'rejected', 'flagged', 'flag_cleared', 'linked',"
    " 'gallant_given', 'gallant_declined')"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_boon_events_kind"), "boon_events", type_="check")
    op.create_check_constraint(op.f("ck_boon_events_kind"), "boon_events", AFTER)


def downgrade() -> None:
    op.execute("delete from boon_events where kind in ('gallant_given', 'gallant_declined')")
    op.drop_constraint(op.f("ck_boon_events_kind"), "boon_events", type_="check")
    op.create_check_constraint(op.f("ck_boon_events_kind"), "boon_events", BEFORE)
