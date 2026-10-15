"""specialisations and building troupe

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-14 22:53:22.846344
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "troupe_specializations",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("category_key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
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
            ["troupe_id"], ["troupes.id"], name=op.f("fk_troupe_specializations_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_troupe_specializations")),
        sa.UniqueConstraint(
            "troupe_id", "category_key", "name", name=op.f("uq_troupe_specializations_troupe_id")
        ),
    )
    op.create_index(
        op.f("ix_troupe_specializations_troupe_id"),
        "troupe_specializations",
        ["troupe_id"],
        unique=False,
    )
    op.add_column("characters", sa.Column("building_troupe_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_characters_building_troupe_id_troupes"),
        "characters",
        "troupes",
        ["building_troupe_id"],
        ["id"],
    )
    op.add_column(
        "trait_categories",
        sa.Column("specializes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trait_categories", "specializes")
    op.drop_constraint(
        op.f("fk_characters_building_troupe_id_troupes"), "characters", type_="foreignkey"
    )
    op.drop_column("characters", "building_troupe_id")
    op.drop_index(op.f("ix_troupe_specializations_troupe_id"), table_name="troupe_specializations")
    op.drop_table("troupe_specializations")
