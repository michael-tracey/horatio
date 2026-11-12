"""Reviewing boons (issue #687): whether boons players report wait for review, the
flags raised on boons for review, and the boon log's new kinds of entry.

Revision ID: 0194
Revises: 0191
Create Date: 2026-11-12 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0194"
down_revision: str | None = "0191"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = (
    "kind in ('registered', 'edited', 'traded', 'passed_on', 'settled', 'voided', 'reopened')"
)
NEW_KINDS = (
    "kind in ('registered', 'edited', 'traded', 'passed_on', 'settled', 'voided',"
    " 'reopened', 'submitted', 'accepted', 'rejected', 'flagged', 'flag_cleared', 'linked')"
)


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("boon_review", sa.Boolean(), server_default="false", nullable=False),
    )
    op.drop_constraint(op.f("ck_boon_events_kind"), "boon_events", type_="check")
    op.create_check_constraint(op.f("ck_boon_events_kind"), "boon_events", NEW_KINDS)
    op.create_table(
        "boon_flags",
        sa.Column("boon_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=True),
        sa.Column("detail", sa.String(), server_default="", nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("other_boon_id", sa.Uuid(), nullable=True),
        sa.Column("raised_by", sa.Uuid(), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_by", sa.Uuid(), nullable=True),
        sa.Column("cleared_note", sa.String(), server_default="", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind in ('unmatched', 'duplicate', 'hand')", name=op.f("ck_boon_flags_kind")
        ),
        sa.CheckConstraint(
            "side is null or side in ('debtor', 'creditor')", name=op.f("ck_boon_flags_side")
        ),
        sa.CheckConstraint(
            "(kind = 'unmatched') = (side is not null)", name=op.f("ck_boon_flags_sided")
        ),
        sa.ForeignKeyConstraint(
            ["boon_id"],
            ["boons.id"],
            name=op.f("fk_boon_flags_boon_id_boons"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["other_boon_id"],
            ["boons.id"],
            name=op.f("fk_boon_flags_other_boon_id_boons"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["raised_by"], ["users.id"], name=op.f("fk_boon_flags_raised_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["cleared_by"], ["users.id"], name=op.f("fk_boon_flags_cleared_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boon_flags")),
    )
    op.create_index(op.f("ix_boon_flags_boon_id"), "boon_flags", ["boon_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_boon_flags_boon_id"), table_name="boon_flags")
    op.drop_table("boon_flags")
    op.execute(
        "delete from boon_events where kind in ('submitted', 'accepted', 'rejected', 'flagged',"
        " 'flag_cleared', 'linked')"
    )
    op.drop_constraint(op.f("ck_boon_events_kind"), "boon_events", type_="check")
    op.create_check_constraint(op.f("ck_boon_events_kind"), "boon_events", OLD_KINDS)
    op.drop_column("troupes", "boon_review")
