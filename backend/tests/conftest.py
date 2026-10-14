import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from horatio.app import app
from horatio.db import get_session
from horatio.rules.files import DATA_DIR, load_rule_set
from horatio.rules.store import sync_rule_set

# The test client talks plain HTTP, which would never send a Secure cookie back.
os.environ["HORATIO_COOKIE_SECURE"] = "false"

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


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url)
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
    sync_rule_set(session, load_rule_set(DATA_DIR / "bns_met_vampire.toml"))
    app.dependency_overrides[get_session] = lambda: session
    clients: list[TestClient] = []

    def make() -> TestClient:
        client = TestClient(app, headers={"X-Horatio": "1"})
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()
    app.dependency_overrides.clear()
