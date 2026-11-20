"""Signing in with a passkey alone (#1098): the challenges waiting on the browser's
answer, and whether each passkey can sign in without a password.

Revision ID: 0259
Revises: 0253
Create Date: 2026-11-20 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0259"
down_revision: str | None = "0253"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("passkeys", sa.Column("discoverable", sa.Boolean(), nullable=True))
    op.create_table(
        "passkey_sign_ins",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkey_sign_ins")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_passkey_sign_ins_token_hash")),
    )
    op.create_index(op.f("ix_passkey_sign_ins_ip_address"), "passkey_sign_ins", ["ip_address"])
    op.create_index(op.f("ix_passkey_sign_ins_expires_at"), "passkey_sign_ins", ["expires_at"])


def downgrade() -> None:
    op.drop_table("passkey_sign_ins")
    op.drop_column("passkeys", "discoverable")
