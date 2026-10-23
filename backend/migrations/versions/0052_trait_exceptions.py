"""trait exceptions: traits asked for, or given, despite the rules or free

Revision ID: 0052
Revises: 0049
Create Date: 2026-10-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint(
        "kind",
        "approvals",
        "kind in ('sheet_change', 'home_troupe_change', 'discipline', 'review', 'exception')",
    )
    op.drop_index("uq_approvals_one_pending", table_name="approvals")
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'pending' and kind not in ('discipline', 'review', 'exception')"
        ),
    )
    op.create_table(
        "trait_exceptions",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("character_trait_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column(
            "checks",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("free", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("normal_cost", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("given_by", sa.Uuid(), nullable=True),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=True),
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
            ["approval_id"],
            ["approvals.id"],
            name=op.f("fk_trait_exceptions_approval_id_approvals"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_trait_exceptions_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["character_trait_id"],
            ["character_traits.id"],
            name=op.f("fk_trait_exceptions_character_trait_id_character_traits"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["given_by"], ["users.id"], name=op.f("fk_trait_exceptions_given_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_trait_exceptions_requested_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trait_exceptions")),
        sa.UniqueConstraint("approval_id", name=op.f("uq_trait_exceptions_approval_id")),
    )
    op.create_index(
        op.f("ix_trait_exceptions_character_id"),
        "trait_exceptions",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trait_exceptions_character_trait_id"),
        "trait_exceptions",
        ["character_trait_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trait_exceptions_character_trait_id"), table_name="trait_exceptions")
    op.drop_index(op.f("ix_trait_exceptions_character_id"), table_name="trait_exceptions")
    op.drop_table("trait_exceptions")
    op.execute(
        "delete from discipline_purchases where approval_id in"
        " (select id from approvals where kind = 'exception')"
    )
    op.execute("delete from approvals where kind = 'exception'")
    op.drop_index("uq_approvals_one_pending", table_name="approvals")
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' and kind not in ('discipline', 'review')"),
    )
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint(
        "kind",
        "approvals",
        "kind in ('sheet_change', 'home_troupe_change', 'discipline', 'review')",
    )
