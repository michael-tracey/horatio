"""downtime keywords: a troupe's own list, as house rules; Computer's Watch is now
Observe (issue #509)

Revision ID: 0151
Revises: 0150
Create Date: 2026-11-07 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0151"
down_revision: str | None = "0150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "downtime_keywords",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("explanation", sa.String(), server_default="", nullable=False),
        sa.Column(
            "fields", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "action_kinds",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("computers_only", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("science", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("cost", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "required_for",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("step", sa.Integer(), server_default="5", nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("cost >= 0", name=op.f("ck_downtime_keywords_cost")),
        sa.CheckConstraint("step between 1 and 6", name=op.f("ck_downtime_keywords_step")),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_downtime_keywords_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_downtime_keywords")),
        sa.UniqueConstraint("troupe_id", "key", name=op.f("uq_downtime_keywords_troupe_id")),
    )
    op.create_index(op.f("ix_downtime_keywords_troupe_id"), "downtime_keywords", ["troupe_id"])
    # Computer's second use is called Observe, as the troupes' primers call it.
    op.execute(
        "update answers set structured = jsonb_set(structured, '{counter}', '\"observe\"')"
        " where structured->>'counter' = 'watch'"
    )


def downgrade() -> None:
    op.execute(
        "update answers set structured = jsonb_set(structured, '{counter}', '\"watch\"')"
        " where structured->>'counter' = 'observe'"
    )
    op.drop_index(op.f("ix_downtime_keywords_troupe_id"), table_name="downtime_keywords")
    op.drop_table("downtime_keywords")
