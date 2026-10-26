"""house traits: merits and flaws a troupe makes itself, and those staff apply

Revision ID: 0073
Revises: 0071
Create Date: 2026-10-26 20:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[Any]]:
    return [
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
    ]


def upgrade() -> None:
    op.add_column("trait_definitions", sa.Column("troupe_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_trait_definitions_troupe_id_troupes"),
        "trait_definitions",
        "troupes",
        ["troupe_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_trait_definitions_troupe_id"), "trait_definitions", ["troupe_id"], unique=False
    )
    op.drop_constraint(
        op.f("uq_trait_definitions_category_id"), "trait_definitions", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_trait_definitions_category_id"),
        "trait_definitions",
        ["category_id", "name", "troupe_id"],
        postgresql_nulls_not_distinct=True,
    )

    op.create_table(
        "house_traits",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("splat", sa.String(), server_default="vampire", nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), server_default="General", nullable=False),
        sa.Column("availability", sa.String(), nullable=False),
        sa.Column("creation_only", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("description", sa.String(), server_default="", nullable=False),
        sa.Column("requirement", sa.String(), server_default="", nullable=False),
        sa.Column(
            "effects",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "availability in ('staff', 'building')", name=op.f("ck_house_traits_availability")
        ),
        sa.CheckConstraint(
            "category in ('merits', 'flaws')", name=op.f("ck_house_traits_category")
        ),
        sa.CheckConstraint(
            "kind in ('General', 'Clan', 'Sabbat')", name=op.f("ck_house_traits_kind")
        ),
        sa.CheckConstraint("points between 1 and 7", name=op.f("ck_house_traits_points")),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_house_traits_trait_definition_id_trait_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_house_traits_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_house_traits")),
        sa.UniqueConstraint(
            "trait_definition_id", name=op.f("uq_house_traits_trait_definition_id")
        ),
        sa.UniqueConstraint(
            "troupe_id", "splat", "category", "name", name=op.f("uq_house_traits_troupe_id")
        ),
    )
    op.create_index(op.f("ix_house_traits_troupe_id"), "house_traits", ["troupe_id"], unique=False)

    op.create_table(
        "applied_house_traits",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("character_trait_id", sa.Uuid(), nullable=False),
        sa.Column("house_trait_id", sa.Uuid(), nullable=False),
        sa.Column("free", sa.Boolean(), nullable=False),
        sa.Column("counts_toward_limit", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("cost", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("applied_by", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["applied_by"], ["users.id"], name=op.f("fk_applied_house_traits_applied_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_applied_house_traits_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["character_trait_id"],
            ["character_traits.id"],
            name=op.f("fk_applied_house_traits_character_trait_id_character_traits"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["house_trait_id"],
            ["house_traits.id"],
            name=op.f("fk_applied_house_traits_house_trait_id_house_traits"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applied_house_traits")),
        sa.UniqueConstraint(
            "character_trait_id", name=op.f("uq_applied_house_traits_character_trait_id")
        ),
    )
    op.create_index(
        op.f("ix_applied_house_traits_character_id"),
        "applied_house_traits",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_applied_house_traits_house_trait_id"),
        "applied_house_traits",
        ["house_trait_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_applied_house_traits_house_trait_id"), table_name="applied_house_traits")
    op.drop_index(op.f("ix_applied_house_traits_character_id"), table_name="applied_house_traits")
    op.drop_table("applied_house_traits")
    op.drop_index(op.f("ix_house_traits_troupe_id"), table_name="house_traits")
    op.drop_table("house_traits")
    # House traits' definitions go with them; sheets can no longer hold them.
    op.execute("delete from trait_definitions where troupe_id is not null")
    op.drop_constraint(
        op.f("uq_trait_definitions_category_id"), "trait_definitions", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_trait_definitions_category_id"), "trait_definitions", ["category_id", "name"]
    )
    op.drop_index(op.f("ix_trait_definitions_troupe_id"), table_name="trait_definitions")
    op.drop_constraint(
        op.f("fk_trait_definitions_troupe_id_troupes"), "trait_definitions", type_="foreignkey"
    )
    op.drop_column("trait_definitions", "troupe_id")
