"""A troupe's feeding setting (issue #416): feeding tracked as the book has it, or left
out of Horatio; and the optional rule Blood Resonance (MET: VTM Vol. 2, pp. 294-297),
with the Resonance and Dyscrasia a feeding answer gives.

Revision ID: 0123
Revises: 0122
Create Date: 2026-11-01 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0123"
down_revision: str | None = "0122"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("feeding", sa.String(), server_default="book", nullable=False)
    )
    op.create_check_constraint("feeding", "troupes", "feeding in ('off', 'book')")
    op.add_column(
        "troupes",
        sa.Column("feeding_resonance", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("submissions", sa.Column("feeding_resonance", sa.String(), nullable=True))
    op.create_check_constraint(
        "feeding_resonance",
        "submissions",
        "feeding_resonance is null or feeding_resonance in"
        " ('choleric', 'melancholic', 'phlegmatic', 'sanguine')",
    )
    op.add_column(
        "submissions",
        sa.Column("feeding_dyscrasia", sa.String(), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("submissions", "feeding_dyscrasia")
    op.drop_constraint("feeding_resonance", "submissions", type_="check")
    op.drop_column("submissions", "feeding_resonance")
    op.drop_column("troupes", "feeding_resonance")
    op.drop_constraint("feeding", "troupes", type_="check")
    op.drop_column("troupes", "feeding")
