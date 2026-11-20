"""Devices where people turned on push notifications, and what waits to go to them
(issue #1054).

Revision ID: 0252
Revises: 0249
Create Date: 2026-11-20 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0252"
down_revision: str | None = "0249"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("p256dh", sa.String(), nullable=False),
        sa.Column("auth", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
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
            name=op.f("fk_push_devices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_devices")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_devices_endpoint")),
    )
    op.create_index(op.f("ix_push_devices_user_id"), "push_devices", ["user_id"])
    op.create_table(
        "push_notices",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("troupe", sa.String(), nullable=True),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("link", sa.String(), nullable=False),
        sa.Column(
            "due_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["push_devices.id"],
            name=op.f("fk_push_notices_device_id_push_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_notices")),
    )
    op.create_index(op.f("ix_push_notices_device_id"), "push_notices", ["device_id"])
    op.create_index(op.f("ix_push_notices_due_at"), "push_notices", ["due_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_push_notices_due_at"), table_name="push_notices")
    op.drop_index(op.f("ix_push_notices_device_id"), table_name="push_notices")
    op.drop_table("push_notices")
    op.drop_index(op.f("ix_push_devices_user_id"), table_name="push_devices")
    op.drop_table("push_devices")
