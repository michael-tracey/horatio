"""troupe profiles: portrait, banner, links, schedule, venue, setting, public or not

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("public", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("troupes", sa.Column("portrait_id", sa.Uuid(), nullable=True))
    op.add_column(
        "troupes",
        sa.Column("portrait_crop", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("troupes", sa.Column("banner_id", sa.Uuid(), nullable=True))
    op.add_column(
        "troupes",
        sa.Column(
            "profile",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column("troupes", sa.Column("contact_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_troupes_contact_id_users"), "troupes", "users", ["contact_id"], ["id"]
    )
    op.create_table(
        "scheduled_games",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_scheduled_games_ends_after_start")),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_scheduled_games_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_games")),
    )
    op.create_index(
        op.f("ix_scheduled_games_troupe_id"), "scheduled_games", ["troupe_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scheduled_games_troupe_id"), table_name="scheduled_games")
    op.drop_table("scheduled_games")
    op.drop_constraint(op.f("fk_troupes_contact_id_users"), "troupes", type_="foreignkey")
    op.drop_column("troupes", "contact_id")
    op.drop_column("troupes", "profile")
    op.drop_column("troupes", "banner_id")
    op.drop_column("troupes", "portrait_crop")
    op.drop_column("troupes", "portrait_id")
    op.drop_column("troupes", "public")
