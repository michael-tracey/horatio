"""Two-step sign-in (#1057): authenticator apps, recovery codes and passkeys, sign-ins
waiting on their second step, the challenge for a passkey being added, and the troupe
setting that asks it of staff.

Revision ID: 0253
Revises: 0252
Create Date: 2026-11-20 20:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0253"
down_revision: str | None = "0252"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def record_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def user_key(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name=op.f(f"fk_{table}_user_id_users"), ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "authenticator_apps",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("secret", sa.LargeBinary(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_step", sa.BigInteger(), nullable=True),
        *record_columns(),
        user_key("authenticator_apps"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_authenticator_apps")),
        sa.UniqueConstraint("user_id", name=op.f("uq_authenticator_apps_user_id")),
    )
    op.create_table(
        "recovery_codes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *record_columns(),
        user_key("recovery_codes"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recovery_codes")),
        sa.UniqueConstraint("user_id", "code_hash", name=op.f("uq_recovery_codes_user_id")),
    )
    op.create_index(op.f("ix_recovery_codes_user_id"), "recovery_codes", ["user_id"])
    op.create_table(
        "passkeys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "transports",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *record_columns(),
        user_key("passkeys"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkeys")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_passkeys_credential_id")),
    )
    op.create_index(op.f("ix_passkeys_user_id"), "passkeys", ["user_id"])
    op.create_table(
        "second_step_sign_ins",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("login_hash", sa.String(length=64), nullable=True),
        sa.Column("challenge", sa.LargeBinary(), nullable=True),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *record_columns(),
        user_key("second_step_sign_ins"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_second_step_sign_ins")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_second_step_sign_ins_token_hash")),
    )
    op.create_index(op.f("ix_second_step_sign_ins_user_id"), "second_step_sign_ins", ["user_id"])
    op.add_column("sessions", sa.Column("passkey_challenge", sa.LargeBinary(), nullable=True))
    op.add_column(
        "troupes",
        sa.Column("staff_two_step", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("troupes", "staff_two_step")
    op.drop_column("sessions", "passkey_challenge")
    op.drop_table("second_step_sign_ins")
    op.drop_table("passkeys")
    op.drop_table("recovery_codes")
    op.drop_table("authenticator_apps")
