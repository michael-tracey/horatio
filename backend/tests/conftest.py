import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy import Connection, Engine, create_engine, select
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from horatio.app import app
from horatio.auth import passwords
from horatio.config import get_settings
from horatio.db import get_session
from horatio.models import RuleSet
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.store import forget_rules, sync_rule_set

# The test client talks plain HTTP, which would never send a Secure cookie back.
os.environ["HORATIO_COOKIE_SECURE"] = "false"
get_settings.cache_clear()  # importing the app has already read the settings once

# Real argon2 settings are slow on purpose; tests sign up hundreds of people.
passwords._hasher = PasswordHash(  # pyright: ignore[reportPrivateUsage]
    (Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1), BcryptHasher())
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A throwaway Postgres 18 for the whole test run."""
    with PostgresContainer("postgres:18") as postgres:
        yield postgres.get_connection_url(driver="psycopg")


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def load_rules(engine: Engine) -> None:
    """Load the generic rule sets, committed, once for the whole run."""
    with Session(engine) as session, session.begin():
        sync_rule_set(session, load_rule_set(DATA_DIR / "bns_met_vampire.toml"))


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url)
    load_rules(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        yield connection


@pytest.fixture
def session(connection: Connection) -> Iterator[Session]:
    """A session whose work is rolled back after each test."""
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()


@pytest.fixture
def client_for(session: Session) -> Iterator[Callable[[], TestClient]]:
    """Make API clients, one per person, all sharing the test's database session.

    Each client keeps its own cookies, so each one is signed in as one person.
    The `X-Horatio` header is what the app requires on every change.
    """
    app.dependency_overrides[get_session] = lambda: session
    clients: list[TestClient] = []

    def make() -> TestClient:
        client = TestClient(app, base_url="http://testserver/api", headers={"X-Horatio": "1"})
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def without_bank(session: Session) -> None:
    """Keep all unspent creation XP on a first acceptance, for tests about
    something else whose balances would otherwise lose it (MET: VTM p. 107)."""
    for rule_set in session.scalars(select(RuleSet)):
        rule_set.banked_xp = None
    session.flush()
    forget_rules(session)
