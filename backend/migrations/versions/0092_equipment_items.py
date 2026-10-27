"""equipment items: what a troupe gives its home characters, with each item's history,
and the rest of an item on a troupe's own templates

Revision ID: 0092
Revises: 0086
Create Date: 2026-10-27 22:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0092"
down_revision: str | None = "0086"
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


def jsonb(name: str, default: str) -> sa.Column[Any]:
    return sa.Column(
        name, postgresql.JSONB(astext_type=sa.Text()), server_default=default, nullable=False
    )


def upgrade() -> None:
    op.add_column(
        "equipment_templates",
        sa.Column("crafted", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("equipment_templates", jsonb("effects", "[]"))
    op.add_column(
        "equipment_templates",
        sa.Column("description", sa.String(), server_default="", nullable=False),
    )

    op.create_table(
        "equipment_items",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("given_by", sa.Uuid(), nullable=True),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("grade", sa.String(), nullable=False),
        jsonb("qualities", "[]"),
        sa.Column("crafted", sa.Boolean(), server_default="false", nullable=False),
        jsonb("effects", "[]"),
        sa.Column("description", sa.String(), server_default="", nullable=False),
        sa.Column("staff_note", sa.String(), server_default="", nullable=False),
        sa.Column("special_troupe_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), server_default="held", nullable=False),
        *record_columns(),
        sa.CheckConstraint(KIND_CHECK, name=op.f("ck_equipment_items_kind")),
        sa.CheckConstraint(
            "grade in ('cheap', 'standard', 'special')", name=op.f("ck_equipment_items_grade")
        ),
        sa.CheckConstraint(
            "status in ('held', 'taken_back', 'discarded')", name=op.f("ck_equipment_items_status")
        ),
        sa.CheckConstraint(
            "(grade = 'special') = (special_troupe_id is not null)",
            name=op.f("ck_equipment_items_special_troupe"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_equipment_items_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_equipment_items_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["given_by"], ["users.id"], name=op.f("fk_equipment_items_given_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["special_troupe_id"],
            ["troupes.id"],
            name=op.f("fk_equipment_items_special_troupe_id_troupes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_items")),
    )
    op.create_index(op.f("ix_equipment_items_character_id"), "equipment_items", ["character_id"])
    op.create_index(op.f("ix_equipment_items_troupe_id"), "equipment_items", ["troupe_id"])
    op.create_index(op.f("ix_equipment_items_status"), "equipment_items", ["status"])

    op.create_table(
        "equipment_events",
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("from_character_id", sa.Uuid(), nullable=True),
        sa.Column("to_character_id", sa.Uuid(), nullable=True),
        sa.Column("from_name", sa.String(), server_default="", nullable=False),
        sa.Column("to_name", sa.String(), server_default="", nullable=False),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        jsonb("changes", "{}"),
        *record_columns(),
        sa.CheckConstraint(
            "action in ('given', 'changed', 'taken_back', 'passed', 'discarded', 'restored')",
            name=op.f("ck_equipment_events_action"),
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["equipment_items.id"],
            name=op.f("fk_equipment_events_item_id_equipment_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_equipment_events_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_equipment_events_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["from_character_id"],
            ["characters.id"],
            name=op.f("fk_equipment_events_from_character_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["to_character_id"],
            ["characters.id"],
            name=op.f("fk_equipment_events_to_character_id_characters"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_events")),
    )
    op.create_index(op.f("ix_equipment_events_item_id"), "equipment_events", ["item_id"])


def downgrade() -> None:
    op.drop_table("equipment_events")
    op.drop_table("equipment_items")
    op.drop_column("equipment_templates", "description")
    op.drop_column("equipment_templates", "effects")
    op.drop_column("equipment_templates", "crafted")
