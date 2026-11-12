"""Blood bonds' player modes (issue #661): a drink a player reports for their own
character waits as a bond report, on the troupe's running staff (as a request in its
approvals queue, of the new kind `bond_drink`) or on the thrall's player, until it is
approved or confirmed.

Revision ID: 0171
Revises: 0170
Create Date: 2026-11-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0171"
down_revision: str | None = "0170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = (
    "'sheet_change', 'home_troupe_change', 'discipline', 'review', 'exception', 'diablerie',"
    " 'merit_flaw'"
)
APART = "'discipline', 'review', 'exception', 'merit_flaw'"


def one_pending(apart: str) -> None:
    op.drop_index("uq_approvals_one_pending", table_name="approvals")
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text(f"status = 'pending' and kind not in ({apart})"),
    )


def upgrade() -> None:
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint("kind", "approvals", f"kind in ({KINDS}, 'bond_drink')")
    one_pending(f"{APART}, 'bond_drink'")
    op.create_table(
        "bond_reports",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("thrall_id", sa.Uuid(), nullable=True),
        sa.Column("thrall_name", sa.String(), server_default="", nullable=False),
        sa.Column("regnant_id", sa.Uuid(), nullable=True),
        sa.Column("regnant_name", sa.String(), server_default="", nullable=False),
        sa.Column("reported_as", sa.String(), nullable=False),
        sa.Column("night", sa.Date(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("waiting_on", sa.String(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("reported_by", sa.Uuid(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("bond_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'withdrawn')",
            name=op.f("ck_bond_reports_status"),
        ),
        sa.CheckConstraint(
            "waiting_on in ('staff', 'thrall')", name=op.f("ck_bond_reports_waiting_on")
        ),
        sa.CheckConstraint(
            "reported_as in ('thrall', 'regnant')", name=op.f("ck_bond_reports_reported_as")
        ),
        sa.CheckConstraint("source in ('game', 'downtime')", name=op.f("ck_bond_reports_source")),
        sa.CheckConstraint(
            "(thrall_id is null) <> (thrall_name = '')", name=op.f("ck_bond_reports_thrall")
        ),
        sa.CheckConstraint(
            "(regnant_id is null) <> (regnant_name = '')", name=op.f("ck_bond_reports_regnant")
        ),
        sa.CheckConstraint(
            "(waiting_on = 'staff') = (approval_id is not null)",
            name=op.f("ck_bond_reports_approval"),
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
            name=op.f("fk_bond_reports_approval_id_approvals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bond_id"],
            ["blood_bonds.id"],
            name=op.f("fk_bond_reports_bond_id_blood_bonds"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_bond_reports_decided_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["regnant_id"], ["characters.id"], name=op.f("fk_bond_reports_regnant_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["reported_by"], ["users.id"], name=op.f("fk_bond_reports_reported_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["thrall_id"], ["characters.id"], name=op.f("fk_bond_reports_thrall_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_bond_reports_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bond_reports")),
        sa.UniqueConstraint("approval_id", name=op.f("uq_bond_reports_approval_id")),
    )
    op.create_index(op.f("ix_bond_reports_regnant_id"), "bond_reports", ["regnant_id"])
    op.create_index(op.f("ix_bond_reports_thrall_id"), "bond_reports", ["thrall_id"])
    op.create_index(op.f("ix_bond_reports_troupe_id"), "bond_reports", ["troupe_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_bond_reports_troupe_id"), table_name="bond_reports")
    op.drop_index(op.f("ix_bond_reports_thrall_id"), table_name="bond_reports")
    op.drop_index(op.f("ix_bond_reports_regnant_id"), table_name="bond_reports")
    op.drop_table("bond_reports")
    op.execute("delete from approvals where kind = 'bond_drink'")
    one_pending(APART)
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint("kind", "approvals", f"kind in ({KINDS})")
