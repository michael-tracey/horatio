"""A digest email a day or a week, and quiet hours for phone notifications (#1196): the
last digest each person was sent, and a push held for the end of their quiet hours.

Revision ID: 0286
Revises: 0283
Create Date: 2026-11-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0286"
down_revision: str | None = "0283"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_digests",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("window", sa.String(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_digests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_digests")),
        sa.UniqueConstraint("user_id", name=op.f("uq_email_digests_user_id")),
    )
    op.add_column(
        "push_notices", sa.Column("held_until", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("push_notices", "held_until")
    op.drop_table("email_digests")
