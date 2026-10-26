"""a ghoul's Embrace, and XP debt: a debt line in the XP history, and the record of each Embrace

Revision ID: 0079
Revises: 0074
Create Date: 2026-10-26 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0079"
down_revision: str | None = "0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'award', 'purchase', 'settlement', 'fee', 'correction', 'self_entered', 'cap', 'reprice'"


def upgrade() -> None:
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS}, 'debt')")
    op.create_table(
        "embraces",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.String(), nullable=False),
        sa.Column("embraced_on", sa.Date(), nullable=False),
        sa.Column("sire_id", sa.Uuid(), nullable=True),
        sa.Column("sire_name", sa.String(), server_default="", nullable=False),
        sa.Column("sire_clan", sa.String(), server_default="", nullable=False),
        sa.Column("sire_generation", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(), server_default="", nullable=False),
        sa.Column("buy_back_into_debt", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "outcome",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("recorded_by", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("result in ('vampire', 'died')", name=op.f("ck_embraces_result")),
        sa.ForeignKeyConstraint(
            ["character_id"], ["characters.id"], name=op.f("fk_embraces_character_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"], ["users.id"], name=op.f("fk_embraces_recorded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["sire_id"], ["characters.id"], name=op.f("fk_embraces_sire_id_characters")
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_embraces_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embraces")),
    )
    op.create_index(op.f("ix_embraces_character_id"), "embraces", ["character_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_embraces_character_id"), table_name="embraces")
    op.drop_table("embraces")
    op.execute("delete from xp_entries where kind = 'debt'")
    op.drop_constraint("kind", "xp_entries", type_="check")
    op.create_check_constraint("kind", "xp_entries", f"kind in ({KINDS})")
