"""troupe xp floor and ceiling, self-entered xp, and topping up or capping on joining

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-20 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'award', 'purchase', 'settlement', 'fee', 'correction'"


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("starting_xp", sa.Integer(), server_default="30", nullable=False)
    )
    op.create_table(
        "xp_range_entries",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("floor_change", sa.Integer(), nullable=False),
        sa.Column("ceiling_change", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("entered_on", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("entered_by", sa.Uuid(), nullable=True),
        sa.Column("cycle_id", sa.Uuid(), nullable=True),
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
            "kind in ('game', 'downtime', 'set')", name=op.f("ck_xp_range_entries_kind")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_xp_range_entries_troupe_id_troupes")
        ),
        sa.ForeignKeyConstraint(
            ["entered_by"], ["users.id"], name=op.f("fk_xp_range_entries_entered_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["downtime_cycles.id"],
            name=op.f("fk_xp_range_entries_cycle_id_downtime_cycles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_xp_range_entries")),
    )
    op.create_index(
        op.f("ix_xp_range_entries_troupe_id"), "xp_range_entries", ["troupe_id"], unique=False
    )
    # Cycles already closed count toward the ceiling, as closing one does from now on.
    op.execute(
        "insert into xp_range_entries"
        " (troupe_id, kind, floor_change, ceiling_change, reason, entered_on, cycle_id)"
        " select troupe_id, 'downtime', 0, completion_xp, 'Downtime: ' || name,"
        " coalesce(closed_at, now())::date, id"
        " from downtime_cycles"
        " where status in ('closed', 'complete') and completion_xp > 0"
    )

    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS}, 'self_entered', 'cap')")

    op.add_column(
        "home_troupe_changes",
        sa.Column("top_up", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "home_troupe_changes",
        sa.Column("xp_review", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("home_troupe_changes", "xp_review")
    op.drop_column("home_troupe_changes", "top_up")
    # Corrections of self-entered XP go with it.
    op.execute(
        "delete from xp_entries where corrects_id in"
        " (select id from xp_entries where kind = 'self_entered')"
    )
    op.execute("delete from xp_entries where kind in ('self_entered', 'cap')")
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS})")
    op.drop_index(op.f("ix_xp_range_entries_troupe_id"), table_name="xp_range_entries")
    op.drop_table("xp_range_entries")
    op.drop_column("troupes", "starting_xp")
