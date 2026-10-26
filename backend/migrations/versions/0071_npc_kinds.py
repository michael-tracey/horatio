"""npc kinds: what each NPC is and its form, and what a Stock NPC has

Revision ID: 0071
Revises: 0069
Create Date: 2026-10-26 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0071"
down_revision: str | None = "0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("npc_kind", sa.String(), nullable=True))
    op.add_column("characters", sa.Column("npc_form", sa.String(), nullable=True))
    op.add_column(
        "characters",
        sa.Column("npc_custom_kind", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Every NPC so far has a full sheet; a ghoul NPC is a ghoul, the rest vampires.
    op.execute(
        "update characters set npc_form = 'sheeted',"
        " npc_kind = case when splat = 'ghoul' then 'ghoul' else 'vampire' end"
        " where kind = 'npc'"
    )
    op.create_check_constraint(
        op.f("ck_characters_npc_has_kind"),
        "characters",
        "(kind = 'npc') = (npc_kind is not null and npc_form is not null)",
    )
    op.create_check_constraint(
        op.f("ck_characters_npc_form"), "characters", "npc_form in ('sheeted', 'stock')"
    )
    op.create_table(
        "stock_npcs",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column(
            "specializations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("notes", sa.String(), server_default="", nullable=False),
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
        sa.CheckConstraint("rating >= 1", name=op.f("ck_stock_npcs_rating")),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_stock_npcs_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_npcs")),
        sa.UniqueConstraint("character_id", name=op.f("uq_stock_npcs_character_id")),
    )


def downgrade() -> None:
    op.drop_table("stock_npcs")
    op.drop_constraint(op.f("ck_characters_npc_form"), "characters", type_="check")
    op.drop_constraint(op.f("ck_characters_npc_has_kind"), "characters", type_="check")
    op.drop_column("characters", "npc_custom_kind")
    op.drop_column("characters", "npc_form")
    op.drop_column("characters", "npc_kind")
