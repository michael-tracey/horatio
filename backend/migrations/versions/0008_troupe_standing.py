"""troupe standing

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14 08:38:28.767873
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Memberships gain a standing and their own approved sheet.
    op.add_column(
        "troupe_memberships",
        sa.Column("standing", sa.String(), server_default="draft", nullable=False),
    )
    op.add_column(
        "troupe_memberships",
        sa.Column("standing_note", sa.String(), server_default="", nullable=False),
    )
    op.add_column("troupe_memberships", sa.Column("approved_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_troupe_memberships_approved_version_id_sheet_versions"),
        "troupe_memberships",
        "sheet_versions",
        ["approved_version_id"],
        ["id"],
    )

    # Sheet versions belong to the troupe that approved them: until now, always
    # the home troupe.
    op.add_column("sheet_versions", sa.Column("troupe_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        update sheet_versions v set troupe_id = c.home_troupe_id
        from characters c where v.character_id = c.id
        """
    )
    op.execute("delete from sheet_versions where troupe_id is null")
    op.alter_column("sheet_versions", "troupe_id", nullable=False)
    op.drop_constraint(op.f("uq_sheet_versions_character_id"), "sheet_versions", type_="unique")
    op.create_unique_constraint(
        op.f("uq_sheet_versions_character_id"),
        "sheet_versions",
        ["character_id", "troupe_id", "number"],
    )
    op.create_index(op.f("ix_sheet_versions_troupe_id"), "sheet_versions", ["troupe_id"])
    op.create_foreign_key(
        op.f("fk_sheet_versions_troupe_id_troupes"),
        "sheet_versions",
        "troupes",
        ["troupe_id"],
        ["id"],
    )

    # A character approved before was approved by its home troupe.
    op.execute(
        """
        update troupe_memberships m
        set standing = 'approved', approved_version_id = c.approved_version_id
        from characters c
        where m.character_id = c.id and m.troupe_id = c.home_troupe_id
          and m.left_at is null and c.approved_version_id is not null
        """
    )
    op.drop_constraint(
        op.f("fk_characters_approved_version_id_sheet_versions"), "characters", type_="foreignkey"
    )
    op.drop_column("characters", "approved_version_id")

    # Characters are active or retired; draft is now each troupe's call.
    op.drop_constraint(op.f("ck_characters_status"), "characters", type_="check")
    op.execute("update characters set status = 'active' where status = 'draft'")
    op.create_check_constraint(
        op.f("ck_characters_status"), "characters", "status in ('active', 'retired')"
    )
    op.alter_column("characters", "status", server_default="active")
    op.create_check_constraint(
        op.f("ck_troupe_memberships_standing"),
        "troupe_memberships",
        "standing in ('draft', 'approved')",
    )

    # One waiting request of each kind per troupe, not per character.
    op.drop_index(
        op.f("uq_approvals_one_pending"),
        table_name="approvals",
        postgresql_where="((status)::text = 'pending'::text)",
    )
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "troupe_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.add_column("creation_rules", sa.Column("restriction", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("creation_rules", "restriction")
    op.drop_index(
        "uq_approvals_one_pending",
        table_name="approvals",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        op.f("uq_approvals_one_pending"),
        "approvals",
        ["character_id", "kind"],
        unique=True,
        postgresql_where="((status)::text = 'pending'::text)",
    )
    op.drop_constraint(op.f("ck_troupe_memberships_standing"), "troupe_memberships", type_="check")
    op.drop_constraint(op.f("ck_characters_status"), "characters", type_="check")
    op.create_check_constraint(
        op.f("ck_characters_status"), "characters", "status in ('draft', 'active', 'retired')"
    )
    op.alter_column("characters", "status", server_default="draft")
    op.add_column("characters", sa.Column("approved_version_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        update characters c set approved_version_id = m.approved_version_id
        from troupe_memberships m
        where m.character_id = c.id and m.troupe_id = c.home_troupe_id and m.left_at is null
        """
    )
    op.execute(
        "update characters set status = 'draft' where approved_version_id is null and status = 'active'"
    )
    op.create_foreign_key(
        op.f("fk_characters_approved_version_id_sheet_versions"),
        "characters",
        "sheet_versions",
        ["approved_version_id"],
        ["id"],
    )
    op.drop_constraint(
        op.f("fk_troupe_memberships_approved_version_id_sheet_versions"),
        "troupe_memberships",
        type_="foreignkey",
    )
    op.drop_column("troupe_memberships", "approved_version_id")
    op.drop_column("troupe_memberships", "standing_note")
    op.drop_column("troupe_memberships", "standing")
    op.drop_constraint(
        op.f("fk_sheet_versions_troupe_id_troupes"), "sheet_versions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_sheet_versions_troupe_id"), table_name="sheet_versions")
    op.drop_constraint(op.f("uq_sheet_versions_character_id"), "sheet_versions", type_="unique")
    op.create_unique_constraint(
        op.f("uq_sheet_versions_character_id"), "sheet_versions", ["character_id", "number"]
    )
    op.drop_column("sheet_versions", "troupe_id")
