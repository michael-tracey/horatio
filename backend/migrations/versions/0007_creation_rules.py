"""creation rules

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14 07:37:32.925101
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creation_rules",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("picks", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
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
            "(points is null and rating > 0 and picks > 0) or (points > 0 and rating is null and picks is null)",
            name=op.f("ck_creation_rules_picks_or_points"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["trait_categories.id"],
            name=op.f("fk_creation_rules_category_id_trait_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"], ["rule_sets.id"], name=op.f("fk_creation_rules_rule_set_id_rule_sets")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_creation_rules_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_creation_rules")),
    )
    op.create_index(
        op.f("ix_creation_rules_rule_set_id"), "creation_rules", ["rule_set_id"], unique=False
    )
    op.create_index(
        op.f("ix_creation_rules_troupe_id"), "creation_rules", ["troupe_id"], unique=False
    )
    op.create_table(
        "starting_traits",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
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
            ["rule_set_id"], ["rule_sets.id"], name=op.f("fk_starting_traits_rule_set_id_rule_sets")
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_starting_traits_trait_definition_id_trait_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_starting_traits_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_starting_traits")),
    )
    op.create_index(
        op.f("ix_starting_traits_rule_set_id"), "starting_traits", ["rule_set_id"], unique=False
    )
    op.create_index(
        op.f("ix_starting_traits_troupe_id"), "starting_traits", ["troupe_id"], unique=False
    )
    op.add_column("character_traits", sa.Column("creation_pick", sa.Integer(), nullable=True))
    op.add_column(
        "characters", sa.Column("creation_completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("reconciliation_items", sa.Column("pool_category", sa.String(), nullable=True))
    op.add_column("reconciliation_items", sa.Column("pool_rating", sa.Integer(), nullable=True))
    op.alter_column(
        "reconciliation_items", "trait_definition_id", existing_type=sa.UUID(), nullable=True
    )

    # Autogenerate does not see check constraints change; these are by hand.
    op.drop_constraint(
        op.f("ck_reconciliation_items_difference"), "reconciliation_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_items_difference"),
        "reconciliation_items",
        "difference in ('cost_differs', 'not_allowed', 'creation_differs')",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_items_proposed_settlement"), "reconciliation_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_items_proposed_settlement"),
        "reconciliation_items",
        "proposed_settlement in ('keep_price', 'pay_difference', 'refund_difference', 'remove_and_refund', 'pay_for_dots', 'remove_dots', 'add_free_dots')",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_items_settlement"), "reconciliation_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_items_settlement"),
        "reconciliation_items",
        "settlement is null or settlement in ('keep_price', 'pay_difference', 'refund_difference', 'remove_and_refund', 'pay_for_dots', 'remove_dots', 'add_free_dots')",
    )
    op.create_check_constraint(
        op.f("ck_character_traits_pick_is_free"),
        "character_traits",
        "creation_pick is null or creation_pick <= free_rating",
    )


def downgrade() -> None:
    # Check constraints, by hand.
    op.drop_constraint(
        op.f("ck_reconciliation_items_difference"), "reconciliation_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_items_difference"),
        "reconciliation_items",
        "difference in ('cost_differs', 'not_allowed')",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_items_proposed_settlement"), "reconciliation_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_items_proposed_settlement"),
        "reconciliation_items",
        "proposed_settlement in ('keep_price', 'pay_difference', 'refund_difference', 'remove_and_refund')",
    )
    op.drop_constraint(
        op.f("ck_reconciliation_items_settlement"), "reconciliation_items", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_reconciliation_items_settlement"),
        "reconciliation_items",
        "settlement is null or settlement in ('keep_price', 'pay_difference', 'refund_difference', 'remove_and_refund')",
    )
    op.drop_constraint(op.f("ck_character_traits_pick_is_free"), "character_traits", type_="check")
    op.alter_column(
        "reconciliation_items", "trait_definition_id", existing_type=sa.UUID(), nullable=False
    )
    op.drop_column("reconciliation_items", "pool_rating")
    op.drop_column("reconciliation_items", "pool_category")
    op.drop_column("characters", "creation_completed_at")
    op.drop_column("character_traits", "creation_pick")
    op.drop_index(op.f("ix_starting_traits_troupe_id"), table_name="starting_traits")
    op.drop_index(op.f("ix_starting_traits_rule_set_id"), table_name="starting_traits")
    op.drop_table("starting_traits")
    op.drop_index(op.f("ix_creation_rules_troupe_id"), table_name="creation_rules")
    op.drop_index(op.f("ix_creation_rules_rule_set_id"), table_name="creation_rules")
    op.drop_table("creation_rules")
