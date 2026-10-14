"""home troupe changes reconciliation

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14 00:38:22.658353
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "home_troupe_changes",
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("from_troupe_id", sa.Uuid(), nullable=True),
        sa.Column("to_troupe_id", sa.Uuid(), nullable=False),
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
            name=op.f("fk_home_troupe_changes_approval_id_approvals"),
        ),
        sa.ForeignKeyConstraint(
            ["from_troupe_id"],
            ["troupes.id"],
            name=op.f("fk_home_troupe_changes_from_troupe_id_troupes"),
        ),
        sa.ForeignKeyConstraint(
            ["to_troupe_id"],
            ["troupes.id"],
            name=op.f("fk_home_troupe_changes_to_troupe_id_troupes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_home_troupe_changes")),
        sa.UniqueConstraint("approval_id", name=op.f("uq_home_troupe_changes_approval_id")),
    )
    op.create_table(
        "reconciliation_items",
        sa.Column("home_troupe_change_id", sa.Uuid(), nullable=False),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=False),
        sa.Column("detail", sa.String(), server_default="", nullable=False),
        sa.Column("difference", sa.String(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("old_cost", sa.Integer(), nullable=False),
        sa.Column("new_cost", sa.Integer(), nullable=True),
        sa.Column("proposed_settlement", sa.String(), nullable=False),
        sa.Column("settlement", sa.String(), nullable=True),
        sa.Column("xp_delta", sa.Integer(), nullable=True),
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
            "difference in ('cost_differs', 'not_allowed')",
            name=op.f("ck_reconciliation_items_difference"),
        ),
        sa.CheckConstraint(
            "proposed_settlement in ('keep_price', 'pay_difference', 'refund_difference', 'remove_and_refund')",
            name=op.f("ck_reconciliation_items_proposed_settlement"),
        ),
        sa.CheckConstraint(
            "settlement is null or settlement in ('keep_price', 'pay_difference', 'refund_difference', 'remove_and_refund')",
            name=op.f("ck_reconciliation_items_settlement"),
        ),
        sa.ForeignKeyConstraint(
            ["home_troupe_change_id"],
            ["home_troupe_changes.id"],
            name=op.f("fk_reconciliation_items_home_troupe_change_id_home_troupe_changes"),
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_reconciliation_items_trait_definition_id_trait_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_items")),
    )
    op.create_index(
        op.f("ix_reconciliation_items_home_troupe_change_id"),
        "reconciliation_items",
        ["home_troupe_change_id"],
        unique=False,
    )
    op.add_column("xp_entries", sa.Column("reconciliation_item_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_xp_entries_reconciliation_item_id_reconciliation_items"),
        "xp_entries",
        "reconciliation_items",
        ["reconciliation_item_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_xp_entries_settlement_names_its_difference"),
        "xp_entries",
        "kind <> 'settlement' or reconciliation_item_id is not null",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_xp_entries_settlement_names_its_difference"), "xp_entries", type_="check"
    )
    op.drop_constraint(
        op.f("fk_xp_entries_reconciliation_item_id_reconciliation_items"),
        "xp_entries",
        type_="foreignkey",
    )
    op.drop_column("xp_entries", "reconciliation_item_id")
    op.drop_index(
        op.f("ix_reconciliation_items_home_troupe_change_id"), table_name="reconciliation_items"
    )
    op.drop_table("reconciliation_items")
    op.drop_table("home_troupe_changes")
