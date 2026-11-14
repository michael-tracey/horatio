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


def test_the_tzimisce_migration_folds_the_misspelt_merit_into_the_books(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0222 (#811): "Blood of Tzimisce" was the same merit as "Blood of the
    Tzimisce" listed twice. A character who held the misspelt one holds the book's,
    one who held both holds it once, and a troupe's ban, an approved sheet and the
    grant a free Lore dot was placed by follow it."""
    merits = "merits"
    with engine.connect() as connection:
        book = trait_definition(connection, merits, "Blood of the Tzimisce")
    assert book is not None

    command.downgrade(alembic_config, "0221")
    user, troupe = uuid.uuid4(), uuid.uuid4()
    alone, both = uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'fleshcrafter@example.com', 'Fleshcrafter', 'fleshcrafter')"
                ),
                {"id": user},
            )
            connection.execute(
                text(
                    "insert into troupes (id, name, lead_user_id)"
                    " values (:id, 'Old Country', :lead)"
                ),
                {"id": troupe, "lead": user},
            )
            for character, name in ((alone, "Misspelt Only"), (both, "Spelt Both Ways")):
                connection.execute(
                    text(
                        "insert into characters (id, player_id, splat, name, home_troupe_id)"
                        " values (:id, :player, 'vampire', :name, :troupe)"
                    ),
                    {"id": character, "player": user, "name": name, "troupe": troupe},
                )
            twin = connection.scalar(
                text(
                    "insert into trait_definitions (category_id, name)"
                    " select category_id, 'Blood of Tzimisce' from trait_definitions"
                    " where id = :book returning id"
                ),
                {"book": book},
            )
            for character, definition in ((alone, twin), (both, twin), (both, book)):
                connection.execute(
                    text(
                        "insert into character_traits (character_id, trait_definition_id)"
                        " values (:character, :definition)"
                    ),
                    {"character": character, "definition": definition},
                )
            # The merit's two free dots of Lore, placed by staff on an NPC-style sheet.
            connection.execute(
                text(
                    "insert into character_traits (character_id, trait_definition_id, rating,"
                    " free_rating, grant_place, place_grant, place_by) values (:character,"
                    " :lore, 2, 2, 2, 'merits/Blood of Tzimisce/1', 'staff')"
                ),
                {"character": alone, "lore": trait_definition(connection, "skills", "Lore")},
            )
            for definition, reason in ((twin, "Misspelt"), (book, "Spelt right")):
                connection.execute(
                    text(
                        "insert into trait_overrides (troupe_id, trait_definition_id, banned,"
                        " ban_reason) values (:troupe, :definition, true, :reason)"
                    ),
                    {"troupe": troupe, "definition": definition, "reason": reason},
                )
            connection.execute(
                text(
                    "insert into sheet_versions (character_id, troupe_id, number, snapshot,"
                    " approved_by) values (:character, :troupe, 1, cast(:snapshot as jsonb),"
                    " :user)"
                ),
                {
                    "character": alone,
                    "troupe": troupe,
                    "snapshot": json.dumps(
                        [{"category": merits, "name": "Blood of Tzimisce", "detail": ""}]
                    ),
                    "user": user,
                },
            )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            assert trait_definition(connection, merits, "Blood of the Tzimisce") == book
            assert trait_definition(connection, merits, "Blood of Tzimisce") is None
            assert held(connection, alone) == [
                (merits, "Blood of the Tzimisce"),
                ("skills", "Lore"),
            ]
            assert held(connection, both) == [(merits, "Blood of the Tzimisce")]
            assert connection.scalars(
                text(
                    "select place_grant from character_traits where character_id = :id"
                    " and place_grant is not null"
                ),
                {"id": alone},
            ).all() == ["merits/Blood of the Tzimisce/1"]
            assert connection.execute(
                text(
                    "select trait_definition_id, ban_reason from trait_overrides"
                    " where troupe_id = :id"
                ),
                {"id": troupe},
            ).all() == [(book, "Spelt right")]
            approved = connection.scalar(
                text("select snapshot from sheet_versions where character_id = :id"),
                {"id": alone},
            )
        assert approved == [{"category": merits, "name": "Blood of the Tzimisce", "detail": ""}]
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for table, column, value in (
                ("trait_overrides", "troupe_id", troupe),
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
    """Migration 0158 (#550): a character retired before retiring gave up titles gives
    up those it still holds, with one entry in each troupe's log; one still playing
    keeps its own."""
    from horatio.api.roster import message

    command.downgrade(alembic_config, "0157")
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


def test_the_migration_keeps_assamite_for_troupes_that_were_there(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0128 (issue #430): a troupe made before it sees no change; one made
    after starts with Banu Haqim. Not beside the other tests of #430: their
    `without_bank` holds a lock on rule_sets that downgrading past 0162 waits for."""
    command.downgrade(alembic_config, "0127")
    user, older = uuid.uuid4(), uuid.uuid4()
    newer = uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'clan-names@example.com', 'Namer', 'clan_namer')"
                ),
                {"id": user},
            )
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Alamut', :lead)"),
                {"id": older, "lead": user},
            )

        command.upgrade(alembic_config, "head")

        with engine.begin() as connection:
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Masyaf', :lead)"),
                {"id": newer, "lead": user},
            )
            names = dict(
                connection.execute(
                    text("select id, assamite_name from troupes where lead_user_id = :lead"),
                    {"lead": user},
                ).all()
            )
        assert names == {older: "Assamite", newer: "Banu Haqim"}
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            connection.execute(text("delete from troupes where lead_user_id = :id"), {"id": user})
            connection.execute(text("delete from users where id = :id"), {"id": user})


