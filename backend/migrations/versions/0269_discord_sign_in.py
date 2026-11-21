"""Signing in and up with Discord (#1128): sign-ins waiting on Discord's callback,
and sign-ups waiting on a name and handle.

Revision ID: 0269
Revises: 0268
Create Date: 2026-11-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0269"
down_revision: str | None = "0268"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discord_sign_ins",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next", sa.String(), nullable=True),
        sa.Column("discord_user_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("discord_username", sa.String(), nullable=True),
        sa.Column("discord_name", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discord_sign_ins")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_discord_sign_ins_token_hash")),
    )
    op.create_index(op.f("ix_discord_sign_ins_ip_address"), "discord_sign_ins", ["ip_address"])
    op.create_index(op.f("ix_discord_sign_ins_expires_at"), "discord_sign_ins", ["expires_at"])
    # Accounts linked to Discord before it could sign in (#857) have no identity row:
    # each gets one now, so the two agree (horatio.api.discord_account).
    op.execute(
        """
        insert into auth_identities (user_id, provider, subject)
        select u.id, 'discord', u.discord_user_id
        from users u
        where u.discord_user_id is not null
          and not exists (
            select 1 from auth_identities a
            where a.provider = 'discord' and a.subject = u.discord_user_id
          )
        """
    )


def downgrade() -> None:
    op.drop_table("discord_sign_ins")
