"""Limits on failed sign-ins and on sign-ups (#1059)."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.orm import Session
from starlette.requests import Request

from horatio import audit
from horatio.api import auth
from horatio.api.roster import message
from horatio.app import app
from horatio.auth import attempts
from horatio.auth.passwords import verify_password
from horatio.config import get_settings
from horatio.models import AuditEvent, AuthAttempt
from tests.api_helpers import PASSWORD, sign_up

HOME = "198.51.100.7"
ELSEWHERE = "203.0.113.20"


@pytest.fixture(autouse=True)
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """The limits are off for other tests, as each client signs in from one address."""
    monkeypatch.setattr(get_settings(), "auth_limits", True)


@pytest.fixture
def at(client_for: Callable[[], TestClient]) -> Iterator[Callable[[str], TestClient]]:
    """A client whose requests come from an address of the test's choosing."""
    client_for()  # shares the test's database session
    clients: list[TestClient] = []

    def make(ip: str) -> TestClient:
        client = TestClient(
            app, base_url="http://testserver/api", headers={"X-Horatio": "1"}, client=(ip, 50000)
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def sign_in(client: TestClient, login: str, password: str = "not my password") -> int:
    return client.post("/auth/login", json={"login": login, "password": password}).status_code


def later(session: Session, by: timedelta) -> None:
    """Move every try back in time."""
    session.execute(update(AuthAttempt).values(created_at=AuthAttempt.created_at - by))
    session.flush()


QUARTER_HOUR = timedelta(minutes=15, seconds=1)


def test_one_account_from_one_place_is_held_back_after_five_wrong_passwords(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sign_up(client_for, "agnes")
    home = at(HOME)
    # However the email is typed, it is one login.
    for login in ("agnes@example.com", " Agnes@Example.com", "AGNES@example.com "):
        assert sign_in(home, login) == 401
    # The handle is counted apart, as an unknown login is: counting them together
    # would show that a handle and an email are one account.
    for login in ("@agnes", "AGNES", "agnes ", "@Agnes", "agnes"):
        assert sign_in(home, login) == 401
    assert sign_in(home, "agnes", PASSWORD) == 429
    for _ in range(2):
        assert sign_in(home, "agnes@example.com") == 401

    held = home.post("/auth/login", json={"login": "agnes@example.com", "password": PASSWORD})
    assert held.status_code == 429
    assert held.json() == {"detail": attempts.SIGN_IN_WAIT}
    # Turned away before the password is checked: no Argon2 for it.
    checked: list[str] = []

    def verify(password: str, password_hash: str | None) -> tuple[bool, str | None]:
        checked.append(password)
        return verify_password(password, password_hash)

    monkeypatch.setattr(auth, "verify_password", verify)
    assert sign_in(home, "@agnes") == 429
    assert checked == []

    # Never the account everywhere: from elsewhere she signs in, and so does
    # anyone else from home.
    assert sign_in(at(ELSEWHERE), "agnes", PASSWORD) == 200
    sign_up(client_for, "bertha")
    assert sign_in(home, "bertha", PASSWORD) == 200

    # A quarter of an hour on, home may try again.
    later(session, QUARTER_HOUR)
    assert sign_in(home, "agnes", PASSWORD) == 200


def test_an_unknown_account_is_held_back_the_same(
    client_for: Callable[[], TestClient], at: Callable[[str], TestClient]
) -> None:
    sign_up(client_for, "agnes")
    home = at(HOME)
    for _ in range(5):
        assert sign_in(home, "agnes") == 401
        assert sign_in(home, "nobody@example.com") == 401

    known = home.post("/auth/login", json={"login": "agnes", "password": "guess"})
    unknown = home.post("/auth/login", json={"login": "nobody@example.com", "password": "guess"})

    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json()


def test_signing_in_forgets_the_wrong_passwords_before_it(
    client_for: Callable[[], TestClient], at: Callable[[str], TestClient]
) -> None:
    sign_up(client_for, "agnes")
    home = at(HOME)
    for _ in range(4):
        assert sign_in(home, "agnes") == 401
    assert sign_in(home, "agnes", PASSWORD) == 200
    for _ in range(5):
        assert sign_in(home, "agnes") == 401
    assert sign_in(home, "agnes") == 429


def test_one_place_is_held_back_however_many_accounts_it_tries(
    at: Callable[[str], TestClient], session: Session
) -> None:
    home = at(HOME)
    for n in range(20):
        assert sign_in(home, f"guess{n}@example.com") == 401
    assert sign_in(home, "one-more@example.com") == 429
    assert sign_in(at(ELSEWHERE), "one-more@example.com") == 401

    # Twenty a quarter of an hour, but only a hundred a day.
    for _ in range(4):
        later(session, QUARTER_HOUR)
        for n in range(20):
            assert sign_in(home, f"again{n}@example.com") == 401
    later(session, QUARTER_HOUR)
    assert sign_in(home, "one-more@example.com") == 429
    later(session, timedelta(hours=23))
    assert sign_in(home, "one-more@example.com") == 401
    # What is over a day old is forgotten: elsewhere's try, and home's first forty.
    kept = session.scalars(select(AuthAttempt.ip_address)).all()
    assert (set(kept), len(kept)) == ({HOME}, 61)


def test_sign_ups_from_one_place_are_limited(
    at: Callable[[str], TestClient], session: Session
) -> None:
    home = at(HOME)

    def sign_up_as(client: TestClient, name: str) -> int:
        body = {"email": f"{name}@example.com", "password": PASSWORD, "display_name": name}
        return client.post("/auth/signup", json=body).status_code

    assert sign_up_as(home, "agnes") == 201
    # Refused ones count too.
    for _ in range(19):
        assert sign_up_as(home, "agnes") == 409
    held = home.post(
        "/auth/signup",
        json={"email": "bertha@example.com", "password": PASSWORD, "display_name": "bertha"},
    )
    assert held.status_code == 429
    assert held.json() == {"detail": attempts.SIGN_UP_WAIT}
    assert sign_up_as(at(ELSEWHERE), "bertha") == 201

    # Twenty an hour, but only fifty a day.
    later(session, timedelta(hours=1))
    for n in range(20):
        assert sign_up_as(home, f"hour2_{n}") == 201
    later(session, timedelta(hours=1))
    for n in range(10):
        assert sign_up_as(home, f"hour3_{n}") == 201
    later(session, timedelta(hours=1))
    assert sign_up_as(home, "carla") == 429
    later(session, timedelta(hours=21))
    assert sign_up_as(home, "carla") == 201


def test_being_held_back_is_a_debug_event_and_keeps_nothing_typed(
    client_for: Callable[[], TestClient], at: Callable[[str], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    # Without the IP addresses the custodian may keep with them (#1066): see below.
    audit.save_settings(session, audit.LogSettings(record="debug", sign_in_ips=False))
    session.flush()
    home = at(HOME)
    for _ in range(5):
        sign_in(home, "agnes@example.com", "hunter2 typed here")
        sign_in(home, "nobody_here@example.com", "hunter2 typed here")
    assert sign_in(home, "agnes@example.com", "hunter2 typed here") == 429
    assert sign_in(home, "nobody_here@example.com", "hunter2 typed here") == 429

    held = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == "account.sign_in_throttled")
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )
    assert [(str(e.actor_id) if e.actor_id else None, e.level) for e in held] == [
        (agnes.id, "debug"),
        (None, "debug"),
    ]
    assert [message(e.action, "agnes", None, e.data) for e in held] == [
        "Someone was turned away from signing in as agnes: too many failed sign-ins from"
        " where they were.",
        "Someone was turned away from signing in to an account that doesn't exist: too many"
        " failed sign-ins from where they were.",
    ]
    for event in held:
        assert "hunter2" not in str(event.data)
        assert "nobody_here" not in str(event.data)
        assert HOME not in str(event.data)
    # The tries themselves keep a hash of the login, never the login.
    kept = set(session.scalars(select(AuthAttempt.identity_hash)))
    tried = {attempts.login_key(f"{name}@example.com") for name in ("agnes", "nobody_here")}
    # A sign-up keeps no login at all.
    assert kept == {None, *tried}

    for n in range(20):
        body = {"email": f"s{n}@example.com", "password": PASSWORD, "display_name": f"s{n}"}
        home.post("/auth/signup", json=body)
    body = {"email": "spare@example.com", "password": PASSWORD, "display_name": "spare"}
    assert home.post("/auth/signup", json=body).status_code == 429
    [refused] = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "account.sign_up_throttled")
    ).all()
    assert (refused.actor_id, refused.level, refused.data) == (None, "debug", {})
    assert message(refused.action, None, None, refused.data) == (
        "Someone was turned away from signing up: too many sign-ups from where they were."
    )

    # Keeping IP addresses with sign-in events, as the custodian does unless they say
    # otherwise (#1066), these keep where they came from too.
    audit.save_settings(session, audit.LogSettings(record="debug"))
    session.flush()
    assert sign_in(home, "agnes@example.com", PASSWORD) == 429
    assert home.post("/auth/signup", json=body).status_code == 429
    for action in ("account.sign_in_throttled", "account.sign_up_throttled"):
        newest = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        ).first()
        assert newest is not None
        assert newest.data["ip"] == HOME, action
        assert f" from {HOME}:" in message(newest.action, "agnes", None, newest.data)


