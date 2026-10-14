"""check overrides and review

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-14 17:53:18.671567
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint(
        "kind",
        "approvals",
        "kind in ('sheet_change', 'home_troupe_change', 'discipline', 'review')",
    )
    op.drop_index("uq_approvals_one_pending", table_name="approvals")
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' and kind not in ('discipline', 'review')"),
    )
    op.create_table(
        "check_overrides",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("check_key", sa.String(), nullable=False),
        sa.Column("strength", sa.String(), nullable=False),
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
            "strength in ('refuse', 'complete', 'review', 'note', 'off')",
            name=op.f("ck_check_overrides_strength"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_check_overrides_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_check_overrides")),
        sa.UniqueConstraint("troupe_id", "check_key", name=op.f("uq_check_overrides_troupe_id")),
    )
    op.create_index(
        op.f("ix_check_overrides_troupe_id"), "check_overrides", ["troupe_id"], unique=False
    )


def downgrade() -> None:
    op.execute(
        "delete from discipline_purchases where approval_id in"
        " (select id from approvals where kind = 'review')"
    )
    op.execute("delete from approvals where kind = 'review'")
    op.drop_index("uq_approvals_one_pending", table_name="approvals")
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' and kind <> 'discipline'"),
    )
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint(
        "kind", "approvals", "kind in ('sheet_change', 'home_troupe_change', 'discipline')"
    )
    op.drop_index(op.f("ix_check_overrides_troupe_id"), table_name="check_overrides")
    op.drop_table("check_overrides")
