"""approvals audit starting xp

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14 00:29:55.376612
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("player_note", sa.String(), server_default="", nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_note", sa.String(), server_default="", nullable=False),
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
            "kind in ('sheet_change', 'home_troupe_change')", name=op.f("ck_approvals_kind")
        ),
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'declined', 'withdrawn')",
            name=op.f("ck_approvals_status"),
        ),
        sa.ForeignKeyConstraint(
            ["character_id"], ["characters.id"], name=op.f("fk_approvals_character_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_approvals_decided_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_approvals_requested_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_approvals_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
    )
    op.create_index(op.f("ix_approvals_character_id"), "approvals", ["character_id"], unique=False)
    op.create_index(op.f("ix_approvals_troupe_id"), "approvals", ["troupe_id"], unique=False)
    op.create_index(
        "uq_approvals_one_pending",
        "approvals",
        ["character_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "audit_events",
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column(
            "data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
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
            ["actor_id"], ["users.id"], name=op.f("fk_audit_events_actor_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_audit_events_character_id_characters"),
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_audit_events_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"], unique=False)
    op.create_index(
        op.f("ix_audit_events_character_id"), "audit_events", ["character_id"], unique=False
    )
    op.create_index(op.f("ix_audit_events_troupe_id"), "audit_events", ["troupe_id"], unique=False)
    op.add_column(
        "rule_sets", sa.Column("starting_xp", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("rule_sets", "starting_xp")
    op.drop_index(op.f("ix_audit_events_troupe_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_character_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(
        "uq_approvals_one_pending",
        table_name="approvals",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(op.f("ix_approvals_troupe_id"), table_name="approvals")
    op.drop_index(op.f("ix_approvals_character_id"), table_name="approvals")
    op.drop_table("approvals")
