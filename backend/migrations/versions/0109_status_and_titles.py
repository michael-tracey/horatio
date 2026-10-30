"""Status & Titles: players choose their characters' titles, unless the troupe keeps
titles to staff; one title a character holds in a troupe is active and gives status;
a troupe's own title can be one only one character holds

Each character holding titles keeps its highest at court active, so it loses the
status only of the others.

Revision ID: 0109
Revises: 0105
Create Date: 2026-10-30 12:00:00.000000
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0109"
down_revision: str | None = "0105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "troupes",
        sa.Column("titles_by", sa.String(), server_default="players", nullable=False),
    )
    op.create_check_constraint("titles_by", "troupes", "titles_by in ('players', 'staff')")
    op.add_column(
        "troupe_titles",
        sa.Column("unique", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "character_titles",
        sa.Column("active", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        "uq_character_titles_active",
        "character_titles",
        ["troupe_id", "character_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    keep_highest_active()


def keep_highest_active() -> None:
    """Make each character's highest title in each troupe its active one, as the
    Who's Who ranks them (horatio.titles.court_order): the rule sets' ranked titles
    first, then those that are only a name, then the troupe's own in its order."""
    bind = op.get_bind()
    ranked: dict[str, int] = {}
    for (rules,) in bind.execute(sa.text("select status_rules from rule_sets")):
        tables: list[Any] = (rules or {}).get("titles", [])
        for place, title in enumerate(tables, start=1):
            rank = title.get("rank") or place
            name = title["name"]
            ranked[name] = min(rank, ranked.get(name, rank))
    house = {
        (troupe_id, name): position
        for troupe_id, name, position in bind.execute(
            sa.text("select troupe_id, name, position from troupe_titles")
        )
    }

    def key(troupe_id: Any, name: str) -> tuple[int, int, str]:
        if (troupe_id, name) in house:
            return (2, house[troupe_id, name], name)
        if name in ranked:
            return (0, ranked[name], name)
        return (1, 0, name)

    highest: dict[tuple[Any, Any], tuple[tuple[int, int, str], Any]] = {}
    for row_id, troupe_id, character_id, name in bind.execute(
        sa.text("select id, troupe_id, character_id, name from character_titles")
    ):
        found = (key(troupe_id, name), row_id)
        kept = highest.get((troupe_id, character_id))
        if kept is None or found[0] < kept[0]:
            highest[troupe_id, character_id] = found
    for _, row_id in highest.values():
        bind.execute(
            sa.text("update character_titles set active = true where id = :id"), {"id": row_id}
        )


def downgrade() -> None:
    op.drop_index("uq_character_titles_active", table_name="character_titles")
    op.drop_column("character_titles", "active")
    op.drop_column("troupe_titles", "unique")
    op.drop_constraint("titles_by", "troupes", type_="check")
    op.drop_column("troupes", "titles_by")
