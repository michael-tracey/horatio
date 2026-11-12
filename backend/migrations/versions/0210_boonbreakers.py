"""Boonbreakers (issue #717; MET: VTM pp. 397-398): a character whose boons the Harpy
made void, Disgraced while the mark stands; and the status a debtor loses for
ignoring a major, blood or life boon (p. 395).

Revision ID: 0210
Revises: 0209
Create Date: 2026-11-12 23:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0210"
down_revision: str | None = "0209"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boonbreakers",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("refused_boon_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("declared_by", sa.Uuid(), nullable=True),
        sa.Column("declared_as_id", sa.Uuid(), nullable=True),
        sa.Column(
            "voided", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("held_status_id", sa.Uuid(), nullable=True),
        sa.Column(
            "appeals", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lifted_by", sa.Uuid(), nullable=True),
        sa.Column("lifted_note", sa.String(), server_default="", nullable=False),
        sa.Column(
            "restored", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_boonbreakers_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_boonbreakers_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["refused_boon_id"],
            ["boons.id"],
            name=op.f("fk_boonbreakers_refused_boon_id_boons"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["declared_by"], ["users.id"], name=op.f("fk_boonbreakers_declared_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["declared_as_id"],
            ["characters.id"],
            name=op.f("fk_boonbreakers_declared_as_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["held_status_id"],
            ["held_statuses.id"],
            name=op.f("fk_boonbreakers_held_status_id_held_statuses"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lifted_by"], ["users.id"], name=op.f("fk_boonbreakers_lifted_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boonbreakers")),
    )
    op.create_index(op.f("ix_boonbreakers_troupe_id"), "boonbreakers", ["troupe_id"])
    op.create_index(op.f("ix_boonbreakers_character_id"), "boonbreakers", ["character_id"])
    op.create_index(
        "uq_boonbreakers_standing",
        "boonbreakers",
        ["troupe_id", "character_id"],
        unique=True,
        postgresql_where=sa.text("lifted_at is null"),
    )
    op.add_column("boons", sa.Column("status_loss", sa.String(), nullable=True))
    op.create_check_constraint(
        op.f("ck_boons_status_loss"),
        "boons",
        "status_loss is null or status_loss in ('due', 'taken', 'waived')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_boons_status_loss"), "boons", type_="check")
    op.drop_column("boons", "status_loss")
    op.drop_index("uq_boonbreakers_standing", table_name="boonbreakers")
    op.drop_index(op.f("ix_boonbreakers_character_id"), table_name="boonbreakers")
    op.drop_index(op.f("ix_boonbreakers_troupe_id"), table_name="boonbreakers")
    op.drop_table("boonbreakers")
