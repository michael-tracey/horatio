"""npc grant places: the free dots a merit gives, fitted to an NPC built without the
wizard as its creation picks are: Ventrue Royalty's places, and the Path a Path merit
converts from Humanity (issue #566)

Revision ID: 0160
Revises: 0159
Create Date: 2026-11-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0160"
down_revision: str | None = "0159"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("character_traits", sa.Column("grant_place", sa.Integer(), nullable=True))
    op.add_column("character_traits", sa.Column("place_grant", sa.String(), nullable=True))
    op.add_column("character_traits", sa.Column("place_by", sa.String(), nullable=True))
    op.create_check_constraint(
        "place_is_free", "character_traits", "grant_place is null or grant_place <= free_rating"
    )
    op.create_check_constraint(
        "place_by",
        "character_traits",
        "place_by is null and grant_place is null and place_grant is null"
        " or place_by = 'off' and grant_place is null and place_grant is null"
        " or place_by in ('fit', 'staff') and grant_place is not null"
        " and place_grant is not null",
    )


def downgrade() -> None:
    op.drop_constraint("place_by", "character_traits", type_="check")
    op.drop_constraint("place_is_free", "character_traits", type_="check")
    op.drop_column("character_traits", "place_by")
    op.drop_column("character_traits", "place_grant")
    op.drop_column("character_traits", "grant_place")
