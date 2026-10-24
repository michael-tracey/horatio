"""shared backgrounds: a background characters pool together, and its log

Revision ID: 0058
Revises: 0053
Create Date: 2026-10-23 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shared_backgrounds",
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("background", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), server_default="", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
            ["created_by"], ["users.id"], name=op.f("fk_shared_backgrounds_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_shared_backgrounds_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shared_backgrounds")),
        sa.UniqueConstraint("troupe_id", "name", name="uq_shared_backgrounds_name"),
    )
    op.create_index(
        op.f("ix_shared_backgrounds_troupe_id"), "shared_backgrounds", ["troupe_id"], unique=False
    )
    op.create_table(
        "shared_background_entries",
        sa.Column("background_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("happened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("dots", sa.Integer(), nullable=True),
        sa.Column("purpose", sa.String(), server_default="", nullable=False),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("logged_by", sa.Uuid(), nullable=True),
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
            "kind in ('contribution', 'withdrawal', 'use')",
            name=op.f("ck_shared_background_entries_kind"),
        ),
        sa.CheckConstraint(
            "(kind = 'use') = (dots is null)",
            name=op.f("ck_shared_background_entries_dots_by_kind"),
        ),
        sa.CheckConstraint(
            "dots is null or dots >= 1", name=op.f("ck_shared_background_entries_dots")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_shared_background_entries_character_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["logged_by"], ["users.id"], name=op.f("fk_shared_background_entries_logged_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["background_id"],
            ["shared_backgrounds.id"],
            name=op.f("fk_shared_background_entries_background_id_shared_backgrounds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shared_background_entries")),
    )
    op.create_index(
        op.f("ix_shared_background_entries_character_id"),
        "shared_background_entries",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_shared_background_entries_background_id"),
        "shared_background_entries",
        ["background_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_shared_background_entries_background_id"),
        table_name="shared_background_entries",
    )
    op.drop_index(
        op.f("ix_shared_background_entries_character_id"), table_name="shared_background_entries"
    )
    op.drop_table("shared_background_entries")
    op.drop_index(op.f("ix_shared_backgrounds_troupe_id"), table_name="shared_backgrounds")
    op.drop_table("shared_backgrounds")
