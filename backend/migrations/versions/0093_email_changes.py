"""changing someone's email: the change waits, with its link, until it is confirmed
at the new address

Revision ID: 0093
Revises: 0092
Create Date: 2026-10-27 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0093"
down_revision: str | None = "0092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_changes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("new_email", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_email_changes_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_email_changes_created_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_changes")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_changes_token_hash")),
        sa.UniqueConstraint("user_id", name=op.f("uq_email_changes_user_id")),
    )


def downgrade() -> None:
    op.drop_table("email_changes")
