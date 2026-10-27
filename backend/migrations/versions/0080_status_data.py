"""status data: the rule set's status rules, and the status traits Architect and
Anointed spelt right

Revision ID: 0080
Revises: 0079
Create Date: 2026-10-26 23:30:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0080"
down_revision: str | None = "0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The catalogue's misspelt status traits, and their book spelling (MET: VTM pp. 402, 448).
RENAMES = {"Architech": "Architect", "Annointed": "Anointed"}


def rename(renames: dict[str, str]) -> None:
    """Rename the status traits in place, so sheets, purchases and the XP history keep
    holding them; and in the grants that give them and the troupes' approved sheets.
    Loading the rules afterwards writes the grants anew in any case."""
    connection = op.get_bind()
    for old, new in renames.items():
        connection.execute(
            sa.text(
                "update trait_definitions d set name = :new from trait_categories c"
                " where d.category_id = c.id and c.key = 'status_traits'"
                " and d.name = :old and d.troupe_id is null"
                " and not exists (select 1 from trait_definitions e"
                "   where e.category_id = d.category_id and e.name = :new"
                "   and e.troupe_id is null)"
            ),
            {"old": old, "new": new},
        )
        connection.execute(
            sa.text("update rule_sets set grants = replace(grants::text, :old, :new)::jsonb"),
            {"old": json.dumps(old), "new": json.dumps(new)},
        )
    rows = connection.execute(
        sa.text("select id, snapshot from sheet_versions where snapshot::text ~ :names"),
        {"names": "|".join(renames)},
    )
    for version_id, snapshot in rows.all():
        for trait in snapshot:
            if trait.get("category") == "status_traits" and trait.get("name") in renames:
                trait["name"] = renames[trait["name"]]
        connection.execute(
            sa.text("update sheet_versions set snapshot = cast(:snapshot as jsonb) where id = :id"),
            {"snapshot": json.dumps(snapshot), "id": version_id},
        )


def upgrade() -> None:
    op.add_column(
        "rule_sets",
        sa.Column(
            "status_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    rename(RENAMES)


def downgrade() -> None:
    rename({new: old for old, new in RENAMES.items()})
    op.drop_column("rule_sets", "status_rules")
