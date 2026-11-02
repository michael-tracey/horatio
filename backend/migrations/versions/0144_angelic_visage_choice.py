"""Angelic Visage's focus is the player's choice of Appearance or Charisma, by the
errata (issue #415). Those who hold it already keep Charisma, the focus it gave: the
choice is kept in the merit's detail, so theirs now says Charisma.

Revision ID: 0144
Revises: 0138
Create Date: 2026-11-02 12:00:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0144"
down_revision: str | None = "0138"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MERIT = "Angelic Visage"
KEPT = "Charisma"


def definitions() -> list[object]:
    """The merit's definitions: the rule set's, and any troupe's of the same name."""
    return list(
        op.get_bind()
        .execute(
            sa.text(
                "select d.id from trait_definitions d join trait_categories c"
                " on d.category_id = c.id where c.key = 'merits' and d.name = :name"
            ),
            {"name": MERIT},
        )
        .scalars()
    )


def move(old: str, new: str) -> None:
    """Change the merit's detail from `old` to `new` wherever it is kept: the sheet,
    the free choices that gave it (Piece That Remains), the approved sheets, and the
    XP history and purchases naming it."""
    connection = op.get_bind()
    ids = definitions()
    if ids:
        params = {"ids": ids, "old": old, "new": new}
        in_ids = sa.bindparam("ids", expanding=True)
        connection.execute(
            sa.text(
                "update character_traits t set detail = :new"
                " where t.trait_definition_id in :ids and t.detail = :old"
                " and not exists (select 1 from character_traits n where n.character_id ="
                " t.character_id and n.trait_definition_id = t.trait_definition_id"
                " and n.detail = :new)"
            ).bindparams(in_ids),
            params,
        )
        connection.execute(
            sa.text(
                "update discipline_purchases set detail = :new"
                " where trait_definition_id in :ids and detail = :old"
            ).bindparams(in_ids),
            params,
        )
        connection.execute(
            sa.text(
                "update xp_entries set detail = :new"
                " where trait_definition_id in :ids and coalesce(detail, '') = :old"
            ).bindparams(in_ids),
            params,
        )
    rows = connection.execute(
        sa.text("select id, choices from character_traits where choices::text like :name"),
        {"name": f"%{MERIT}%"},
    )
    for trait_id, choices in rows.all():
        changed = False
        for choice in choices:
            if choice.get("name") == MERIT and choice.get("detail", "") == old:
                choice["detail"] = new
                changed = True
        if changed:
            connection.execute(
                sa.text(
                    "update character_traits set choices = cast(:choices as jsonb) where id = :id"
                ),
                {"choices": json.dumps(choices), "id": trait_id},
            )
    rows = connection.execute(
        sa.text("select id, snapshot from sheet_versions where snapshot::text like :name"),
        {"name": f"%{MERIT}%"},
    )
    for version_id, snapshot in rows.all():
        changed = False
        for trait in snapshot:
            if (
                trait.get("category") == "merits"
                and trait.get("name") == MERIT
                and (trait.get("detail") or "") == old
            ):
                trait["detail"] = new
                changed = True
        if changed:
            connection.execute(
                sa.text(
                    "update sheet_versions set snapshot = cast(:snapshot as jsonb) where id = :id"
                ),
                {"snapshot": json.dumps(snapshot), "id": version_id},
            )


def upgrade() -> None:
    move("", KEPT)


def downgrade() -> None:
    # The book's Charisma again, which needs no detail; an Appearance chosen since
    # keeps its detail, which the old rules leave be.
    move(KEPT, "")
