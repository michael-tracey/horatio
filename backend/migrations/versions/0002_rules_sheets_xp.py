"""rules sheets xp

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13 23:47:21.566585
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rule_sets",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("splat", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_sets")),
        sa.UniqueConstraint("key", name=op.f("uq_rule_sets_key")),
        sa.UniqueConstraint("splat", name=op.f("uq_rule_sets_splat")),
    )
    op.create_table(
        "trait_categories",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("group_name", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("rated", sa.Boolean(), nullable=False),
        sa.Column("max_rating", sa.Integer(), nullable=True),
        sa.Column("house_rules_per_trait", sa.Boolean(), server_default="false", nullable=False),
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
            "rated or max_rating is null", name=op.f("ck_trait_categories_unrated_has_no_max")
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name=op.f("fk_trait_categories_rule_set_id_rule_sets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trait_categories")),
        sa.UniqueConstraint("rule_set_id", "key", name=op.f("uq_trait_categories_rule_set_id")),
    )
    op.create_index(
        op.f("ix_trait_categories_rule_set_id"), "trait_categories", ["rule_set_id"], unique=False
    )
    op.create_table(
        "trait_definitions",
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("page_reference", sa.String(), nullable=True),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["trait_categories.id"],
            name=op.f("fk_trait_definitions_category_id_trait_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trait_definitions")),
        sa.UniqueConstraint("category_id", "name", name=op.f("uq_trait_definitions_category_id")),
    )
    op.create_index(
        op.f("ix_trait_definitions_category_id"), "trait_definitions", ["category_id"], unique=False
    )
    op.create_table(
        "character_traits",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("free_rating", sa.Integer(), server_default="0", nullable=False),
        sa.Column("detail", sa.String(), server_default="", nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
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
            "free_rating >= 0", name=op.f("ck_character_traits_free_rating_not_negative")
        ),
        sa.CheckConstraint(
            "rating is null and free_rating = 0 or rating >= free_rating",
            name=op.f("ck_character_traits_free_rating_within_rating"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_character_traits_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_character_traits_trait_definition_id_trait_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_character_traits")),
        sa.UniqueConstraint(
            "character_id",
            "trait_definition_id",
            "detail",
            name=op.f("uq_character_traits_character_id"),
        ),
    )
    op.create_index(
        op.f("ix_character_traits_character_id"), "character_traits", ["character_id"], unique=False
    )
    op.create_table(
        "cost_rules",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=True),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scheme", sa.String(), nullable=False),
        sa.Column("rate", sa.Integer(), nullable=True),
        sa.Column("cost_table", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("text", sa.String(), nullable=True),
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
            "scheme <> 'table' or cost_table is not null", name=op.f("ck_cost_rules_table_given")
        ),
        sa.CheckConstraint(
            "scheme in ('per_dot', 'progressive', 'table', 'fixed', 'free', 'not_allowed')",
            name=op.f("ck_cost_rules_scheme"),
        ),
        sa.CheckConstraint(
            "scheme not in ('per_dot', 'progressive', 'fixed') or rate is not null",
            name=op.f("ck_cost_rules_rate_given"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["trait_categories.id"],
            name=op.f("fk_cost_rules_category_id_trait_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"], ["rule_sets.id"], name=op.f("fk_cost_rules_rule_set_id_rule_sets")
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_cost_rules_trait_definition_id_trait_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_cost_rules_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cost_rules")),
    )
    op.create_index(op.f("ix_cost_rules_rule_set_id"), "cost_rules", ["rule_set_id"], unique=False)
    op.create_index(op.f("ix_cost_rules_troupe_id"), "cost_rules", ["troupe_id"], unique=False)
    op.create_table(
        "sheet_versions",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name=op.f("fk_sheet_versions_approved_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_sheet_versions_character_id_characters"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sheet_versions")),
        sa.UniqueConstraint("character_id", "number", name=op.f("uq_sheet_versions_character_id")),
    )
    op.create_index(
        op.f("ix_sheet_versions_character_id"), "sheet_versions", ["character_id"], unique=False
    )
    op.create_table(
        "xp_entries",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("entered_on", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("entered_by", sa.Uuid(), nullable=False),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("from_rating", sa.Integer(), nullable=True),
        sa.Column("to_rating", sa.Integer(), nullable=True),
        sa.Column("cost_basis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            "kind <> 'purchase' or (trait_definition_id is not null and from_rating is not null and to_rating is not null and cost_basis is not null)",
            name=op.f("ck_xp_entries_purchase_is_complete"),
        ),
        sa.CheckConstraint(
            "kind in ('award', 'purchase', 'settlement')", name=op.f("ck_xp_entries_kind")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"], ["characters.id"], name=op.f("fk_xp_entries_character_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["entered_by"], ["users.id"], name=op.f("fk_xp_entries_entered_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_xp_entries_trait_definition_id_trait_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_xp_entries")),
    )
    op.create_index(
        op.f("ix_xp_entries_character_id"), "xp_entries", ["character_id"], unique=False
    )
    op.add_column("characters", sa.Column("approved_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_characters_approved_version_id_sheet_versions"),
        "characters",
        "sheet_versions",
        ["approved_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_characters_approved_version_id_sheet_versions"), "characters", type_="foreignkey"
    )
    op.drop_column("characters", "approved_version_id")
    op.drop_index(op.f("ix_xp_entries_character_id"), table_name="xp_entries")
    op.drop_table("xp_entries")
    op.drop_index(op.f("ix_sheet_versions_character_id"), table_name="sheet_versions")
    op.drop_table("sheet_versions")
    op.drop_index(op.f("ix_cost_rules_troupe_id"), table_name="cost_rules")
    op.drop_index(op.f("ix_cost_rules_rule_set_id"), table_name="cost_rules")
    op.drop_table("cost_rules")
    op.drop_index(op.f("ix_character_traits_character_id"), table_name="character_traits")
    op.drop_table("character_traits")
    op.drop_index(op.f("ix_trait_definitions_category_id"), table_name="trait_definitions")
    op.drop_table("trait_definitions")
    op.drop_index(op.f("ix_trait_categories_rule_set_id"), table_name="trait_categories")
    op.drop_table("trait_categories")
    op.drop_table("rule_sets")
