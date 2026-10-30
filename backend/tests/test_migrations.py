from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, select, text
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
