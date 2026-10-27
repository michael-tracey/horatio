"""merging two accounts of the same person: the closed account names the one it was
merged into, and keeps its email and handle for the record, freed from uniqueness

Revision ID: 0096
Revises: 0085
Create Date: 2026-10-27 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0096"
down_revision: str | None = "0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("merged_into_id", sa.Uuid(), nullable=True))
    op.add_column("users", sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_merged_into_id_users"), "users", "users", ["merged_into_id"], ["id"]
    )
    for name, column in (("uq_users_email_lower", "email"), ("uq_users_handle_lower", "handle")):
        op.drop_index(name, table_name="users")
        op.create_index(
            name,
            "users",
            [sa.literal_column(f"lower({column})")],
            unique=True,
            postgresql_where=sa.text("merged_into_id is null"),
        )


def downgrade() -> None:
    for name, column in (("uq_users_email_lower", "email"), ("uq_users_handle_lower", "handle")):
        op.drop_index(name, table_name="users")
        op.create_index(name, "users", [sa.literal_column(f"lower({column})")], unique=True)
    op.drop_constraint(op.f("fk_users_merged_into_id_users"), "users", type_="foreignkey")
    op.drop_column("users", "merged_at")
    op.drop_column("users", "merged_into_id")
