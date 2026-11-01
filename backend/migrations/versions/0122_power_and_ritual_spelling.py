"""Powers, techniques and rituals spelt as the books spell them; Collective
Cognizance is a luminary power only (issue #410)

Revision ID: 0122
Revises: 0121
Create Date: 2026-11-01 12:00:00.000000
"""

import json
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0122"
down_revision: str | None = "0121"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (category, old, new): the catalogue's spelling and the book's.
RENAMES = [
    ("elder_disciplines", "Potence: Relentess Fury", "Potence: Relentless Fury"),
    ("elder_disciplines", "Obeah: Unburden the Beastial Soul", "Obeah: Unburden the Bestial Soul"),
    ("elder_disciplines", "Dementation: La Llorana's Lament", "Dementation: La Llorona's Lament"),
    ("elder_disciplines", "Obeah: Rayzeel's Gaze", "Obeah: Rayzeel's Grace"),
    ("elder_disciplines", "Spiritus: Killer Instinct", "Spiritus: Killer Instincts"),
    ("luminary_disciplines", "Quietus: Awaken the Heartblood", "Quietus: Awaken the Heartsblood"),
    ("techniques", "Beastial Allure", "Bestial Allure"),
    ("techniques", "Perfected Insticts", "Perfected Instincts"),
    ("techniques", "Saguinary Expulsion", "Sanguinary Expulsion"),
    ("techniques", "Symbolic Possession", "Symbiotic Possession"),
    ("techniques", "Shedding the Serpent's Skin", "Sloughing the Serpent's Skin"),
    ("rituals", "Abyssal: Bend the Shadow", "Abyssal: Bind the Shadow"),
    ("rituals", "Abyssal: Dark Hands that Feeds", "Abyssal: Dark Hand that Feeds"),
    ("rituals", "Thaumaturgy: Hand of Path (Setite)", "Thaumaturgy: Hand of Ptah (Setite)"),
    ("rituals", "Necromancy: Letter from Beyond", "Necromancy: Letters from Beyond"),
    ("rituals", "Necromancy: Stained Night", "Necromancy: Stained Sight"),
    (
        "rituals",
        "Thaumaturgy: Thaumaturgical Metabolism",
        "Thaumaturgy: Thaumaturgic Metabolism",
    ),
    ("disciplines", "Necromancy: Path of the Graveborne", "Necromancy: Path of the Graveborn"),
    ("sabbat_rituals", "Irad's Will", "Irad's Wall"),
    ("sabbat_rituals", "Monomancy", "Monomacy"),
]

# Listed as an elder power and as a luminary power; the book has it as luminary only.
COGNIZANCE = "Auspex: Collective Cognizance"
ELDER, LUMINARY = "elder_disciplines", "luminary_disciplines"

# Where trait names are kept as text: JSON columns, then plain ones. A name is
# replaced only where it stands whole, so "Killer Instinct" never becomes
# "Killer Instinctss" and a longer name holding a shorter one is left alone.
JSON_COLUMNS = (
    ("rule_sets", "grants"),
    ("rule_sets", "checks"),
    ("rule_sets", "creation_only"),
    ("rule_sets", "feeding_modifiers"),
    ("house_traits", "effects"),
    ("trait_exceptions", "checks"),
    ("sheet_versions", "snapshot"),
    ("characters", "primary_paths"),
    ("character_traits", "choices"),
    ("character_traits", "power_choices"),
    ("discipline_purchases", "choices"),
    ("stock_npcs", "specializations"),
    ("quest_requirements", "options"),
    ("quest_requirements", "spent"),
    ("cycle_participants", "feeding"),
    ("play_games", "state"),
    ("xp_entries", "cost_basis"),
    ("audit_events", "data"),
)
TEXT_COLUMNS = (
    ("check_overrides", "check_key"),
    ("play_events", "tracker"),
    ("xp_entries", "reason"),
)


def whole(name: str) -> str:
    """A Postgres pattern for the name standing whole, not inside a longer word."""
    return rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])"


