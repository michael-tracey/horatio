"""A character starting to visit a troupe (`troupe.join`) is an info event again
(issue #1066), shown in troupe and character logs as stopping (`troupe.leave`) is.
Migration 0239 made the ones kept debug; this gives them back their level.

Revision ID: 0243
Revises: 0242
Create Date: 2026-11-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0243"
down_revision: str | None = "0242"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

events = sa.table("audit_events", sa.column("action", sa.String()), sa.column("level"))


def upgrade() -> None:
    op.execute(events.update().where(events.c.action == "troupe.join").values(level="info"))


def downgrade() -> None:
    op.execute(events.update().where(events.c.action == "troupe.join").values(level="debug"))
