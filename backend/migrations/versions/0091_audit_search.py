"""the custodian's search of the audit log: an index to read it newest first

Revision ID: 0091
Revises: 0089
Create Date: 2026-10-27 20:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0091"
down_revision: str | None = "0089"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_events_created_at_id", "audit_events", ["created_at", "id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at_id", table_name="audit_events")
