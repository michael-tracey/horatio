"""npc fitted picks: creation picks fitted to an NPC built without the wizard, so its
creation dots are free as a player character's are (issue #527)

Revision ID: 0155
Revises: 0154
Create Date: 2026-11-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0155"
down_revision: str | None = "0154"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("fits_picks", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("character_traits", sa.Column("pick_by", sa.String(), nullable=True))
    op.create_check_constraint(
        "pick_by",
        "character_traits",
        "pick_by is null or pick_by = 'off' and creation_pick is null"
        " or pick_by in ('fit', 'staff') and creation_pick is not null",
    )
    # The sheeted NPCs built without the wizard so far: finished, with no creation pick
    # on their sheet (the wizard won't finish with one unplaced). `python -m
    # horatio.npc_picks` fits their picks once this has run.
    op.execute(
        """
        update characters set fits_picks = true
        where kind = 'npc' and npc_form = 'sheeted' and creation_completed_at is not null
          and not exists (
            select 1 from character_traits t
            where t.character_id = characters.id and t.creation_pick is not null
          )
        """
    )


def downgrade() -> None:
    op.drop_constraint("pick_by", "character_traits", type_="check")
    op.drop_column("character_traits", "pick_by")
    op.drop_column("characters", "fits_picks")
