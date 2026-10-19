"""The custodian's database backups (issue #50), with a stand-in for pg_dump that
says what it was asked."""

import gzip
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import backups
from horatio.config import get_settings
from horatio.models import AuditEvent
from tests.api_helpers import Person, sign_up

FAKE_PG_DUMP = """#!/bin/sh
if [ -n "$FAIL" ]; then echo "pg_dump: error: connection refused" >&2; exit 1; fi
echo "-- dumped with: $*"
echo "-- password given: $PGPASSWORD"
echo "create table t (x int);"
"""


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Backups kept in a scratch directory, made by the stand-in."""
    directory = tmp_path / "backups"
    directory.mkdir()
    fake = tmp_path / "pg_dump"
    fake.write_text(FAKE_PG_DUMP)
    fake.chmod(0o755)
    monkeypatch.setattr(get_settings(), "backup_dir", str(directory))
    monkeypatch.setattr(
        get_settings(), "database_url", "postgresql+psycopg://horatio:s3cret@db.example:5433/hdb"
    )
    monkeypatch.setattr(backups, "PG_DUMP", str(fake))
    return directory


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    return sign_up(client_for, "custodian", custodian=True, session=session)


def actions(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.action.like("backup.%"))
            .order_by(AuditEvent.id)
        )
    )


def test_only_the_custodian(
    client_for: Callable[[], TestClient], custodian: Person, kept: Path
) -> None:
    (kept / "horatio-20261019T031700Z.sql.gz").write_bytes(b"x")
    someone = sign_up(client_for, "someone")
    assert someone.client.get("/backups").status_code == 403
    assert someone.client.post("/backups").status_code == 403
    assert someone.client.get("/backups/horatio-20261019T031700Z.sql.gz").status_code == 403
    assert list(kept.iterdir()) == [kept / "horatio-20261019T031700Z.sql.gz"]


def test_make_list_and_download(custodian: Person, kept: Path, session: Session) -> None:
    (kept / "horatio-20261018T031700Z.sql.gz").write_bytes(gzip.compress(b"-- nightly"))
    (kept / "notes.txt").write_text("not a backup")

    made = custodian.client.post("/backups")
    assert made.status_code == 201, made.text
    backup = made.json()
    assert backup["manual"] is True
    assert backup["name"].endswith("-manual.sql.gz")

    listed = custodian.client.get("/backups").json()
    assert listed["available"] is True
    assert [b["name"] for b in listed["backups"]] == [
        backup["name"],
        "horatio-20261018T031700Z.sql.gz",
    ]
    assert listed["backups"][1]["manual"] is False

    download = custodian.client.get(f"/backups/{backup['name']}")
    assert download.status_code == 200
    assert backup["name"] in download.headers["content-disposition"]
    sql = gzip.decompress(download.content).decode()
    assert "create table t" in sql
    # Connected as the settings say, the password kept off the command line.
    assert "--dbname=hdb --host=db.example --port=5433 --username=horatio" in sql
    assert "s3cret" not in sql.splitlines()[0]
    assert "-- password given: s3cret" in sql

    assert actions(session) == ["backup.made", "backup.downloaded"]


def test_a_failed_dump_leaves_nothing(
    custodian: Person, kept: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAIL", "1")
    failed = custodian.client.post("/backups")
    assert failed.status_code == 500
    assert failed.json()["detail"] == "pg_dump failed: pg_dump: error: connection refused"
    assert list(kept.iterdir()) == []


def test_names_cannot_reach_outside(custodian: Person, kept: Path) -> None:
    (kept.parent / "secret.sql.gz").write_bytes(b"x")
    for name in ("..%2Fsecret.sql.gz", "secret.sql.gz", "horatio-20261019T031700Z.sql.gz"):
        assert custodian.client.get(f"/backups/{name}").status_code == 404


def test_not_set_up(custodian: Person) -> None:
    assert custodian.client.get("/backups").json() == {"available": False, "backups": []}
    assert custodian.client.post("/backups").status_code == 409
