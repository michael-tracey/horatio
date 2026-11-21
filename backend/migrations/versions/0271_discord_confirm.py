"""Confirming it's you with Discord, for an account with no password (#1140): the
sign-in a Discord state belongs to, and until when a sign-in is confirmed.

Revision ID: 0271
Revises: 0269
Create Date: 2026-11-21 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0271"
down_revision: str | None = "0269"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("discord_sign_ins", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_discord_sign_ins_session_id"), "discord_sign_ins", ["session_id"])
    op.create_foreign_key(
        op.f("fk_discord_sign_ins_session_id_sessions"),
        "discord_sign_ins",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "sessions", sa.Column("confirmed_until", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sessions", "confirmed_until")
    op.drop_constraint(
        op.f("fk_discord_sign_ins_session_id_sessions"), "discord_sign_ins", type_="foreignkey"
    )
    op.drop_index(op.f("ix_discord_sign_ins_session_id"), table_name="discord_sign_ins")
    op.drop_column("discord_sign_ins", "session_id")
