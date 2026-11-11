"""Blood bonds (issue #660): a troupe's Blood bonds setting, off by default; each bond,
a thrall's to a regnant, either a character or a name only; and each bond's log of
drinks, from which its level is worked out (MET: VTM pp. 295-296).

Revision ID: 0163
Revises: 0162
Create Date: 2026-11-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0163"
down_revision: str | None = "0162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("blood_bonds", sa.String(), server_default="off", nullable=False)
    )
    op.create_check_constraint(
        "blood_bonds",
        "troupes",
        "blood_bonds in ('off', 'staff', 'players_report', 'players_manage')",
    )
    op.create_table(
        "blood_bonds",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("thrall_id", sa.Uuid(), nullable=True),
        sa.Column("thrall_name", sa.String(), server_default="", nullable=False),
        sa.Column("regnant_id", sa.Uuid(), nullable=True),
        sa.Column("regnant_name", sa.String(), server_default="", nullable=False),
        sa.Column("status", sa.String(), server_default="active", nullable=False),
        sa.Column("known_to_regnant", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.Uuid(), nullable=True),
        sa.Column("ended_reason", sa.String(), server_default="", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status in ('active', 'fading', 'ended', 'broken')",
            name=op.f("ck_blood_bonds_status"),
        ),
        sa.CheckConstraint(
            "(thrall_id is null) <> (thrall_name = '')", name=op.f("ck_blood_bonds_thrall")
        ),
        sa.CheckConstraint(
            "(regnant_id is null) <> (regnant_name = '')", name=op.f("ck_blood_bonds_regnant")
        ),
        sa.CheckConstraint("thrall_id <> regnant_id", name=op.f("ck_blood_bonds_not_own_regnant")),
        sa.CheckConstraint(
            "(status in ('ended', 'broken')) = (ended_at is not null)",
            name=op.f("ck_blood_bonds_ended"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_blood_bonds_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["ended_by"], ["users.id"], name=op.f("fk_blood_bonds_ended_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["regnant_id"], ["characters.id"], name=op.f("fk_blood_bonds_regnant_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["thrall_id"], ["characters.id"], name=op.f("fk_blood_bonds_thrall_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_blood_bonds_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blood_bonds")),
    )
    op.create_index(op.f("ix_blood_bonds_regnant_id"), "blood_bonds", ["regnant_id"])
    op.create_index(op.f("ix_blood_bonds_thrall_id"), "blood_bonds", ["thrall_id"])
    op.create_index(op.f("ix_blood_bonds_troupe_id"), "blood_bonds", ["troupe_id"])
    op.create_table(
        "bond_entries",
        sa.Column("bond_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("night", sa.Date(), nullable=False),
        sa.Column("source", sa.String(), server_default="staff", nullable=False),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind in ('drink', 'entered')", name=op.f("ck_bond_entries_kind")),
        sa.CheckConstraint(
            "source in ('game', 'downtime', 'staff')", name=op.f("ck_bond_entries_source")
        ),
        sa.CheckConstraint(
            "(kind = 'entered') = (level is not null)", name=op.f("ck_bond_entries_entered_level")
        ),
        sa.CheckConstraint("level between 1 and 3", name=op.f("ck_bond_entries_level")),
        sa.ForeignKeyConstraint(
            ["bond_id"],
            ["blood_bonds.id"],
            name=op.f("fk_bond_entries_bond_id_blood_bonds"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_bond_entries_recorded_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bond_entries")),
    )
    op.create_index(op.f("ix_bond_entries_bond_id"), "bond_entries", ["bond_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bond_entries_bond_id"), table_name="bond_entries")
    op.drop_table("bond_entries")
    op.drop_index(op.f("ix_blood_bonds_troupe_id"), table_name="blood_bonds")
    op.drop_index(op.f("ix_blood_bonds_thrall_id"), table_name="blood_bonds")
    op.drop_index(op.f("ix_blood_bonds_regnant_id"), table_name="blood_bonds")
    op.drop_table("blood_bonds")
    op.drop_constraint("blood_bonds", "troupes", type_="check")
    op.drop_column("troupes", "blood_bonds")
