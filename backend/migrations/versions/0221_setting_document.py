"""The Setting Style Document's generated parts (issue #771): a reason for each clan
rarity the troupe sets itself, the document on the troupe's profile, and the optional
New Character Incentive (MET: VTM p. 349).

Revision ID: 0221
Revises: 0220
Create Date: 2026-11-13 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0221"
down_revision: str | None = "0220"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column(
            "clan_rarity_notes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "troupes",
        sa.Column("setting_public", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "troupes",
        sa.Column("new_character_incentive", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "new_character_incentive")
    op.drop_column("troupes", "setting_public")
    op.drop_column("troupes", "clan_rarity_notes")
