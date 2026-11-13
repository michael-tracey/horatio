"""Blood of the Tzimisce is one merit, spelt as the book spells it (core p. 244), not
two: what was held under "Blood of Tzimisce" moves to it (issue #811)

Revision ID: 0222
Revises: 0221
Create Date: 2026-11-13 20:00:00.000000
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0222"
down_revision: str | None = "0221"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY, OLD, NEW = "merits", "Blood of Tzimisce", "Blood of the Tzimisce"

# Where trait names are kept as text inside JSON: the rule set's own columns (which
# loading the rules writes anew in any case), the troupes' house rules about traits,
# approved sheets, a character's choices, play and the audit trail.
JSON_COLUMNS = (
    ("rule_sets", "grants"),
    ("rule_sets", "checks"),
    ("rule_sets", "creation_only"),
    ("rule_sets", "feeding_modifiers"),
    ("house_traits", "effects"),
    ("house_checks", "condition"),
    ("teacher_rules", "names"),
    ("teacher_rules", "condition"),
    ("cost_rules", "condition"),
    ("trait_exceptions", "checks"),
    ("sheet_versions", "snapshot"),
    ("character_traits", "choices"),
    ("discipline_purchases", "choices"),
    ("stock_npcs", "specializations"),
    ("quest_requirements", "options"),
    ("quest_requirements", "spent"),
    ("cycle_participants", "feeding"),
    ("play_games", "state"),
    ("xp_entries", "cost_basis"),
    ("audit_events", "data"),
)
# And as plain text: a check's key ("merits/Blood of Tzimisce/requirement"), the
# grant a free dot was placed by ("merits/Blood of Tzimisce/1"), a troupe's check on
# the merit by name, and the reason an XP entry gives.
TEXT_COLUMNS = (
    ("check_overrides", "check_key"),
    ("character_traits", "place_grant"),
    ("house_checks", "name"),
    ("play_events", "tracker"),
    ("xp_entries", "reason"),
)


def whole(name: str) -> str:
    """A Postgres pattern for the name standing whole, not inside a longer word."""
    return rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])"


def definition(name: str) -> object | None:
    """The rule set's trait definition (not a troupe's house trait), if there is one."""
    return (
        op.get_bind()
        .execute(
            sa.text(
                "select d.id from trait_definitions d join trait_categories c"
                " on d.category_id = c.id where c.key = :category and d.name = :name"
                " and d.troupe_id is null"
            ),
            {"category": CATEGORY, "name": name},
        )
        .scalar()
    )


def merge(old_id: object, new_id: object) -> None:
    """Move everything that points at the old definition to the new one, then drop
    the old. A character who holds both keeps the one spelt right, and a troupe that
    changed both (a ban, its own wording) keeps what it set for that one."""
    connection = op.get_bind()
    ids = {"old": old_id, "new": new_id}
    connection.execute(
        sa.text(
            "delete from character_traits o where o.trait_definition_id = :old"
            " and exists (select 1 from character_traits n where n.character_id ="
            " o.character_id and n.trait_definition_id = :new"
            " and n.detail is not distinct from o.detail)"
        ),
        ids,
    )
    connection.execute(
        sa.text(
            "delete from trait_overrides o where o.trait_definition_id = :old"
            " and exists (select 1 from trait_overrides n where n.troupe_id = o.troupe_id"
            " and n.trait_definition_id = :new)"
        ),
        ids,
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
            sa.text(f'update {table} set "{column}" = :new where "{column}" = :old'), ids
        )
    connection.execute(sa.text("delete from trait_definitions where id = :old"), ids)


def replace_text() -> None:
    """Replace the old name wherever it is kept as text. "Blood of Tzimisce" never
    stands inside "Blood of the Tzimisce", so the right spelling is left alone."""
    connection = op.get_bind()
    pattern = {"old": OLD, "new": NEW, "pattern": whole(OLD)}
    connection.execute(
        sa.text(
            "delete from check_overrides o where o.check_key ~ :pattern"
            " and exists (select 1 from check_overrides n where n.troupe_id = o.troupe_id"
            " and n.check_key = regexp_replace(o.check_key, :pattern, :new, 'g'))"
        ),
        pattern,
    )
    for table, column in JSON_COLUMNS:
        connection.execute(
            sa.text(
                f"update {table} set {column} ="
                f" regexp_replace({column}::text, :pattern, :new, 'g')::jsonb"
                f" where {column}::text like '%' || :old || '%'"
                f" and {column}::text ~ :pattern"
            ),
            pattern,
        )
    for table, column in TEXT_COLUMNS:
        connection.execute(
            sa.text(
                f"update {table} set {column} = regexp_replace({column}, :pattern, :new, 'g')"
                f" where {column} like '%' || :old || '%' and {column} ~ :pattern"
            ),
            pattern,
        )


def upgrade() -> None:
    connection = op.get_bind()
    old_id, new_id = definition(OLD), definition(NEW)
    if old_id is not None and new_id is not None:
        merge(old_id, new_id)
    elif old_id is not None:
        connection.execute(
            sa.text("update trait_definitions set name = :new where id = :id"),
            {"new": NEW, "id": old_id},
        )
    replace_text()


def downgrade() -> None:
    # The merit stays one: the old rules files bring the misspelt entry back, empty,
    # when they are loaded, and those who held it keep holding the book's spelling.
    pass
