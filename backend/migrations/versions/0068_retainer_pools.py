"""retainer pools and identities: each Retainer's specialties and whether it is a
ghoul, and the group each Alternate Identity is Accepted by

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-26 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0068"
down_revision: str | None = "0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "retainers", sa.Column("ghoul", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "retainers",
        sa.Column(
            "specialties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "retainers", sa.Column("discipline", sa.String(), server_default="", nullable=False)
    )
    op.create_table(
        "alternate_identities",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("accepted_by", sa.String(), server_default="", nullable=False),
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
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_alternate_identities_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alternate_identities")),
        sa.UniqueConstraint(
            "character_id", "name", name=op.f("uq_alternate_identities_character_id")
        ),
    )
    op.create_index(
        op.f("ix_alternate_identities_character_id"),
        "alternate_identities",
        ["character_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_alternate_identities_character_id"), table_name="alternate_identities")
    op.drop_table("alternate_identities")
    op.drop_column("retainers", "discipline")
    op.drop_column("retainers", "specialties")
    op.drop_column("retainers", "ghoul")
