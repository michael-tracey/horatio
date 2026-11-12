"""sire lines: each character's sire, kept on the character, and a troupe's choice
to show its sire lines to its players (issue #707)

A vampire's sire was kept only on an Embrace run in play. It is now on the
character too, for every vampire, and the Embraces already run fill it in.

Revision ID: 0184
Revises: 0181
Create Date: 2026-11-12 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0184"
down_revision: str | None = "0181"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The sire: a character in Horatio, or one known by name and clan only. Kept by
    # name if the linked one is deleted (horatio.deletion).
    op.add_column(
        "characters",
        sa.Column(
            "sire_id",
            sa.Uuid(),
            sa.ForeignKey("characters.id", name="fk_characters_sire_id_characters"),
            nullable=True,
        ),
    )
    op.add_column(
        "characters", sa.Column("sire_name", sa.String(), nullable=False, server_default="")
    )
    op.add_column(
        "characters", sa.Column("sire_clan", sa.String(), nullable=False, server_default="")
    )
    # Its sire is kept from the troupe's players: their sire lines leave it out.
    op.add_column(
        "characters",
        sa.Column("sire_secret", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_characters_sire_id", "characters", ["sire_id"])
    op.add_column(
        "troupes",
        sa.Column("sire_lines_players", sa.Boolean(), nullable=False, server_default="false"),
    )
    # The Embraces already run name their childe's sire.
    op.execute(
        """
        update characters c
        set sire_id = e.sire_id, sire_name = e.sire_name, sire_clan = e.sire_clan
        from embraces e
        where e.character_id = c.id and e.result = 'vampire'
        """
    )


def downgrade() -> None:
    op.drop_column("troupes", "sire_lines_players")
    op.drop_index("ix_characters_sire_id", table_name="characters")
    op.drop_column("characters", "sire_secret")
    op.drop_column("characters", "sire_clan")
    op.drop_column("characters", "sire_name")
    op.drop_column("characters", "sire_id")
