"""Audits of a character's boons (issue #690): each one as the ledger held it then,
who made it and as whom, and who it was given to.

Revision ID: 0214
Revises: 0209
Create Date: 2026-11-13 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0214"
down_revision: str | None = "0209"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boon_audits",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column(
            "contents",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("made_by", sa.Uuid(), nullable=True),
        sa.Column("as_character_id", sa.Uuid(), nullable=True),
        sa.Column("given_to_id", sa.Uuid(), nullable=True),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_boon_audits_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["characters.id"],
            name=op.f("fk_boon_audits_subject_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["made_by"], ["users.id"], name=op.f("fk_boon_audits_made_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["as_character_id"],
            ["characters.id"],
            name=op.f("fk_boon_audits_as_character_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["given_to_id"],
            ["characters.id"],
            name=op.f("fk_boon_audits_given_to_id_characters"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boon_audits")),
    )
    op.create_index(op.f("ix_boon_audits_troupe_id"), "boon_audits", ["troupe_id"])
    op.create_index(op.f("ix_boon_audits_subject_id"), "boon_audits", ["subject_id"])
    op.create_index(op.f("ix_boon_audits_given_to_id"), "boon_audits", ["given_to_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_boon_audits_given_to_id"), table_name="boon_audits")
    op.drop_index(op.f("ix_boon_audits_subject_id"), table_name="boon_audits")
    op.drop_index(op.f("ix_boon_audits_troupe_id"), table_name="boon_audits")
    op.drop_table("boon_audits")