def test_the_merits_and_flaws_migration_recalculates_only_drafts(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0165 (#657): a character still in creation has its merits cost XP and
    its flaws give it, up to the flaws' budget, in the order taken; one a home troupe
    accepted keeps its numbers."""
    command.downgrade(alembic_config, "0164")
    user, troupe = uuid.uuid4(), uuid.uuid4()
    draft, accepted = uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'drafts@example.com', 'Drafter', 'drafter')"
                ),
                {"id": user},
            )
            connection.execute(
                text("insert into troupes (id, name, lead_user_id) values (:id, 'Embers', :lead)"),
                {"id": troupe, "lead": user},
            )
            for character, name, home in ((draft, "Wren", None), (accepted, "Xan", troupe)):
                connection.execute(
                    text(
                        "insert into characters (id, player_id, splat, name, home_troupe_id)"
                        " values (:id, :player, 'vampire', :name, :home)"
                    ),
                    {"id": character, "player": user, "name": name, "home": home},
                )
                # Iron Will 3; Hunted 4, Slow Healing 3 and Dark Secret 1: 8 of flaws.
                for category, trait, points in (
                    ("merits", "Iron Will", 3),
                    ("flaws", "Hunted", 4),
                    ("flaws", "Slow Healing", 3),
                    ("flaws", "Dark Secret", 1),
                ):
                    definition = connection.scalar(
                        text(
                            "select d.id from trait_definitions d"
                            " join trait_categories c on c.id = d.category_id"
                            " join rule_sets r on r.id = c.rule_set_id"
                            " where r.splat = 'vampire' and c.key = :category"
                            " and d.name = :name and d.troupe_id is null"
                        ),
                        {"category": category, "name": trait},
                    )
                    connection.execute(
                        text(
                            "insert into character_traits (character_id, trait_definition_id,"
                            " rating, free_rating, creation_pick)"
                            " values (:character, :definition, :points, :points, :points)"
                        ),
                        {"character": character, "definition": definition, "points": points},
                    )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            flags = dict(
                connection.execute(
                    text("select id, merits_flaws_xp from characters where player_id = :id"),
                    {"id": user},
                ).all()
            )
            lines = connection.execute(
                text(
                    "select character_id, amount, reason from xp_entries"
                    " where kind = 'creation' and entered_by = :id order by id"
                ),
                {"id": user},
            ).all()
        assert flags == {draft: True, accepted: False}
        assert [(c, amount) for c, amount, _ in lines] == [
            (draft, -3),
            (draft, 4),
            (draft, 3),
            (draft, 0),
        ]
        assert lines[0][2] == "Iron Will 0 → 3, taken in creation: merits now cost XP (p. 106)"
        assert lines[1][2] == "Hunted 0 → 4, taken in creation: flaws now give XP (p. 106)"
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            connection.execute(text("delete from xp_entries where entered_by = :id"), {"id": user})
            connection.execute(
                text(
                    "delete from character_traits where character_id in"
                    " (select id from characters where player_id = :id)"
                ),
                {"id": user},
            )
            connection.execute(text("delete from characters where player_id = :id"), {"id": user})
            connection.execute(text("delete from troupes where lead_user_id = :id"), {"id": user})
            connection.execute(text("delete from users where id = :id"), {"id": user})


def test_the_retainer_animal_migration_marks_ardent_companions_ghouled_animal(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0225 (#854): Retainers gain `animal`, false for all but those a merit
    gives as an animal (Ardent Companion's ghouled animal, Vol. 2 Issue 1 p. 39)."""
    command.downgrade(alembic_config, "0224")
    user, troupe, character = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    companion, servant = uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'kennel@example.com', 'Kennel', 'kennel')"
                ),
                {"id": user},
            )
            connection.execute(
                text(
                    "insert into troupes (id, name, lead_user_id)"
                    " values (:id, 'Kennel Court', :lead)"
                ),
                {"id": troupe, "lead": user},
            )
            connection.execute(
                text(
                    "insert into characters (id, player_id, splat, name, home_troupe_id)"
                    " values (:id, :player, 'vampire', 'Houndkeeper', :troupe)"
                ),
                {"id": character, "player": user, "troupe": troupe},
            )
            for retainer, name, merit in (
                (companion, "Brutus", "Ardent Companion"),
                (servant, "Mrs Holloway", ""),
            ):
                connection.execute(
                    text(
                        "insert into retainers (id, character_id, name, dots, from_merit, ghoul)"
                        " values (:id, :character, :name, 3, :merit, true)"
                    ),
                    {"id": retainer, "character": character, "name": name, "merit": merit},
                )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            animals = dict(
                connection.execute(
                    text("select id, animal from retainers where character_id = :id"),
                    {"id": character},
                ).all()
            )
        assert animals == {companion: True, servant: False}
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for table, column, value in (
                ("retainers", "character_id", character),
                ("characters", "id", character),
                ("troupes", "id", troupe),
                ("users", "id", user),
            ):
                connection.execute(text(f"delete from {table} where {column} = :id"), {"id": value})


