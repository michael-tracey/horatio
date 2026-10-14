"""home troupe holds the sheet

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-14 13:11:43.866497
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Sheet changes are no longer approved; any still waiting are withdrawn.
    op.execute(
        "update approvals set status = 'withdrawn', decided_at = now()"
        " where kind = 'sheet_change' and status = 'pending'"
    )
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint(
        "kind", "approvals", "kind in ('sheet_change', 'home_troupe_change', 'discipline')"
    )
    op.drop_index("uq_approvals_one_pending", table_name="approvals")
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' and kind <> 'discipline'"),
    )
    op.create_table(
        "discipline_purchases",
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("trait_definition_id", sa.Uuid(), nullable=False),
        sa.Column("detail", sa.String(), server_default="", nullable=False),
        sa.Column("from_rating", sa.Integer(), nullable=False),
        sa.Column("to_rating", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
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
            ["approval_id"],
            ["approvals.id"],
            name=op.f("fk_discipline_purchases_approval_id_approvals"),
        ),
        sa.ForeignKeyConstraint(
            ["trait_definition_id"],
            ["trait_definitions.id"],
            name=op.f("fk_discipline_purchases_trait_definition_id_trait_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discipline_purchases")),
        sa.UniqueConstraint("approval_id", name=op.f("uq_discipline_purchases_approval_id")),
    )
    op.drop_column("troupe_memberships", "standing_note")
    op.drop_column("troupe_memberships", "standing")


def downgrade() -> None:
    op.add_column(
        "troupe_memberships",
        sa.Column(
            "standing",
            sa.VARCHAR(),
            server_default=sa.text("'draft'::character varying"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.add_column(
        "troupe_memberships",
        sa.Column(
            "standing_note",
            sa.VARCHAR(),
            server_default=sa.text("''::character varying"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "standing", "troupe_memberships", "standing in ('draft', 'approved')"
    )
    op.execute(
        "update troupe_memberships set standing = 'approved' where approved_version_id is not null"
    )
    op.drop_table("discipline_purchases")
    op.execute("delete from approvals where kind = 'discipline'")
    op.drop_index("uq_approvals_one_pending", table_name="approvals")
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_constraint("kind", "approvals", type_="check")
    op.create_check_constraint(
        "kind", "approvals", "kind in ('sheet_change', 'home_troupe_change')"
    )
