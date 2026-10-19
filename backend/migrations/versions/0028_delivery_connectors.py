"""delivery connectors

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-18 19:56:31.287742
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "troupe_connectors",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("mode", sa.String(), server_default="alert", nullable=False),
        sa.Column("test_mode", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
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
        sa.CheckConstraint("kind in ('discord', 'email')", name=op.f("ck_troupe_connectors_kind")),
        sa.CheckConstraint("mode in ('full', 'alert')", name=op.f("ck_troupe_connectors_mode")),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_troupe_connectors_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_troupe_connectors")),
        sa.UniqueConstraint("troupe_id", "kind", name=op.f("uq_troupe_connectors_troupe_id")),
    )
    op.create_index(
        op.f("ix_troupe_connectors_troupe_id"), "troupe_connectors", ["troupe_id"], unique=False
    )
    op.add_column(
        "deliveries", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("deliveries", sa.Column("marked_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_deliveries_marked_by_users"), "deliveries", "users", ["marked_by"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_deliveries_marked_by_users"), "deliveries", type_="foreignkey")
    op.drop_column("deliveries", "marked_by")
    op.drop_column("deliveries", "next_attempt_at")
    op.drop_index(op.f("ix_troupe_connectors_troupe_id"), table_name="troupe_connectors")
    op.drop_table("troupe_connectors")
