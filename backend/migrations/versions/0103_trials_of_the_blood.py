"""Trials of the Blood: the merit spelt as the book has it (Vol. 2 Issue 1, p. 27),
not "Trials of Blood"

Revision ID: 0103
Revises: 0101
Create Date: 2026-10-27 12:00:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0103"
down_revision: str | None = "0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD, NEW = "Trials of Blood", "Trials of the Blood"


def rename(old: str, new: str) -> None:
    """Rename the merit in place, so the characters who hold it keep it, with their
    purchases and XP history; and where its name is kept as text: the troupes'
    approved sheets, the key of the check its clan requirement makes (a troupe's
    house strength for it, an exception setting it aside) and the rule set's grants
    and checks. Loading the rules afterwards writes those two anew in any case."""
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "update trait_definitions d set name = :new from trait_categories c"
            " where d.category_id = c.id and c.key = 'merits'"
            " and d.name = :old and d.troupe_id is null"
            " and not exists (select 1 from trait_definitions e"
            "   where e.category_id = d.category_id and e.name = :new"
            "   and e.troupe_id is null)"
        ),
        {"old": old, "new": new},
    )
    # The name has nothing JSON escapes, and neither name holds the other.
    for column in ("grants", "checks"):
        connection.execute(
            sa.text(f"update rule_sets set {column} = replace({column}::text, :old, :new)::jsonb"),
            {"old": old, "new": new},
        )
    old_key, new_key = f"merits/{old}/", f"merits/{new}/"
    connection.execute(
        sa.text(
            "update check_overrides set check_key = :new || substr(check_key, length(:old) + 1)"
            " where starts_with(check_key, :old)"
        ),
        {"old": old_key, "new": new_key},
    )
    connection.execute(
        sa.text(
            "update trait_exceptions set checks = replace(checks::text, :old, :new)::jsonb"
            " where checks::text like '%' || :old || '%'"
        ),
        {"old": old_key, "new": new_key},
    )
    rows = connection.execute(
        sa.text("select id, snapshot from sheet_versions where snapshot::text like :name"),
        {"name": f"%{old}%"},
    )
    for version_id, snapshot in rows.all():
        for trait in snapshot:
            if trait.get("category") == "merits" and trait.get("name") == old:
                trait["name"] = new
        connection.execute(
            sa.text("update sheet_versions set snapshot = cast(:snapshot as jsonb) where id = :id"),
            {"snapshot": json.dumps(snapshot), "id": version_id},
        )


def upgrade() -> None:
    rename(OLD, NEW)


def downgrade() -> None:
    rename(NEW, OLD)
