"""locations: a troupe's Stock Locations and havens on its list, the location
qualities it adds, and its house options for them (horatio.locations)

Revision ID: 0111
Revises: 0108
Create Date: 2026-10-30 16:32:49.881628
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0111"
down_revision: str | None = "0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "troupe_location_qualities",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), server_default="standard", nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), server_default="", nullable=False),
        sa.Column("repeatable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "suggested",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "kind in ('standard', 'iconic', 'supernatural', 'elysium')",
            name=op.f("ck_troupe_location_qualities_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"],
            ["troupes.id"],
            name=op.f("fk_troupe_location_qualities_troupe_id_troupes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_troupe_location_qualities")),
        sa.UniqueConstraint("troupe_id", "name", name="uq_troupe_location_qualities_name"),
    )
    op.create_index(
        op.f("ix_troupe_location_qualities_troupe_id"),
        "troupe_location_qualities",
        ["troupe_id"],
        unique=False,
    )
    op.create_table(
        "locations",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column(
            "qualities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "negatives",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("control", sa.String(), server_default="none", nullable=False),
        sa.Column("controller_id", sa.Uuid(), nullable=True),
        sa.Column("controller_name", sa.String(), server_default="", nullable=False),
        sa.Column("joint_id", sa.Uuid(), nullable=True),
        sa.Column("joint_name", sa.String(), server_default="", nullable=False),
        sa.Column("heir_id", sa.Uuid(), nullable=True),
        sa.Column("heir_name", sa.String(), server_default="", nullable=False),
        sa.Column("influence_type", sa.String(), nullable=True),
        sa.Column("influence_area", sa.String(), server_default="", nullable=False),
        sa.Column("address", sa.String(), server_default="", nullable=False),
        sa.Column("web_address", sa.String(), server_default="", nullable=False),
        sa.Column("map_link", sa.String(), server_default="", nullable=False),
        sa.Column("feeding_block", sa.String(), server_default="", nullable=False),
        sa.Column("locked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("haven_of_id", sa.Uuid(), nullable=True),
        sa.Column(
            "haven_advantages",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("elysium_since", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(), server_default="", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
            "(control = 'character') = (controller_id is not null)",
            name=op.f("ck_locations_controller"),
        ),
        sa.CheckConstraint(
            "(control = 'named') = (controller_name <> '')",
            name=op.f("ck_locations_controller_name"),
        ),
        sa.CheckConstraint(
            "(kind = 'haven') <= (haven_of_id is not null)",
            name=op.f("ck_locations_haven_has_owner"),
        ),
        sa.CheckConstraint(
            "control in ('character', 'named', 'none', 'uncontrollable')",
            name=op.f("ck_locations_control"),
        ),
        sa.CheckConstraint(
            "influence_type is null or influence_type in ('elite', 'underworld')",
            name=op.f("ck_locations_influence_type"),
        ),
        sa.CheckConstraint(
            "kind in ('standard', 'prestige', 'iconic', 'haven')", name=op.f("ck_locations_kind")
        ),
        sa.CheckConstraint(
            "parent_id is null or parent_id <> id", name=op.f("ck_locations_not_own_parent")
        ),
        sa.CheckConstraint("rating between 1 and 5", name=op.f("ck_locations_rating")),
        sa.ForeignKeyConstraint(
            ["controller_id"], ["characters.id"], name=op.f("fk_locations_controller_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_locations_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["haven_of_id"], ["characters.id"], name=op.f("fk_locations_haven_of_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["heir_id"], ["characters.id"], name=op.f("fk_locations_heir_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["joint_id"], ["characters.id"], name=op.f("fk_locations_joint_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["locations.id"],
            name=op.f("fk_locations_parent_id_locations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_locations_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint("troupe_id", "name", name="uq_locations_name"),
    )
    op.create_index(
        op.f("ix_locations_controller_id"), "locations", ["controller_id"], unique=False
    )
    op.create_index(op.f("ix_locations_haven_of_id"), "locations", ["haven_of_id"], unique=False)
    op.create_index(op.f("ix_locations_joint_id"), "locations", ["joint_id"], unique=False)
    op.create_index(op.f("ix_locations_parent_id"), "locations", ["parent_id"], unique=False)
    op.create_index(op.f("ix_locations_troupe_id"), "locations", ["troupe_id"], unique=False)
    op.add_column(
        "troupes",
        sa.Column(
            "location_options_off",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "troupes", sa.Column("location_limit", sa.String(), server_default="refuse", nullable=False)
    )
    op.create_check_constraint(
        op.f("ck_troupes_location_limit"), "troupes", "location_limit in ('refuse', 'note')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_troupes_location_limit"), "troupes", type_="check")
    op.drop_column("troupes", "location_limit")
    op.drop_column("troupes", "location_options_off")
    op.drop_index(op.f("ix_locations_troupe_id"), table_name="locations")
    op.drop_index(op.f("ix_locations_parent_id"), table_name="locations")
    op.drop_index(op.f("ix_locations_joint_id"), table_name="locations")
    op.drop_index(op.f("ix_locations_haven_of_id"), table_name="locations")
    op.drop_index(op.f("ix_locations_controller_id"), table_name="locations")
    op.drop_table("locations")
    op.drop_index(
        op.f("ix_troupe_location_qualities_troupe_id"), table_name="troupe_location_qualities"
    )
    op.drop_table("troupe_location_qualities")