def replace_text(old: str, new: str) -> None:
    """Replace the name wherever it is kept as text. Loading the rules afterwards
    writes the rule set's own columns anew in any case."""
    connection = op.get_bind()
    pattern = {"old": old, "new": new, "pattern": whole(old)}
    # A troupe's house strength for a check of the old name, where it also has one
    # for the new name, would clash with it: the new one stands.
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
    the old. A character who holds both keeps the new one."""
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
    purchases and XP history (or merge it into the new name, where loading the new
    rules made that already), and wherever its name is kept as text."""
    connection = op.get_bind()
    old_id, new_id = definition(category, old), definition(category, new)
    if old_id is not None and new_id is not None:
        merge(old_id, new_id)
    elif old_id is not None:
        connection.execute(
            sa.text("update trait_definitions set name = :new where id = :id"),
            {"new": new, "id": old_id},
        )
    replace_text(old, new)


def cognizance_to_luminary() -> None:
    """Whoever holds Collective Cognizance as an elder power holds it as the
    luminary power instead, with what they paid for it; one who holds both keeps
    the luminary one. A troupe's house price for the elder entry goes with it."""
    connection = op.get_bind()
    elder_id, luminary_id = definition(ELDER, COGNIZANCE), definition(LUMINARY, COGNIZANCE)
    if elder_id is None:
        return
    connection.execute(
        sa.text("delete from cost_rules where trait_definition_id = :old"), {"old": elder_id}
    )
    if luminary_id is not None:
        merge(elder_id, luminary_id)
    else:
        connection.execute(
            sa.text(
                "update trait_definitions d set category_id = l.id"
                " from trait_categories e, trait_categories l"
                " where d.id = :id and e.id = d.category_id and l.rule_set_id = e.rule_set_id"
                " and l.key = :luminary"
            ),
            {"id": elder_id, "luminary": LUMINARY},
        )
    rows = connection.execute(
        sa.text("select id, snapshot from sheet_versions where snapshot::text like :name"),
        {"name": f"%{COGNIZANCE}%"},
    )
    for version_id, snapshot in rows.all():
        if not any(t.get("category") == ELDER and t.get("name") == COGNIZANCE for t in snapshot):
            continue
        held = {
            t.get("detail") or ""
            for t in snapshot
            if t.get("category") == LUMINARY and t.get("name") == COGNIZANCE
        }
        kept = []
        for trait in snapshot:
            if trait.get("category") == ELDER and trait.get("name") == COGNIZANCE:
                if (trait.get("detail") or "") in held:
                    continue
                trait["category"] = LUMINARY
            kept.append(trait)
        connection.execute(
            sa.text("update sheet_versions set snapshot = cast(:snapshot as jsonb) where id = :id"),
            {"snapshot": json.dumps(kept), "id": version_id},
        )
    # Its key in a check, a tracker or a tap: "elder_disciplines/Auspex: ...".
    old_key, new_key = f"{ELDER}/{COGNIZANCE}/", f"{LUMINARY}/{COGNIZANCE}/"
    connection.execute(
        sa.text(
            "delete from check_overrides o where starts_with(o.check_key, :old)"
            " and exists (select 1 from check_overrides n where n.troupe_id = o.troupe_id"
            " and n.check_key = :new || substr(o.check_key, length(:old) + 1))"
        ),
        {"old": old_key, "new": new_key},
    )
    for table, column in JSON_COLUMNS:
        connection.execute(
            sa.text(
                f"update {table} set {column} = replace({column}::text, :old, :new)::jsonb"
                f" where {column}::text like '%' || :old || '%'"
            ),
            {"old": old_key, "new": new_key},
        )
    for table, column in TEXT_COLUMNS:
        connection.execute(
            sa.text(
                f"update {table} set {column} = replace({column}, :old, :new)"
                f" where {column} like '%' || :old || '%'"
            ),
            {"old": old_key, "new": new_key},
        )


def upgrade() -> None:
    for category, old, new in RENAMES:
        rename(category, old, new)
    cognizance_to_luminary()


def downgrade() -> None:
    # Collective Cognizance stays a luminary power: the old rules files bring the
    # elder entry back, empty, when they are loaded.
    for category, old, new in RENAMES:
        rename(category, new, old)
