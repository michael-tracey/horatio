"""Boons (issue #685): a troupe's Boons setting, off by default; each boon its debtor
owes its creditor, either side a character or a name only; and each boon's own log
of what was done to it (MET: VTM pp. 395-397).

Revision ID: 0172
Revises: 0170
Create Date: 2026-11-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0172"
down_revision: str | None = "0170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("boons", sa.Boolean(), server_default="false", nullable=False)
    )
    op.create_table(
        "boons",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("debtor_id", sa.Uuid(), nullable=True),
        sa.Column("debtor_name", sa.String(), server_default="", nullable=False),
        sa.Column("creditor_id", sa.Uuid(), nullable=True),
        sa.Column("creditor_name", sa.String(), server_default="", nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("made_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("conditions", sa.String(), server_default="", nullable=False),
        sa.Column("notify_on_trade", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("state", sa.String(), server_default="registered", nullable=False),
        sa.Column("settled_how", sa.String(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_note", sa.String(), server_default="", nullable=False),
        sa.Column("staff_note", sa.String(), server_default="", nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind in ('trivial', 'minor', 'major', 'blood', 'life')", name=op.f("ck_boons_kind")
        ),
        sa.CheckConstraint(
            "state in ('pending', 'registered', 'settled', 'void')", name=op.f("ck_boons_state")
        ),
        sa.CheckConstraint(
            "(debtor_id is null) <> (debtor_name = '')", name=op.f("ck_boons_debtor")
        ),
        sa.CheckConstraint(
            "(creditor_id is null) <> (creditor_name = '')", name=op.f("ck_boons_creditor")
        ),
        sa.CheckConstraint("debtor_id <> creditor_id", name=op.f("ck_boons_not_own_creditor")),
        sa.CheckConstraint(
            "settled_how is null or settled_how in ('called_in', 'forgiven', 'ignored')",
            name=op.f("ck_boons_settled_how"),
        ),
        sa.CheckConstraint(
            "(state = 'settled') = (settled_how is not null)", name=op.f("ck_boons_settled")
        ),
        sa.CheckConstraint(
            "(state in ('settled', 'void')) = (closed_at is not null)",
            name=op.f("ck_boons_closed"),
        ),
        sa.ForeignKeyConstraint(
            ["creditor_id"], ["characters.id"], name=op.f("fk_boons_creditor_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["debtor_id"], ["characters.id"], name=op.f("fk_boons_debtor_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"], ["users.id"], name=op.f("fk_boons_submitted_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_boons_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boons")),
    )
    op.create_index(op.f("ix_boons_creditor_id"), "boons", ["creditor_id"])
    op.create_index(op.f("ix_boons_debtor_id"), "boons", ["debtor_id"])
    op.create_index("ix_boons_troupe_id_state", "boons", ["troupe_id", "state"])
    op.create_table(
        "boon_events",
        sa.Column("boon_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column(
            "changes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("as_character_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind in ('registered', 'edited', 'traded', 'passed_on', 'settled', 'voided',"
            " 'reopened')",
            name=op.f("ck_boon_events_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_boon_events_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["as_character_id"],
            ["characters.id"],
            name=op.f("fk_boon_events_as_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["boon_id"],
            ["boons.id"],
            name=op.f("fk_boon_events_boon_id_boons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boon_events")),
    )
    op.create_index(op.f("ix_boon_events_boon_id"), "boon_events", ["boon_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_boon_events_boon_id"), table_name="boon_events")
    op.drop_table("boon_events")
    op.drop_index("ix_boons_troupe_id_state", table_name="boons")
    op.drop_index(op.f("ix_boons_debtor_id"), table_name="boons")
    op.drop_index(op.f("ix_boons_creditor_id"), table_name="boons")
    op.drop_table("boons")
    op.drop_column("troupes", "boons")