def request_from(host: str | None) -> Request:
    return Request({"type": "http", "client": (host, 1) if host else None, "headers": []})


def test_where_a_request_comes_from() -> None:
    assert attempts.source(request_from("198.51.100.7")) == "198.51.100.7"
    # An IPv6 address counts as its /64; an IPv4 one written as IPv6 as itself.
    assert attempts.source(request_from("2001:db8:1:2:aaaa::1")) == "2001:db8:1:2::/64"
    assert attempts.source(request_from("2001:db8:1:2:bbbb::9")) == "2001:db8:1:2::/64"
    assert attempts.source(request_from("::ffff:198.51.100.7")) == "198.51.100.7"
    assert attempts.source(request_from("testclient")) == "testclient"
    assert attempts.source(request_from(None)) is None


def test_tries_made_at_once_cannot_all_slip_under_a_limit(engine: Engine) -> None:
    """Each try is counted under a lock, before the password is checked, so of ten
    made at once from one place at one account only five go on to be checked."""
    ip = "192.0.2.99"
    start = Barrier(10)

    def tried(_: int) -> bool:
        with Session(engine) as db:
            start.wait()
            allowed = attempts.may_sign_in(db, "agnes@example.com", ip)
            db.commit()
            return allowed

    try:
        with ThreadPoolExecutor(10) as pool:
            allowed = list(pool.map(tried, range(10)))
        assert allowed.count(True) == 5
    finally:
        with Session(engine) as db:
            db.execute(delete(AuthAttempt).where(AuthAttempt.ip_address == ip))
            db.commit()
