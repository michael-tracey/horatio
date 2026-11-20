"""Sign-ins and sign-ups tried, for the limits on them (issue #1059). Kept a day at most.

Revision ID: 0240
Revises: 0239
Create Date: 2026-11-20 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0240"
down_revision: str | None = "0239"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_attempts",
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("identity_hash", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_attempts")),
    )
    op.create_index("ix_auth_attempts_created_at", "auth_attempts", ["created_at"])
    op.create_index(
        "ix_auth_attempts_action_ip_created_at",
        "auth_attempts",
        ["action", "ip_address", "created_at"],
    )
    op.create_index(
        "ix_auth_attempts_action_identity_ip_created_at",
        "auth_attempts",
        ["action", "identity_hash", "ip_address", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_action_identity_ip_created_at", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_action_ip_created_at", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_created_at", table_name="auth_attempts")
    op.drop_table("auth_attempts")
