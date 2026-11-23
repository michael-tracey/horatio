"""custodian_accesses: the custodian switching custodian access on for a sign-in, with a
reason, for an hour from their last use of it (#1213). Until then a custodian has only
their troupe roles' permissions.

Revision ID: 0290
Revises: 0288
Create Date: 2026-11-22 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0290"
down_revision: str | None = "0288"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custodian_accesses",
        sa.Column("custodian_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lasts", sa.Interval(), nullable=False),
        sa.Column(
            "told_troupe_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default="{}",
            nullable=False,
        ),
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
            ["custodian_id"], ["users.id"], name=op.f("fk_custodian_accesses_custodian_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_custodian_accesses_session_id_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custodian_accesses")),
    )
    op.create_index(
        op.f("ix_custodian_accesses_custodian_id"), "custodian_accesses", ["custodian_id"]
    )
    op.create_index(op.f("ix_custodian_accesses_session_id"), "custodian_accesses", ["session_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_custodian_accesses_session_id"), table_name="custodian_accesses")
    op.drop_index(op.f("ix_custodian_accesses_custodian_id"), table_name="custodian_accesses")
    op.drop_table("custodian_accesses")
