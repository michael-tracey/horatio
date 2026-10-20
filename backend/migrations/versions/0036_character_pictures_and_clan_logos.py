"""character pictures, visible notes and clan logos

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-19 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("picture_id", sa.Uuid(), nullable=True))
    op.add_column(
        "characters",
        sa.Column("picture_crop", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("characters", sa.Column("picture_by", sa.Uuid(), nullable=True))
    op.add_column(
        "characters", sa.Column("picture_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "characters",
        sa.Column("visible_note", sa.String(), server_default="", nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_characters_picture_by_users"), "characters", "users", ["picture_by"], ["id"]
    )
    op.create_table(
        "clan_logos",
        sa.Column("splat", sa.String(), nullable=False),
        sa.Column("clan", sa.String(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_clan_logos_uploaded_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clan_logos")),
        sa.UniqueConstraint("splat", "clan", name=op.f("uq_clan_logos_splat")),
    )


def downgrade() -> None:
    op.drop_table("clan_logos")
    op.drop_constraint(op.f("fk_characters_picture_by_users"), "characters", type_="foreignkey")
    op.drop_column("characters", "visible_note")
    op.drop_column("characters", "picture_at")
    op.drop_column("characters", "picture_by")
    op.drop_column("characters", "picture_crop")
    op.drop_column("characters", "picture_id")