def test_the_setting_migration_makes_each_tone_a_mood_and_back(
    engine: Engine, alembic_config: Config
) -> None:
    """Migration 0220 (#770): a profile's tone becomes a mood of the troupe's own, named
    by it when short and described by it when long, and goes from the profile; going
    back puts it on the profile again."""
    command.downgrade(alembic_config, "0219")
    user = uuid.uuid4()
    short, long, none = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    long_tone = (
        "Political intrigue at court, with a slow-burning horror under it all, night after night."
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into users (id, email, display_name, handle)"
                    " values (:id, 'tone@example.com', 'Tone', 'tone')"
                ),
                {"id": user},
            )
            for troupe, name, tone in (
                (short, "Short Tone", "  Gothic noir "),
                (long, "Long Tone", long_tone),
                (none, "No Tone", None),
            ):
                setting = {"chronicle": name, "city": "Leeds"}
                if tone is not None:
                    setting["tone"] = tone
                connection.execute(
                    text(
                        "insert into troupes (id, name, lead_user_id, profile)"
                        " values (:id, :name, :lead, cast(:profile as jsonb))"
                    ),
                    {
                        "id": troupe,
                        "name": name,
                        "lead": user,
                        "profile": json.dumps({"setting": setting}),
                    },
                )

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            moods = connection.execute(
                text(
                    "select troupe_id, kind, name, description, book_key, position"
                    " from chronicle_motifs where troupe_id in (:a, :b, :c)"
                ),
                {"a": short, "b": long, "c": none},
            ).all()
            profiles = dict(
                connection.execute(
                    text("select id, profile from troupes where id in (:a, :b, :c)"),
                    {"a": short, "b": long, "c": none},
                ).all()
            )
        assert sorted(moods, key=lambda m: m[2]) == [
            (short, "mood", "Gothic noir", "", None, 1),
            (long, "mood", "Tone", long_tone, None, 1),
        ]
        assert profiles[short]["setting"] == {"chronicle": "Short Tone", "city": "Leeds"}
        assert profiles[long]["setting"] == {"chronicle": "Long Tone", "city": "Leeds"}

        command.downgrade(alembic_config, "0219")
        with engine.connect() as connection:
            tones = dict(
                connection.execute(
                    text(
                        "select id, profile -> 'setting' ->> 'tone' from troupes"
                        " where id in (:a, :b, :c)"
                    ),
                    {"a": short, "b": long, "c": none},
                ).all()
            )
        assert tones == {short: "Gothic noir", long: long_tone, none: None}
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as connection:
            for troupe in (short, long, none):
                connection.execute(
                    text("delete from chronicle_motifs where troupe_id = :id"), {"id": troupe}
                )
                connection.execute(text("delete from troupes where id = :id"), {"id": troupe})
            connection.execute(text("delete from users where id = :id"), {"id": user})
