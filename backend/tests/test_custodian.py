"""The command that makes an account the custodian, or stops it being one."""

import pytest
from sqlalchemy import Connection
from sqlalchemy.orm import Session

from horatio import custodian
from horatio.models import User


@pytest.fixture(autouse=True)
def command_session(connection: Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    """The command's own session, inside the test's transaction."""
    monkeypatch.setattr(
        custodian,
        "get_sessionmaker",
        lambda: lambda: Session(bind=connection, join_transaction_mode="create_savepoint"),
    )


def account(session: Session, name: str, *, is_custodian: bool = False) -> User:
    user = User(
        email=f"{name}@example.com", display_name=name, handle=name, is_custodian=is_custodian
    )
    session.add(user)
    session.commit()
    return user


def test_making_and_removing_a_custodian(
    session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    first = account(session, "keeper", is_custodian=True)
    second = account(session, "warden")

    assert custodian.main(["WARDEN@example.com"]) == 0
    assert capsys.readouterr().out == "WARDEN@example.com is now a custodian.\n"
    session.refresh(second)
    assert second.is_custodian

    assert custodian.main(["--remove", "keeper@example.com"]) == 0
    assert capsys.readouterr().out == "keeper@example.com is no longer a custodian.\n"
    session.refresh(first)
    assert not first.is_custodian


def test_the_last_custodian_stays(session: Session, capsys: pytest.CaptureFixture[str]) -> None:
    only = account(session, "keeper", is_custodian=True)
    account(session, "warden")

    assert custodian.main(["--remove", "keeper@example.com"]) == 1
    assert "the only custodian" in capsys.readouterr().err
    session.refresh(only)
    assert only.is_custodian

    # Someone who isn't one can't be removed either.
    assert custodian.main(["--remove", "warden@example.com"]) == 1
    assert capsys.readouterr().err == "warden@example.com is not a custodian.\n"


def test_usage(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in ([], ["--remove"], ["--revoke", "keeper@example.com"], ["a@b", "c@d"]):
        assert custodian.main(argv) == 2
        assert capsys.readouterr().err.startswith("usage:")
    assert custodian.main(["nobody@example.com"]) == 1
    assert "Sign up first" in capsys.readouterr().err
