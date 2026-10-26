"""ghouls: a character's domitor, and the splats a troupe takes

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-26 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0069"
down_revision: str | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("domitor_id", sa.Uuid(), nullable=True))
    op.add_column(
        "characters", sa.Column("domitor_name", sa.String(), server_default="", nullable=False)
    )
    op.create_foreign_key(
        op.f("fk_characters_domitor_id_characters"),
        "characters",
        "characters",
        ["domitor_id"],
        ["id"],
    )
    # Every troupe so far takes vampires only.
    op.add_column(
        "troupes",
        sa.Column(
            "allowed_splats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='["vampire"]',
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("troupes", "allowed_splats")
    op.drop_constraint(
        op.f("fk_characters_domitor_id_characters"), "characters", type_="foreignkey"
    )
    op.drop_column("characters", "domitor_name")
    op.drop_column("characters", "domitor_id")
