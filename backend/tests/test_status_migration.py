"""Migration 0082 moves the status traits on sheets (issue #252): fleeting and negative
status becomes held status from "(before Horatio)"; Accepted, and abiding status a
title or social age gives, goes; abiding status nothing gives stays, for staff."""

import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text

from tests.conftest import load_rules


def definition(connection: Connection, category: str, name: str) -> uuid.UUID:
    return connection.scalar(
        text(
            "select d.id from trait_definitions d join trait_categories c"
            " on c.id = d.category_id where c.key = :category and d.name = :name"
            " and d.troupe_id is null"
        ),
        {"category": category, "name": name},
    )


def test_status_traits_move_to_held_status_or_go(engine: Engine, alembic_config: Config) -> None:
    command.downgrade(alembic_config, "0080")
    user, troupe, character = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'mig@example.com', 'Mig', 'mig')"
                ),
                {"id": user},
            )
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Court', :lead)"),
                {"id": troupe, "lead": user},
            )
            connection.execute(
                text(
                    "insert into characters (id, player_id, splat, name, home_troupe_id)"
                    " values (:id, :player, 'vampire', 'Old Mother', :troupe)"
                ),
                {"id": character, "player": user, "troupe": troupe},
            )
            connection.execute(
                text(
                    "insert into character_titles (troupe_id, character_id, name)"
                    " values (:troupe, :character, 'Prince')"
                ),
                {"troupe": troupe, "character": character},
            )
            for category, name, rating in (
                ("sect", "Camarilla", None),
                ("backgrounds", "Generation", 3),
                ("status_traits", "Loyal", 2),
                ("status_traits", "Warned", 1),
                ("status_traits", "Acknowledged", 1),
                ("status_traits", "Confirmed", 1),
                ("status_traits", "Authority", 1),
                ("status_traits", "Noble", 1),
            ):
                connection.execute(
                    text(
                        "insert into character_traits (character_id, trait_definition_id, rating)"
                        " values (:character, :definition, :rating)"
                    ),
                    {
                        "character": character,
                        "definition": definition(connection, category, name),
                        "rating": rating,
                    },
                )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            held = connection.execute(
                text(
                    "select name, patron_text, place from held_statuses"
                    " where character_id = :id order by name"
                ),
                {"id": character},
            ).all()
            left = connection.scalars(
                text(
                    "select d.name from character_traits t"
                    " join trait_definitions d on d.id = t.trait_definition_id"
                    " join trait_categories c on c.id = d.category_id"
                    " where t.character_id = :id and c.key = 'status_traits'"
                ),
                {"id": character},
            ).all()
        assert [tuple(r) for r in held] == [
            ("Loyal", "(before Horatio)", "Court"),
            ("Loyal", "(before Horatio)", "Court"),
            ("Warned", "(before Horatio)", "Court"),
        ]
        assert left == ["Noble"]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for table, column in (
                ("held_statuses", "character_id"),
                ("character_traits", "character_id"),
                ("character_titles", "character_id"),
                ("characters", "id"),
            ):
                connection.execute(
                    text(f"delete from {table} where {column} = :id"), {"id": character}
                )
            connection.execute(text("delete from troupes where id = :id"), {"id": troupe})
            connection.execute(text("delete from users where id = :id"), {"id": user})
        load_rules(engine)


def test_marks_on_bans_on_clans_are_kept_by_key(engine: Engine, alembic_config: Config) -> None:
    """Migration 0159 (issue #553): a staff mark on a ban on clans moves from the ban's
    words, which now name the troupe's clans, to its key; any other stays."""
    old_pillar = (
        "Not Embraced into a pillar clan (Assamite, Brujah, Malkavian, Nosferatu, Toreador,"
        " Tremere, Ventrue); the Gangrel are not one again yet."
    )
    command.downgrade(alembic_config, "0158")
    user, character = uuid.uuid4(), uuid.uuid4()

    def marks() -> list[tuple[str, str]]:
        with engine.connect() as connection:
            return [
                (r.sect, r.ban)
                for r in connection.execute(
                    text("select sect, ban from status_ban_marks where character_id = :id"),
                    {"id": character},
                )
            ]

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'ban@example.com', 'Ban', 'banmig')"
                ),
                {"id": user},
            )
            connection.execute(
                text(
                    "insert into characters (id, player_id, splat, name)"
                    " values (:id, :player, 'vampire', 'Bruno')"
                ),
                {"id": character, "player": user},
            )
            for sect, ban in (
                ("Camarilla", old_pillar),
                ("Camarilla", "Has committed diablerie."),
                ("Sabbat", "Tremere antitribu."),
            ):
                connection.execute(
                    text(
                        "insert into status_ban_marks"
                        " (character_id, sect, ban, applies, reason, marked_by)"
                        " values (:character, :sect, :ban, false, 'Loyal', :user)"
                    ),
                    {"character": character, "sect": sect, "ban": ban, "user": user},
                )

        command.upgrade(alembic_config, "0159")
        assert sorted(marks()) == [
            ("Camarilla", "Has committed diablerie."),
            ("Camarilla", "pillar_clans"),
            ("Sabbat", "greater_antitribu"),
        ]
        command.downgrade(alembic_config, "0158")
        assert sorted(marks()) == [
            ("Camarilla", "Has committed diablerie."),
            ("Camarilla", old_pillar),
            ("Sabbat", "Tremere antitribu."),
        ]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for table, column in (("status_ban_marks", "character_id"), ("characters", "id")):
                connection.execute(
                    text(f"delete from {table} where {column} = :id"), {"id": character}
                )
            connection.execute(text("delete from users where id = :id"), {"id": user})
        load_rules(engine)
