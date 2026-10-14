from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine

from horatio.models import Base
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
