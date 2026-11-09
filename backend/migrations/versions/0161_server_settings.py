"""server settings: settings for all of Horatio that the custodian chooses, the
first its loading animation, by splat (issue #568)

Revision ID: 0161
Revises: 0160
Create Date: 2026-11-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0161"
down_revision: str | None = "0160"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "server_settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_server_settings")),
    )


def downgrade() -> None:
    op.drop_table("server_settings")
