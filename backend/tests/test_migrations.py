import json
import uuid

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.orm import Session

from horatio.models import Base, TraitCategory, TraitDefinition
from tests.conftest import load_rules


def test_migrations_match_models(engine: Engine) -> None:
    """A model change without a migration (or the reverse) fails here."""
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []


def test_migrations_downgrade_and_upgrade_cleanly(engine: Engine, alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    load_rules(engine)  # the downgrade dropped them; later tests need them


def test_check_constraints_match_models(engine: Engine) -> None:
    """Alembic's autogenerate does not compare check constraints, so this does."""
    from sqlalchemy import CheckConstraint, inspect

    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        in_models = {
            str(c.name) for c in table.constraints if isinstance(c, CheckConstraint) and c.name
        }
        in_database = {str(c["name"]) for c in inspector.get_check_constraints(table.name)}
        assert in_models == in_database, table.name


def merit_definition(engine: Engine, name: str) -> object:
    with Session(engine) as session:
        return session.scalar(
            select(TraitDefinition.id)
            .join(TraitCategory, TraitDefinition.category_id == TraitCategory.id)
            .where(TraitCategory.key == "merits", TraitDefinition.name == name)
        )


def test_the_migration_renames_trials_of_blood_in_place(
    engine: Engine, alembic_config: Config
) -> None:
    """Sheets hold a merit by its definition, so renaming the definition keeps every
    character who holds it holding it."""
    merit = merit_definition(engine, "Trials of the Blood")
    assert merit is not None

    command.downgrade(alembic_config, "0101")
    try:
        assert merit_definition(engine, "Trials of Blood") == merit
        with engine.connect() as connection:
            checks = connection.scalar(text("select checks::text from rule_sets limit 1"))
        assert "merits/Trials of Blood/requirement" in (checks or "")
    finally:
        command.upgrade(alembic_config, "head")
        load_rules(engine)

    assert merit_definition(engine, "Trials of the Blood") == merit
    assert merit_definition(engine, "Trials of Blood") is None


def test_the_spelling_migration_renames_in_place_and_folds_in_the_misspelt_twin(
    engine: Engine, alembic_config: Config
) -> None:
    """Blasé keeps its definition under its new name, and what pointed at the misspelt
    Thaumaturgical Expertise now points at Thaumaturgic Expertise, the one left."""
    blase = merit_definition(engine, "Blasé")
    expertise = merit_definition(engine, "Thaumaturgic Expertise")
    assert blase is not None and expertise is not None

    command.downgrade(alembic_config, "0105")
    try:
        assert merit_definition(engine, "Blase") == blase
        with engine.begin() as connection:
            twin = connection.scalar(
                text(
                    "insert into trait_definitions (category_id, name)"
                    " select category_id, 'Thaumaturgical Expertise' from trait_definitions"
                    " where id = :expertise returning id"
                ),
                {"expertise": expertise},
            )
            starting = connection.scalar(
                text(
                    "insert into starting_traits (rule_set_id, trait_definition_id, rating)"
                    " select id, :twin, 1 from rule_sets limit 1 returning id"
                ),
                {"twin": twin},
            )
        command.upgrade(alembic_config, "head")

        assert merit_definition(engine, "Blasé") == blase
        assert merit_definition(engine, "Blase") is None
        assert merit_definition(engine, "Thaumaturgical Expertise") is None
        with engine.begin() as connection:
            moved = connection.scalar(
                text("select trait_definition_id from starting_traits where id = :id"),
                {"id": starting},
            )
            connection.execute(text("delete from starting_traits where id = :id"), {"id": starting})
        assert moved == expertise
    finally:
        command.upgrade(alembic_config, "head")
        load_rules(engine)


def trait_definition(connection: Connection, category: str, name: str) -> object:
    return connection.scalar(
        text(
            "select d.id from trait_definitions d join trait_categories c"
            " on c.id = d.category_id where c.key = :category and d.name = :name"
            " and d.troupe_id is null"
        ),
        {"category": category, "name": name},
    )


def held(connection: Connection, character: uuid.UUID) -> list[tuple[str, str]]:
    rows = connection.execute(
        text(
            "select c.key, d.name from character_traits t"
            " join trait_definitions d on d.id = t.trait_definition_id"
            " join trait_categories c on c.id = d.category_id"
            " where t.character_id = :id order by c.key, d.name"
        ),
        {"id": character},
    ).all()
    return [(r[0], r[1]) for r in rows]


def test_the_power_spelling_migration_renames_held_traits_and_moves_collective_cognizance(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0122 (#410): a character holding a misspelt power keeps it under the
    book's name, the same definition, and its name in a troupe's house strength and
    an approved sheet follows. Collective Cognizance held as an elder power becomes
    the luminary power, once."""
    elder, luminary = "elder_disciplines", "luminary_disciplines"
    cognizance = "Auspex: Collective Cognizance"
    with engine.connect() as connection:
        instincts = trait_definition(connection, elder, "Spiritus: Killer Instincts")
        luminary_cognizance = trait_definition(connection, luminary, cognizance)
    assert instincts is not None and luminary_cognizance is not None

    command.downgrade(alembic_config, "0121")
    user, troupe = uuid.uuid4(), uuid.uuid4()
    alone, both = uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            assert trait_definition(connection, elder, "Spiritus: Killer Instinct") == instincts
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'spelling@example.com', 'Speller', 'speller')"
                ),
                {"id": user},
            )
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Lexicon', :lead)"),
                {"id": troupe, "lead": user},
            )
            for character, name in ((alone, "Only Elder"), (both, "Both Kinds")):
                connection.execute(
                    text(
                        "insert into characters (id, player_id, splat, name, home_troupe_id)"
                        " values (:id, :player, 'vampire', :name, :troupe)"
                    ),
                    {"id": character, "player": user, "name": name, "troupe": troupe},
                )
            elder_cognizance = connection.scalar(
                text(
                    "insert into trait_definitions (category_id, name)"
                    " select category_id, :name from trait_definitions where id = :instincts"
                    " returning id"
                ),
                {"name": cognizance, "instincts": instincts},
            )
            for character, definition in (
                (alone, instincts),
                (alone, elder_cognizance),
                (both, elder_cognizance),
                (both, luminary_cognizance),
            ):
                connection.execute(
                    text(
                        "insert into character_traits (character_id, trait_definition_id)"
                        " values (:character, :definition)"
                    ),
                    {"character": character, "definition": definition},
                )
            connection.execute(
                text(
                    "insert into check_overrides (troupe_id, check_key, strength)"
                    " values (:troupe, 'techniques/Perfected Insticts/1', 'off')"
                ),
                {"troupe": troupe},
            )
            snapshot = [
                {"category": elder, "name": "Spiritus: Killer Instinct", "detail": ""},
                {"category": elder, "name": cognizance, "detail": ""},
            ]
            connection.execute(
                text(
                    "insert into sheet_versions (character_id, troupe_id, number, snapshot,"
                    " approved_by) values (:character, :troupe, 1, cast(:snapshot as jsonb),"
                    " :user)"
                ),
                {
                    "character": alone,
                    "troupe": troupe,
                    "snapshot": json.dumps(snapshot),
                    "user": user,
                },
            )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            assert trait_definition(connection, elder, "Spiritus: Killer Instincts") == instincts
            assert trait_definition(connection, elder, "Spiritus: Killer Instinct") is None
            assert trait_definition(connection, elder, cognizance) is None
            assert held(connection, alone) == [
                (elder, "Spiritus: Killer Instincts"),
                (luminary, cognizance),
            ]
            assert held(connection, both) == [(luminary, cognizance)]
            assert connection.scalars(
                text("select check_key from check_overrides where troupe_id = :id"),
                {"id": troupe},
            ).all() == ["techniques/Perfected Instincts/1"]
            approved = connection.scalar(
                text("select snapshot from sheet_versions where character_id = :id"),
                {"id": alone},
            )
        assert approved == [
            {"category": elder, "name": "Spiritus: Killer Instincts", "detail": ""},
            {"category": luminary, "name": cognizance, "detail": ""},
        ]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for table, column, value in (
                ("check_overrides", "troupe_id", troupe),
                ("sheet_versions", "troupe_id", troupe),
                ("character_traits", "character_id", alone),
                ("character_traits", "character_id", both),
                ("characters", "id", alone),
                ("characters", "id", both),
                ("troupes", "id", troupe),
                ("users", "id", user),
            ):
                connection.execute(text(f"delete from {table} where {column} = :id"), {"id": value})
        load_rules(engine)


def test_the_angelic_visage_migration_keeps_charisma(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0144 (#415): Angelic Visage's focus is now a choice kept in its detail,
    so those who held it keep Charisma, on the sheet, in the free choice that gave it
    and in the approved sheet."""
    with engine.connect() as connection:
        visage = trait_definition(connection, "merits", "Angelic Visage")
        piece = trait_definition(connection, "merits", "Piece That Remains")
    assert visage is not None and piece is not None

    command.downgrade(alembic_config, "0138")
    user, troupe = uuid.uuid4(), uuid.uuid4()
    bought, given = uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'visage@example.com', 'Visage', 'visage')"
                ),
                {"id": user},
            )
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Abyss', :lead)"),
                {"id": troupe, "lead": user},
            )
            for character, name in ((bought, "Bought It"), (given, "Given It")):
                connection.execute(
                    text(
                        "insert into characters (id, player_id, splat, name, home_troupe_id)"
                        " values (:id, :player, 'vampire', :name, :troupe)"
                    ),
                    {"id": character, "player": user, "name": name, "troupe": troupe},
                )
            choices = [{"grant": "g", "name": "Angelic Visage", "detail": "", "amount": 0}]
            for character, definition, chosen in (
                (bought, visage, []),
                (given, piece, choices),
                (given, visage, []),
            ):
                connection.execute(
                    text(
                        "insert into character_traits (character_id, trait_definition_id,"
                        " rating, choices) values (:character, :definition, 1,"
                        " cast(:choices as jsonb))"
                    ),
                    {
                        "character": character,
                        "definition": definition,
                        "choices": json.dumps(chosen),
                    },
                )
            snapshot = [{"category": "merits", "name": "Angelic Visage", "detail": "", "rating": 1}]
            connection.execute(
                text(
                    "insert into sheet_versions (character_id, troupe_id, number, snapshot,"
                    " approved_by) values (:character, :troupe, 1, cast(:snapshot as jsonb),"
                    " :user)"
                ),
                {
                    "character": bought,
                    "troupe": troupe,
                    "snapshot": json.dumps(snapshot),
                    "user": user,
                },
            )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            details = connection.execute(
                text(
                    "select character_id, detail from character_traits"
                    " where trait_definition_id = :id and character_id in (:a, :b)"
                ),
                {"id": visage, "a": bought, "b": given},
            ).all()
            kept = connection.scalar(
                text(
                    "select choices from character_traits where trait_definition_id = :id"
                    " and character_id = :character"
                ),
                {"id": piece, "character": given},
            )
            approved = connection.scalar(
                text("select snapshot from sheet_versions where character_id = :id"),
                {"id": bought},
            )
        assert sorted(d for _, d in details) == ["Charisma", "Charisma"]
        assert [c["detail"] for c in kept] == ["Charisma"]
        assert approved[0]["detail"] == "Charisma"
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for table, column, value in (
                ("sheet_versions", "troupe_id", troupe),
                ("character_traits", "character_id", bought),
                ("character_traits", "character_id", given),
                ("characters", "id", bought),
                ("characters", "id", given),
                ("troupes", "id", troupe),
                ("users", "id", user),
            ):
                connection.execute(text(f"delete from {table} where {column} = :id"), {"id": value})
        load_rules(engine)


