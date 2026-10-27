"""status on the character: held fleeting and negative status with its patron, staff's
marks on status bans, and the troupe's Status on sheets setting; sheets' status
traits move to held status, or go where titles, social age or merits now give them

Revision ID: 0082
Revises: 0081
Create Date: 2026-10-27 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0082"
down_revision: str | None = "0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE_HORATIO = "(before Horatio)"

# The abiding status each title gives, and a Camarilla Ancilla's and Elder's, as
# bns_met_vampire_status.toml has them now: kept here so the migration reads the same
# whatever the rules later say. Conditional status counts: it is the title's.
TITLE_STATUS = {
    "Inner Circle": {"Ascendant", "Authority", "Commander", "Ominous"},
    "Imperator": {"Ascendant", "Authority", "Commander"},
    "Justicar": {"Ascendant", "Authority", "Commander"},
    "Archon": {"Commander", "Noble"},
    "Alastor": {"Commander"},
    "Prince": {"Authority", "Commander", "Sovereign"},
    "Petty Prince": {"Authority", "Sovereign"},
    "Seneschal": {"Noble", "Authority"},
    "Primogen": {"Noble"},
    "Whip": {"Noble"},
    "Harpy": {"Prominent", "Noble", "Guardian"},
    "Keeper of Elysium": {"Enforcer", "Guardian"},
    "Sheriff": {"Enforcer", "Privileged"},
    "Scourge": {"Enforcer"},
    "Regent": {"Authority", "Commander", "Ominous", "Sacrosanct"},
    "Cardinal": {"Authority", "Glorious", "Sacrosanct"},
    "Archbishop": {"Authority", "Glorious", "Ordained"},
    "Bishop": {"Blessed", "Enforcer", "Ordained"},
    "Templar": {"Enforcer"},
    "Priscus": {"Infamous", "Prominent", "Sacrosanct"},
    "Ductus": {"Blessed"},
    "Priest": {"Ordained"},
    "Baron": {"Authority", "Mandate"},
    "Constable": {"Enforcer", "Warrant"},
    "Architect": {"Enforcer"},
    "Ambassador": {"Established"},
}
AGE_STATUS = {"Ancilla": {"Confirmed"}, "Elder": {"Confirmed", "Established", "Privileged"}}


def social_age(generation: int, shift: int) -> str:
    """As horatio.social_age works it out."""
    start = 0 if generation <= 1 else 1 if generation == 2 else 2
    return ("Neonate", "Ancilla", "Elder")[min(max(start + shift, 0), 2)]


def upgrade() -> None:
    op.add_column(
        "troupes", sa.Column("status_by", sa.String(), server_default="players", nullable=False)
    )
    op.create_check_constraint("status_by", "troupes", "status_by in ('players', 'staff')")
    op.create_table(
        "held_statuses",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("patron_id", sa.Uuid(), nullable=True),
        sa.Column("patron_name", sa.String(), server_default="", nullable=False),
        sa.Column("patron_title", sa.String(), server_default="", nullable=False),
        sa.Column("patron_text", sa.String(), server_default="", nullable=False),
        sa.Column("troupe_id", sa.Uuid(), nullable=True),
        sa.Column("place", sa.String(), server_default="", nullable=False),
        sa.Column("given_on", sa.Date(), nullable=False),
        sa.Column("story", sa.String(), server_default="", nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=True),
        sa.Column("game_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["added_by"], ["users.id"], name=op.f("fk_held_statuses_added_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_held_statuses_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["play_games.id"],
            name=op.f("fk_held_statuses_game_id_play_games"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["patron_id"],
            ["characters.id"],
            name=op.f("fk_held_statuses_patron_id_characters"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["troupe_id"], ["troupes.id"], name=op.f("fk_held_statuses_troupe_id_troupes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_held_statuses")),
    )
    op.create_index(op.f("ix_held_statuses_character_id"), "held_statuses", ["character_id"])
    op.create_table(
        "status_ban_marks",
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("sect", sa.String(), nullable=False),
        sa.Column("ban", sa.String(), nullable=False),
        sa.Column("applies", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("marked_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name=op.f("fk_status_ban_marks_character_id_characters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["marked_by"], ["users.id"], name=op.f("fk_status_ban_marks_marked_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_status_ban_marks")),
        sa.UniqueConstraint(
            "character_id", "sect", "ban", name=op.f("uq_status_ban_marks_character_id")
        ),
    )
    op.create_index(op.f("ix_status_ban_marks_character_id"), "status_ban_marks", ["character_id"])
    move_status()


def move_status() -> None:
    """Each sheet's status traits, as #252 has it: fleeting and negative status becomes
    held status, from "(before Horatio)"; Accepted goes, as the sect gives it; abiding
    and innate status a title, social age or merit now gives goes, keeping what a
    merit grants; and the rest stays on the sheet for staff to resolve."""
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "select t.id, t.character_id, d.name, d.properties->>'type', t.rating,"
            " t.granted_rating, t.created_at, c.home_troupe_id, c.owner_troupe_id"
            " from character_traits t"
            " join trait_definitions d on d.id = t.trait_definition_id"
            " join trait_categories k on k.id = d.category_id"
            " join characters c on c.id = t.character_id"
            " where k.key = 'status_traits' and coalesce(t.rating, 0) > 0"
        )
    ).all()
    if not rows:
        return
    who = list({r.character_id for r in rows})
    sects: dict[object, str] = {}
    generation: dict[object, int] = {}
    shift: dict[object, int] = {}
    for character_id, category, name, rating, social_class in connection.execute(
        sa.text(
            "select t.character_id, k.key, d.name, t.rating, d.properties->>'social_class'"
            " from character_traits t"
            " join trait_definitions d on d.id = t.trait_definition_id"
            " join trait_categories k on k.id = d.category_id"
            " where t.character_id = any(:who)"
            " and k.key in ('sect', 'backgrounds', 'merits', 'flaws')"
        ),
        {"who": who},
    ):
        if category == "sect":
            sects[character_id] = name
        elif rating == 0:
            continue
        elif category == "backgrounds" and name == "Generation":
            generation[character_id] = rating or 0
        elif social_class:
            shift[character_id] = shift.get(character_id, 0) + int(social_class)
    titled: dict[object, set[str]] = {}
    for character_id, title in connection.execute(
        sa.text("select character_id, name from character_titles where character_id = any(:who)"),
        {"who": who},
    ):
        titled.setdefault(character_id, set()).update(TITLE_STATUS.get(title, set()))
    troupe_names = dict(connection.execute(sa.text("select id, name from troupes")).all())

    for row in rows:
        character_id, name, kind = row.character_id, row[2], row[3]
        bought = (row.rating or 0) - row.granted_rating
        if bought <= 0:
            continue
        given = set(titled.get(character_id, set()))
        if sects.get(character_id) == "Camarilla":
            age = social_age(generation.get(character_id, 0), shift.get(character_id, 0))
            given |= AGE_STATUS.get(age, set())
        if kind in ("Fleeting", "Negative"):
            troupe_id = row.home_troupe_id or row.owner_troupe_id
            connection.execute(
                sa.text(
                    "insert into held_statuses"
                    " (character_id, name, patron_text, troupe_id, place, given_on, created_at)"
                    " select :character, :name, :patron, :troupe, :place, :on, :at"
                    " from generate_series(1, :times)"
                ),
                {
                    "character": character_id,
                    "name": name,
                    "patron": BEFORE_HORATIO,
                    "troupe": troupe_id,
                    "place": troupe_names.get(troupe_id, ""),
                    "on": row.created_at.date(),
                    "at": row.created_at,
                    "times": bought,
                },
            )
        elif not (kind == "Accepted" or name in given):
            continue  # nothing gives it: left for staff to resolve
        if row.granted_rating:
            connection.execute(
                sa.text(
                    "update character_traits set rating = granted_rating,"
                    " free_rating = granted_rating, creation_pick = null where id = :id"
                ),
                {"id": row.id},
            )
        else:
            connection.execute(
                sa.text("delete from character_traits where id = :id"), {"id": row.id}
            )


def downgrade() -> None:
    """Held status goes back on the sheets as status traits, one dot each."""
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "insert into character_traits (character_id, trait_definition_id, rating)"
            " select h.character_id, d.id, count(*)"
            " from held_statuses h"
            " join trait_definitions d on d.name = h.name and d.troupe_id is null"
            " join trait_categories k on k.id = d.category_id and k.key = 'status_traits'"
            " group by h.character_id, d.id"
            " on conflict (character_id, trait_definition_id, detail)"
            " do update set rating = character_traits.rating + excluded.rating"
        )
    )
    op.drop_index(op.f("ix_status_ban_marks_character_id"), table_name="status_ban_marks")
    op.drop_table("status_ban_marks")
    op.drop_index(op.f("ix_held_statuses_character_id"), table_name="held_statuses")
    op.drop_table("held_statuses")
    op.drop_constraint("status_by", "troupes", type_="check")
    op.drop_column("troupes", "status_by")
