"""Merits and flaws spelt as the books spell them; the two listed twice become one

Revision ID: 0106
Revises: 0103
Create Date: 2026-10-28 12:00:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0106"
down_revision: str | None = "0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (category, old, new): the catalogue's spelling and the book's.
RENAMES = [
    ("flaws", "Daughters of Cacophany: No Encore", "Daughters of Cacophony: No Encore"),
    ("flaws", "Daughters of Cacophany: Stage Fright", "Daughters of Cacophony: Stage Fright"),
    ("flaws", "Daughters of Cacophany: Tone Deaf", "Daughters of Cacophony: Tone Deaf"),
    ("flaws", "Intolerant", "Intolerance"),
    ("flaws", "Lhiannan: Deer in the Headlights", "Lhiannan: Deer in Headlights"),
    ("flaws", "Lasombra: Mancha's Disdain", "Lasombra: Mångha's Disdain"),
    ("merits", "No Place Like.Home", "No Place Like Home"),
    ("merits", "Blase", "Blasé"),
    ("merits", "Local Legends", "Local Legend"),
    ("merits", "The Blade Whisper", "The Blade Whisperer"),
    ("merits", "Baali", "Infernal Acolyte"),
]
# Listed twice, once misspelt: what is held under the misspelling moves to the
# entry the book spells right, and the misspelt one goes.
MERGES = [
    ("flaws", "Followers of Set: Temperment of Storms", "Followers of Set: Temperament of Storms"),
    ("merits", "Thaumaturgical Expertise", "Thaumaturgic Expertise"),
]


# Where trait names are kept as text, in JSON.
TEXT_COLUMNS = (("rule_sets", "grants"), ("rule_sets", "checks"), ("house_traits", "effects"))
CLAN_NAMES = {"Baali"}


def definition(category: str, name: str) -> object | None:
    """The rule set's trait definition (not a troupe's house trait), if there is one."""
    return (
        op.get_bind()
        .execute(
            sa.text(
                "select d.id from trait_definitions d join trait_categories c"
                " on d.category_id = c.id where c.key = :category and d.name = :name"
                " and d.troupe_id is null"
            ),
            {"category": category, "name": name},
        )
        .scalar()
    )


def merge(old_id: object, new_id: object) -> None:
    """Move everything that points at the old definition to the new one, then drop
    the old. A character who holds both keeps the one spelt right."""
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "delete from character_traits o where o.trait_definition_id = :old"
            " and exists (select 1 from character_traits n where n.character_id ="
            " o.character_id and n.trait_definition_id = :new"
            " and n.detail is not distinct from o.detail)"
        ),
        {"old": old_id, "new": new_id},
    )
    references = connection.execute(
        sa.text(
            "select c.conrelid::regclass::text, a.attname from pg_constraint c"
            " join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)"
            " where c.contype = 'f' and c.confrelid = 'trait_definitions'::regclass"
        )
    ).all()
    for table, column in references:
        connection.execute(
            sa.text(f'update {table} set "{column}" = :new where "{column}" = :old'),
            {"old": old_id, "new": new_id},
        )
    connection.execute(sa.text("delete from trait_definitions where id = :old"), {"old": old_id})


def rename(category: str, old: str, new: str) -> None:
    """Give the trait its new name in place, so those who hold it keep it, with their
    purchases and XP history (or merge it into the new name, where that exists);
    and where its name is kept as text: the troupes' approved sheets, the keys of
    its checks (a troupe's house strength for one, an exception setting one aside),
    the effects of a troupe's own merits and flaws, and the rule set's grants and
    checks. Loading the rules afterwards writes those two anew in any case."""
    connection = op.get_bind()
    old_id, new_id = definition(category, old), definition(category, new)
    if old_id is not None and new_id is not None:
        merge(old_id, new_id)
    elif old_id is not None:
        connection.execute(
            sa.text("update trait_definitions set name = :new where id = :id"),
            {"new": new, "id": old_id},
        )
    # The names have nothing JSON escapes but their letters, which jsonb keeps as
    # they are, and no other name in the rules holds the old one; but for "Baali",
    # which is also the clan's name and is named in no grant or check as a merit.
    for table, column in TEXT_COLUMNS if old not in CLAN_NAMES and new not in CLAN_NAMES else ():
        connection.execute(
            sa.text(
                f"update {table} set {column} = replace({column}::text, :old, :new)::jsonb"
                f" where {column}::text like '%' || :old || '%'"
            ),
            {"old": old, "new": new},
        )
    old_key, new_key = f"{category}/{old}/", f"{category}/{new}/"
    connection.execute(
        sa.text(
            "delete from check_overrides o where starts_with(o.check_key, :old)"
            " and exists (select 1 from check_overrides n where n.troupe_id = o.troupe_id"
            " and n.check_key = :new || substr(o.check_key, length(:old) + 1))"
        ),
        {"old": old_key, "new": new_key},
    )
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
        held = [t for t in snapshot if t.get("category") == category and t.get("name") == old]
        if not held:
            continue
        for trait in held:
            trait["name"] = new
        connection.execute(
            sa.text("update sheet_versions set snapshot = cast(:snapshot as jsonb) where id = :id"),
            {"snapshot": json.dumps(snapshot), "id": version_id},
        )


def upgrade() -> None:
    for category, old, new in RENAMES + MERGES:
        rename(category, old, new)


def downgrade() -> None:
    # Merged traits stay merged: the old rules files bring the misspelt entry back,
    # empty, when they are loaded.
    for category, old, new in RENAMES:
        rename(category, new, old)
