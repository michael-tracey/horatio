"""viewings: the custodian viewing Horatio as someone, read-only, for support

Revision ID: 0094
Revises: 0085
Create Date: 2026-10-27 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0094"
down_revision: str | None = "0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "viewings",
        sa.Column("custodian_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
            ["custodian_id"], ["users.id"], name=op.f("fk_viewings_custodian_id_users")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_viewings_user_id_users")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_viewings_session_id_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_viewings")),
    )
    op.create_index(op.f("ix_viewings_user_id"), "viewings", ["user_id"])
    op.create_index(op.f("ix_viewings_session_id"), "viewings", ["session_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_viewings_session_id"), table_name="viewings")
    op.drop_index(op.f("ix_viewings_user_id"), table_name="viewings")
    op.drop_table("viewings")
