"""Vampiric Texts are equipment, not traits (issue #341): a new kind of item, text;
each text held as a trait becomes an item its character holds, with a line in its
history saying it moved from the sheet, and the vampiric_texts category goes

Revision ID: 0115
Revises: 0114
Create Date: 2026-10-31 12:00:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0115"
down_revision: str | None = "0114"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "('melee', 'ranged', 'protective', 'miscellaneous', 'text')"
OLD_KINDS = "('melee', 'ranged', 'protective', 'miscellaneous')"
TABLES = ("equipment_items", "equipment_qualities", "equipment_templates")
CATEGORY = "vampiric_texts"
# The catalogue's Wounds of the Night's Sword has this for its apostrophe.
REPLACEMENT_CHARACTER = "\ufffd"


def kinds(check: str) -> None:
    for table in TABLES:
        op.drop_constraint("kind", table, type_="check")
        op.create_check_constraint("kind", table, f"kind in {check}")


def upgrade() -> None:
    kinds(KINDS)
    op.add_column(
        "equipment_items",
        sa.Column("from_sheet", sa.Boolean(), server_default="false", nullable=False),
    )
    op.alter_column("equipment_items", "troupe_id", nullable=True)
    op.create_check_constraint(
        "troupe_given", "equipment_items", "troupe_id is not null or from_sheet"
    )
    move_texts()


def move_texts() -> None:
    """Each text held as a trait becomes an item, from the holder's home troupe if it
    has one; then the category goes, with everything that points at it."""
    connection = op.get_bind()
    texts = (
        "select d.id from trait_definitions d join trait_categories c on c.id = d.category_id"
        f" where c.key = '{CATEGORY}'"
    )
    held = connection.execute(
        sa.text(
            "select t.id, t.character_id, t.detail, t.note, t.created_at, d.name,"
            " c.name as character_name,"
            " coalesce(c.home_troupe_id, c.owner_troupe_id) as troupe_id"
            " from character_traits t join trait_definitions d on d.id = t.trait_definition_id"
            " join characters c on c.id = t.character_id"
            f" where t.trait_definition_id in ({texts})"
        )
    ).all()
    for row in held:
        item_id = connection.scalar(
            sa.text(
                "insert into equipment_items (character_id, troupe_id, given_by, given_at,"
                " name, kind, grade, description, status, from_sheet)"
                " values (:character, :troupe, null, :at, :name, 'text', 'standard',"
                " :description, 'held', true) returning id"
            ),
            {
                "character": row.character_id,
                "troupe": row.troupe_id,
                "at": row.created_at,
                "name": row.name.replace(REPLACEMENT_CHARACTER, "'"),
                # What the sheet said of it: its detail and the player's note.
                "description": "\n".join(p for p in (row.detail, row.note) if p),
            },
        )
        connection.execute(
            sa.text(
                "insert into equipment_events (item_id, action, actor_id, troupe_id,"
                " to_character_id, to_name, changes)"
                " values (:item, 'given', null, :troupe, :character, :name,"
                " cast(:changes as jsonb))"
            ),
            {
                "item": item_id,
                "troupe": row.troupe_id,
                "character": row.character_id,
                "name": row.character_name,
                "changes": json.dumps({"from_sheet": True}),
            },
        )
    connection.execute(
        sa.text(f"delete from character_traits where trait_definition_id in ({texts})")
    )
    # The troupes' approved sheets: a text is no longer on them.
    connection.execute(
        sa.text(
            "update sheet_versions set snapshot = ("
            " select coalesce(jsonb_agg(e), '[]'::jsonb) from jsonb_array_elements(snapshot) e"
            f" where e->>'category' is distinct from '{CATEGORY}')"
            f' where snapshot @> \'[{{"category": "{CATEGORY}"}}]\''
        )
    )
    # Texts cost nothing, so an XP line naming one is rare: one priced by a troupe's
    # house rule. It stays in the history with its amount, as a fee, since a
    # purchase names a trait and there is none now.
    connection.execute(
        sa.text(
            "update xp_entries set kind = 'fee', trait_definition_id = null"
            f" where trait_definition_id in ({texts})"
        )
    )
    category = f"select id from trait_categories where key = '{CATEGORY}'"
    connection.execute(
        sa.text(
            f"delete from cost_rules where category_id in ({category})"
            f" or trait_definition_id in ({texts})"
        )
    )
    connection.execute(sa.text(f"delete from creation_rules where category_id in ({category})"))
    connection.execute(
        sa.text(f"delete from check_overrides where starts_with(check_key, '{CATEGORY}/')")
    )
    # Anything else that names a text (a starting trait, an allowance, a troupe's
    # own text) goes with it.
    references = connection.execute(
        sa.text(
            "select c.conrelid::regclass::text, a.attname from pg_constraint c"
            " join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)"
            " where c.contype = 'f' and c.confrelid = 'trait_definitions'::regclass"
        )
    ).all()
    for table, column in references:
        connection.execute(sa.text(f'delete from {table} where "{column}" in ({texts})'))
    connection.execute(sa.text(f"delete from trait_definitions where id in ({texts})"))
    connection.execute(sa.text(f"delete from trait_categories where key = '{CATEGORY}'"))


def downgrade() -> None:
    # The texts given as items go, and aren't put back on the sheets: the old rules
    # files bring the category back, empty, when they are loaded.
    op.execute("delete from equipment_templates where kind = 'text'")
    op.execute("delete from equipment_qualities where kind = 'text'")
    op.execute("delete from equipment_items where kind = 'text' or troupe_id is null")
    op.drop_constraint("troupe_given", "equipment_items", type_="check")
    op.alter_column("equipment_items", "troupe_id", nullable=False)
    op.drop_column("equipment_items", "from_sheet")
    kinds(OLD_KINDS)
