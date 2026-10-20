"""notifications waiting to go by email, and the key that signs their unsubscribe links

Revision ID: 0040
Revises: 0038
Create Date: 2026-10-20 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() runs once for each existing account: a key each.
    op.add_column(
        "users",
        sa.Column(
            "unsubscribe_key",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.create_table(
        "email_notices",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("troupe", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_notices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_notices")),
    )
    op.create_index(op.f("ix_email_notices_user_id"), "email_notices", ["user_id"], unique=False)
    op.create_index(op.f("ix_email_notices_due_at"), "email_notices", ["due_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_notices_due_at"), table_name="email_notices")
    op.drop_index(op.f("ix_email_notices_user_id"), table_name="email_notices")
    op.drop_table("email_notices")
    op.drop_column("users", "unsubscribe_key")