def test_the_retired_titles_migration_gives_up_the_titles_retired_characters_hold(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0157 (#550): a character retired before retiring gave up titles gives
    up those it still holds, with one entry in each troupe's log; one still playing
    keeps its own."""
    from horatio.api.roster import message

    command.downgrade(alembic_config, "0156")
    user, troupe = uuid.uuid4(), uuid.uuid4()
    gone, playing = uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'gone@example.com', 'Gone', 'gone')"
                ),
                {"id": user},
            )
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Ashes', :lead)"),
                {"id": troupe, "lead": user},
            )
            for character, name, state in (
                (gone, "Ursula", "retired"),
                (playing, "Vera", "active"),
            ):
                connection.execute(
                    text(
                        "insert into characters (id, player_id, splat, name, home_troupe_id,"
                        " status) values (:id, :player, 'vampire', :name, :troupe, :status)"
                    ),
                    {
                        "id": character,
                        "player": user,
                        "name": name,
                        "troupe": troupe,
                        "status": state,
                    },
                )
            for character, name, active in (
                (gone, "Prince", True),
                (gone, "Harpy", False),
                (gone, "Whip", False),
                (playing, "Keeper of Elysium", True),
            ):
                connection.execute(
                    text(
                        "insert into character_titles (troupe_id, character_id, name, active)"
                        " values (:troupe, :character, :name, :active)"
                    ),
                    {"troupe": troupe, "character": character, "name": name, "active": active},
                )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            held = connection.execute(
                text("select character_id, name from character_titles where troupe_id = :id"),
                {"id": troupe},
            ).all()
            logged = connection.execute(
                text(
                    "select actor_id, character_id, action, data from audit_events"
                    " where troupe_id = :id"
                ),
                {"id": troupe},
            ).all()
        assert held == [(playing, "Keeper of Elysium")]
        assert len(logged) == 1
        actor, character, action, data = logged[0]
        assert (actor, character, action) == (None, gone, "title.given_up")
        assert message(action, None, data["character_name"], data) == (
            "Ursula, retired, gave up Harpy, Prince and Whip: a retired character holds no titles."
        )
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for table, column, value in (
                ("audit_events", "troupe_id", troupe),
                ("character_titles", "troupe_id", troupe),
                ("characters", "id", gone),
                ("characters", "id", playing),
                ("troupes", "id", troupe),
                ("users", "id", user),
            ):
                connection.execute(text(f"delete from {table} where {column} = :id"), {"id": value})
