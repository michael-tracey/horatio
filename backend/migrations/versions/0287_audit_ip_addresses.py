"""IP addresses in an audit event's own column (#1205): where a sign-in, a reset
request or the like came from, kept always, and moved out of the events' `data`. The
custodian's "Record IP addresses with sign-in events" becomes "Show IP addresses",
which only says whether they are shown.

Revision ID: 0287
Revises: 0286
Create Date: 2026-11-22 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0287"
down_revision: str | None = "0286"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("ip_address", sa.String(64), nullable=True))
    op.execute(
        "UPDATE audit_events SET ip_address = left(data ->> 'ip', 64), data = data - 'ip'"
        " WHERE data ? 'ip'"
    )
    # The setting keeps its value under its new name.
    op.execute(
        "UPDATE server_settings"
        " SET value = (value - 'sign_in_ips') || jsonb_build_object('show_ips', value -> 'sign_in_ips')"
        " WHERE key = 'audit_log' AND jsonb_typeof(value) = 'object' AND value ? 'sign_in_ips'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE server_settings"
        " SET value = (value - 'show_ips') || jsonb_build_object('sign_in_ips', value -> 'show_ips')"
        " WHERE key = 'audit_log' AND jsonb_typeof(value) = 'object' AND value ? 'show_ips'"
    )
    op.execute(
        "UPDATE audit_events SET data = data || jsonb_build_object('ip', ip_address)"
        " WHERE ip_address IS NOT NULL"
    )
    op.drop_column("audit_events", "ip_address")
