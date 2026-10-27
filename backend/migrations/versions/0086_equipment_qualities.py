"""equipment qualities: each rule set's equipment kinds and grades, its qualities, and
the book's sample items as templates

Revision ID: 0086
Revises: 0085
Create Date: 2026-10-27 20:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0086"
down_revision: str | None = "0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KIND_CHECK = "kind in ('melee', 'ranged', 'protective', 'miscellaneous')"


def record_columns() -> list[sa.Column[Any]]:
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
    op.add_column(
        "rule_sets",
        sa.Column(
            "equipment",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.create_table(
        "equipment_qualities",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("effect", sa.String(), nullable=False),
        sa.Column("page", sa.String(), nullable=True),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("retired", sa.Boolean(), server_default="false", nullable=False),
        *record_columns(),
        sa.CheckConstraint(KIND_CHECK, name=op.f("ck_equipment_qualities_kind")),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name=op.f("fk_equipment_qualities_rule_set_id_rule_sets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_qualities")),
        sa.UniqueConstraint(
            "rule_set_id", "kind", "name", name=op.f("uq_equipment_qualities_rule_set_id")
        ),
    )
    op.create_index(
        op.f("ix_equipment_qualities_rule_set_id"), "equipment_qualities", ["rule_set_id"]
    )
    op.create_table(
        "equipment_templates",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("grade", sa.String(), nullable=False),
        sa.Column(
            "qualities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("page", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        *record_columns(),
        sa.CheckConstraint(KIND_CHECK, name=op.f("ck_equipment_templates_kind")),
        sa.CheckConstraint(
            "grade in ('cheap', 'standard', 'special')", name=op.f("ck_equipment_templates_grade")
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"],
            ["rule_sets.id"],
            name=op.f("fk_equipment_templates_rule_set_id_rule_sets"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_equipment_templates_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_templates")),
        sa.UniqueConstraint(
            "rule_set_id",
            "troupe_id",
            "name",
            name=op.f("uq_equipment_templates_rule_set_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_equipment_templates_rule_set_id"), "equipment_templates", ["rule_set_id"]
    )
    op.create_index(op.f("ix_equipment_templates_troupe_id"), "equipment_templates", ["troupe_id"])


def downgrade() -> None:
    op.drop_table("equipment_templates")
    op.drop_table("equipment_qualities")
    op.drop_column("rule_sets", "equipment")
