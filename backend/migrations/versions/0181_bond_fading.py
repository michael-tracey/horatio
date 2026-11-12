"""Blood bonds fading (issue #662): when a regnant meets Final Death, each of its bonds
fades over 30 days (MET: VTM p. 296), hidden from the thrall until it has faded. A
bond keeps the day its fade ends and why, when the thrall's player was told it had
faded, and whether the regnant's player still sees a bond whose thrall has died.

Revision ID: 0181
Revises: 0175
Create Date: 2026-11-12 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0181"
down_revision: str | None = "0175"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("blood_bonds", sa.Column("fades_on", sa.Date(), nullable=True))
    op.add_column(
        "blood_bonds", sa.Column("fade_reason", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "blood_bonds",
        sa.Column("thrall_told_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "blood_bonds",
        sa.Column("kept_for_regnant", sa.Boolean(), nullable=False, server_default="false"),
    )
    # A bond that existed as fading before this had no day to end on: it ends today.
    op.execute("update blood_bonds set fades_on = current_date where status = 'fading'")
    op.create_check_constraint(
        "fading", "blood_bonds", "(status = 'fading') <= (fades_on is not null)"
    )


def downgrade() -> None:
    op.drop_constraint("fading", "blood_bonds", type_="check")
    op.drop_column("blood_bonds", "kept_for_regnant")
    op.drop_column("blood_bonds", "thrall_told_at")
    op.drop_column("blood_bonds", "fade_reason")
    op.drop_column("blood_bonds", "fades_on")
