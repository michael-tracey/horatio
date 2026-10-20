"""The custodian's view of what is running: build, start time and migrations."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from horatio.api import system
from horatio.config import get_settings
from tests.api_helpers import sign_up


def test_the_custodian_sees_the_build_and_migrations(
    client_for: Callable[[], TestClient], session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    custodian = sign_up(client_for, "custodian", custodian=True, session=session)
    monkeypatch.setattr(get_settings(), "commit", "0123abc-dirty")
    monkeypatch.setattr(get_settings(), "built_at", datetime(2026, 10, 19, 21, 5, tzinfo=UTC))

    response = custodian.client.get("/system")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["commit"] == "0123abc-dirty"
    assert body["commit_url"] == "https://github.com/michael-tracey/horatio/commit/0123abc"
    assert body["built_at"] == "2026-10-19T21:05:00Z"
    assert body["code_revision"] == system.code_revision()
    assert body["code_revision"] is not None
    # The test database was migrated to head.
    assert body["database_revision"] == body["code_revision"]
    assert body["database_version"].startswith("18")


def test_a_local_build_has_no_commit(
    client_for: Callable[[], TestClient], session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    custodian = sign_up(client_for, "custodian", custodian=True, session=session)
    monkeypatch.setattr(get_settings(), "commit", None)
    monkeypatch.setattr(get_settings(), "built_at", None)

    body = custodian.client.get("/system").json()

    assert body["commit"] is None
    assert body["commit_url"] is None
    assert body["built_at"] is None


def test_only_the_custodian_sees_it(client_for: Callable[[], TestClient], session: Session) -> None:
    player = sign_up(client_for, "player", session=session)
    assert player.client.get("/system").status_code == 403
