"""troupe requests

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-19 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "troupe_requests",
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), server_default="", nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'withdrawn')",
            name=op.f("ck_troupe_requests_status"),
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"], ["users.id"], name=op.f("fk_troupe_requests_requester_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["users.id"], name=op.f("fk_troupe_requests_decided_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_troupe_requests_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_troupe_requests")),
    )
    op.create_index(
        op.f("ix_troupe_requests_requester_id"), "troupe_requests", ["requester_id"], unique=False
    )
    op.create_index(op.f("ix_troupe_requests_status"), "troupe_requests", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_troupe_requests_status"), table_name="troupe_requests")
    op.drop_index(op.f("ix_troupe_requests_requester_id"), table_name="troupe_requests")
    op.drop_table("troupe_requests")
