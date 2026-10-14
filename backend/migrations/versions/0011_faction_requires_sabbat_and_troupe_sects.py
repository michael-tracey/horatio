"""faction requires sabbat and troupe sects

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-14 12:32:23.009175
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('trait_categories', sa.Column('requires', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('troupes', sa.Column('allowed_sects', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('troupes', 'allowed_sects')
    op.drop_column('trait_categories', 'requires')
