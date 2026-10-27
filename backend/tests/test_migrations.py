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
