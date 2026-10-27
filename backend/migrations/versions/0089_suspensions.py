"""suspensions: the custodian suspending an account, and lifting it

Revision ID: 0089
Revises: 0087
Create Date: 2026-10-27 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0089"
down_revision: str | None = "0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suspensions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_by_id", sa.Uuid(), nullable=False),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lifted_by_id", sa.Uuid(), nullable=True),
        sa.Column("lift_reason", sa.Text(), nullable=True),
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
            ["user_id"], ["users.id"], name=op.f("fk_suspensions_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["suspended_by_id"], ["users.id"], name=op.f("fk_suspensions_suspended_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["lifted_by_id"], ["users.id"], name=op.f("fk_suspensions_lifted_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suspensions")),
    )
    op.create_index(op.f("ix_suspensions_user_id"), "suspensions", ["user_id"], unique=False)
    op.create_index(
        "uq_suspensions_live_user_id",
        "suspensions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("lifted_at is null"),
    )


def downgrade() -> None:
    op.drop_index("uq_suspensions_live_user_id", table_name="suspensions")
    op.drop_index(op.f("ix_suspensions_user_id"), table_name="suspensions")
    op.drop_table("suspensions")
