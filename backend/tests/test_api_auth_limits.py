"""Limits on sign-ins and on sign-ups (#1059), and the custodian unblocking them (#1074)."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select, update
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
from tests.api_helpers import PASSWORD, Person, sign_up

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


def test_every_sign_in_from_one_place_counts_towards_a_bigger_limit(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signing in correctly checks a password too, so it is limited, by more (#1074)."""
    sign_up(client_for, "agnes")
    home = at(HOME)
    # Some fail, most succeed: sixty in a quarter of an hour.
    for _ in range(4):
        assert sign_in(home, "agnes") == 401
    for _ in range(56):
        assert sign_in(home, "agnes", PASSWORD) == 200
    checked: list[str] = []

    def verify(password: str, password_hash: str | None) -> tuple[bool, str | None]:
        checked.append(password)
        return verify_password(password, password_hash)

    monkeypatch.setattr(auth, "verify_password", verify)
    held = home.post("/auth/login", json={"login": "agnes", "password": PASSWORD})
    assert held.status_code == 429
    assert held.json() == {"detail": attempts.SIGN_INS_WAIT}
    # Whoever the login is, and whether an account uses it: the place is held back.
    assert sign_in(home, "nobody@example.com") == 429
    assert checked == []
    [event] = throttled_events(session)
    assert event.data["limit"] == "sign_ins"
    assert message(event.action, "agnes", None, event.data) == (
        f"Someone was turned away from signing in as agnes from {HOME}: too many sign-ins"
        " from where they were."
    )
    assert sign_in(at(ELSEWHERE), "agnes", PASSWORD) == 200

    # Sixty a quarter of an hour, but only three hundred a day.
    for _ in range(4):
        later(session, QUARTER_HOUR)
        for _ in range(60):
            session.add(AuthAttempt(action=attempts.SIGNED_IN, ip_address=HOME))
        session.flush()
    later(session, QUARTER_HOUR)
    assert sign_in(home, "agnes", PASSWORD) == 429
    later(session, timedelta(hours=23))
    assert sign_in(home, "agnes", PASSWORD) == 200


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


def throttled_events(session: Session) -> list[AuditEvent]:
    session.flush()
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action.like("account.sign_%_throttled%"))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def test_being_held_back_is_logged_at_info_once_a_window_and_keeps_nothing_typed(
    client_for: Callable[[], TestClient], at: Callable[[str], TestClient], session: Session
) -> None:
    """Always recorded, debug events or not, but only the first a limit turns away in
    its window, from one place (and login, for a limit at one login), at info; the
    rest at debug, so a flood can't fill the log (#1074)."""
    agnes = sign_up(client_for, "agnes")
    # Without the IP addresses the custodian may keep with them (#1066): see below.
    audit.save_settings(session, audit.LogSettings(sign_in_ips=False))
    session.flush()
    home = at(HOME)
    for _ in range(5):
        sign_in(home, "agnes@example.com", "hunter2 typed here")
        sign_in(home, "nobody_here@example.com", "hunter2 typed here")
    for _ in range(3):
        assert sign_in(home, "agnes@example.com", "hunter2 typed here") == 429
        assert sign_in(home, "nobody_here@example.com", "hunter2 typed here") == 429

    # Debug events aren't recorded: one each, at info.
    held = throttled_events(session)
    assert [(e.action, str(e.actor_id) if e.actor_id else None, e.level) for e in held] == [
        ("account.sign_in_throttled", agnes.id, "info"),
        ("account.sign_in_throttled", None, "info"),
    ]
    assert [message(e.action, "agnes", None, e.data) for e in held] == [
        "Someone was turned away from signing in as agnes: too many failed sign-ins from"
        " where they were.",
        "Someone was turned away from signing in to an account that doesn't exist: too many"
        " failed sign-ins from where they were.",
    ]
    for event in held:
        assert event.data["limit"] == "failed_at_login"
        assert "hunter2" not in str(event.data)
        assert "nobody_here" not in str(event.data)
        assert HOME not in str(event.data)
    # The tries themselves keep a hash of the login, never the login.
    kept = set(session.scalars(select(AuthAttempt.identity_hash)))
    tried = {attempts.login_key(f"{name}@example.com") for name in ("agnes", "nobody_here")}
    # A sign-up keeps no login at all.
    assert kept == {None, *tried}

    # Recording debug events, the ones after the first are there too, at debug.
    audit.save_settings(session, audit.LogSettings(record="debug", sign_in_ips=False))
    session.flush()
    assert sign_in(home, "agnes@example.com", "hunter2 typed here") == 429
    [again] = throttled_events(session)[2:]
    assert (again.action, again.level) == ("account.sign_in_throttled_again", "debug")
    assert message(again.action, "agnes", None, again.data) == (
        "Someone was turned away again from signing in as agnes: too many failed sign-ins"
        " from where they were."
    )

    # A quarter of an hour on, the limit is a new window: its first is info again.
    audit.save_settings(session, audit.LogSettings(sign_in_ips=False))
    later(session, QUARTER_HOUR)
    for _ in range(5):
        sign_in(home, "agnes@example.com")
    assert sign_in(home, "agnes@example.com") == 429
    assert sign_in(home, "agnes@example.com") == 429
    assert [(e.action, e.level) for e in throttled_events(session)[3:]] == [
        ("account.sign_in_throttled", "info")
    ]

    for n in range(20):
        body = {"email": f"s{n}@example.com", "password": PASSWORD, "display_name": f"s{n}"}
        home.post("/auth/signup", json=body)
    body = {"email": "spare@example.com", "password": PASSWORD, "display_name": "spare"}
    for _ in range(3):
        assert home.post("/auth/signup", json=body).status_code == 429
    [refused] = session.scalars(
        select(AuditEvent).where(AuditEvent.action.startswith("account.sign_up_throttled"))
    ).all()
    assert (refused.action, refused.actor_id, refused.level) == (
        "account.sign_up_throttled",
        None,
        "info",
    )
    assert refused.data == {"limit": "sign_ups"}
    assert message(refused.action, None, None, refused.data) == (
        "Someone was turned away from signing up: too many sign-ups from where they were."
    )

    # Keeping IP addresses with sign-in events, as the custodian does unless they say
    # otherwise (#1066), these keep where they came from too.
    audit.save_settings(session, audit.LogSettings(record="debug"))
    session.flush()
    assert sign_in(home, "agnes@example.com", PASSWORD) == 429
    assert home.post("/auth/signup", json=body).status_code == 429
    for action in ("account.sign_in_throttled_again", "account.sign_up_throttled_again"):
        newest = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        ).first()
        assert newest is not None
        assert newest.data["ip"] == HOME, action
        assert f" from {HOME}:" in message(newest.action, "agnes", None, newest.data)


def test_a_flood_from_one_place_is_logged_once_however_many_logins_it_tries(
    at: Callable[[str], TestClient], session: Session
) -> None:
    """A limit on a place, not a login: one event at info for the place, not one a login."""
    home = at(HOME)
    for n in range(20):
        assert sign_in(home, f"guess{n}@example.com") == 401
    for n in range(10):
        assert sign_in(home, f"more{n}@example.com") == 429
    assert [(e.level, e.data["limit"]) for e in throttled_events(session)] == [("info", "failed")]


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
            allowed = attempts.sign_in_held_back(db, "agnes@example.com", ip) is None
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


# --- changing a password while signed in (#1095) ----------------------------------------


def change_password(client: TestClient, current: str = "not my password") -> int:
    body = {"current": current, "password": "a new password 1"}
    return client.post("/auth/password", json=body).status_code


def test_changing_a_password_is_limited_at_the_account_from_anywhere(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agnes = sign_up(client_for, "agnes")
    # Agnes signed in somewhere else too: her tries there count with these.
    elsewhere = at(ELSEWHERE)
    assert sign_in(elsewhere, "agnes", PASSWORD) == 200
    for client in (agnes.client, elsewhere) * 5:
        assert change_password(client) == 403

    # The right password is turned away too, before it is checked: no Argon2 for it.
    checked: list[str] = []

    def verify(password: str, password_hash: str | None) -> tuple[bool, str | None]:
        checked.append(password)
        return verify_password(password, password_hash)

    monkeypatch.setattr(auth, "verify_password", verify)
    held = agnes.client.post(
        "/auth/password", json={"current": PASSWORD, "password": "a new password 1"}
    )
    assert held.status_code == 429
    assert held.json() == {"detail": attempts.PASSWORD_CHANGE_WAIT}
    assert change_password(elsewhere, PASSWORD) == 429
    assert checked == []

    # Only her account: anyone else changes theirs, and she can still sign in.
    bertha = sign_up(client_for, "bertha")
    assert change_password(bertha.client) == 403
    assert sign_in(at(HOME), "agnes", PASSWORD) == 200

    # A quarter of an hour on, she may try again. A right password counts too: each
    # runs Argon2.
    later(session, QUARTER_HOUR)
    assert change_password(agnes.client, PASSWORD) == 204
    counted = select(func.count()).where(
        AuthAttempt.action == attempts.PASSWORD_CHANGE,
        AuthAttempt.identity_hash == attempts.account_key(UUID(agnes.id)),
        AuthAttempt.created_at > func.now() - timedelta(minutes=15),
    )
    assert session.scalar(counted) == 1

    # And 30 a day.
    for _ in range(9):
        assert change_password(agnes.client) == 403
    later(session, QUARTER_HOUR)
    for _ in range(10):
        assert change_password(agnes.client) == 403
    later(session, QUARTER_HOUR)
    assert change_password(agnes.client) == 429


def test_being_held_back_from_changing_a_password_is_logged_at_info_once_a_window(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    audit.save_settings(session, audit.LogSettings(sign_in_ips=False))
    session.flush()
    for _ in range(10):
        assert change_password(agnes.client, "hunter2 typed here") == 403
    for _ in range(3):
        assert change_password(agnes.client, "hunter2 typed here") == 429

    def held() -> list[AuditEvent]:
        session.flush()
        return list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.action.startswith("account.password_change_throttled"))
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
        )

    [first] = held()
    assert (first.action, str(first.actor_id), first.level) == (
        "account.password_change_throttled",
        agnes.id,
        "info",
    )
    assert first.data == {"limit": "password_changes", "member": "agnes", "user_id": agnes.id}
    assert message(first.action, "agnes", None, first.data) == (
        "agnes was turned away from changing their password: too many tries at the account."
    )

    # Recording debug events, and IP addresses with them, the rest are there at debug.
    audit.save_settings(session, audit.LogSettings(record="debug"))
    session.flush()
    assert change_password(agnes.client, "hunter2 typed here") == 429
    [_, again] = held()
    assert (again.action, again.level) == ("account.password_change_throttled_again", "debug")
    assert "hunter2" not in str(again.data)
    assert message(again.action, "agnes", None, again.data) == (
        f"agnes was turned away again from changing their password from {again.data['ip']}:"
        " too many tries at the account."
    )


# --- the custodian's Throttled now card (#1074) -------------------------------------------


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    return sign_up(client_for, "custodian", custodian=True, session=session)


def held_back(client_for: Callable[[], TestClient], at: Callable[[str], TestClient]) -> None:
    """Agnes's email held back at home, and elsewhere held back whatever it tries."""
    sign_up(client_for, "agnes")
    home = at(HOME)
    for _ in range(5):
        assert sign_in(home, "agnes@example.com") == 401
    assert sign_in(home, "agnes@example.com") == 429
    elsewhere = at(ELSEWHERE)
    for n in range(20):
        assert sign_in(elsewhere, f"guess{n}@example.com") == 401
    assert sign_in(elsewhere, "agnes@example.com") == 429


def unblock(custodian: Person, throttle: dict[str, Any]) -> int:
    return custodian.client.post("/throttled/unblock", json={"id": throttle["id"]}).status_code


def test_the_custodian_sees_who_is_held_back_and_when_it_clears(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    custodian: Person,
    session: Session,
) -> None:
    held_back(client_for, at)
    for _ in range(5):
        assert sign_in(at("192.0.2.1"), "@nobody") == 401

    found = custodian.client.get("/throttled")
    assert found.status_code == 200, found.text
    shown = {
        (t["held"], t["address"], t["masked"], t["per_login"], t["login"], t["limit"])
        for t in found.json()
    }
    at_login = "5 failed sign-ins at one login in 15 minutes"
    assert shown == {
        ("sign_in", HOME, False, True, "agnes@example.com", at_login),
        ("sign_in", ELSEWHERE, False, False, None, "20 failed sign-ins in 15 minutes"),
        # No account uses the login.
        ("sign_in", "192.0.2.1", False, True, None, at_login),
    }
    # Each clears a quarter of an hour after the try that put it at its limit.
    newest = session.scalar(select(func.max(AuthAttempt.created_at)))
    assert newest is not None
    for t in found.json():
        clears = datetime.fromisoformat(t["clears"])
        assert newest - timedelta(minutes=1) < clears - timedelta(minutes=15) <= newest

    # While sign-in events keep no IP addresses, only the start of each shows.
    audit.save_settings(session, audit.LogSettings(sign_in_ips=False))
    session.flush()
    masked = custodian.client.get("/throttled")
    assert {(t["address"], t["masked"]) for t in masked.json()} == {
        ("198.51.x.x", True),
        ("203.0.x.x", True),
        ("192.0.x.x", True),
    }
    for ip in (HOME, ELSEWHERE, "192.0.2.1"):
        assert ip not in masked.text


def test_the_custodian_unblocks_an_address_and_it_is_a_notice(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    custodian: Person,
    session: Session,
) -> None:
    held_back(client_for, at)
    # Unblocking works whether the address shows or not.
    audit.save_settings(session, audit.LogSettings(sign_in_ips=False))
    session.flush()
    found = custodian.client.get("/throttled").json()
    by_login = next(t for t in found if t["per_login"])
    by_place = next(t for t in found if not t["per_login"])

    # Agnes's email at home: elsewhere is still held back.
    assert unblock(custodian, by_login) == 204
    assert [t["id"] for t in custodian.client.get("/throttled").json()] == [by_place["id"]]
    assert sign_in(at(HOME), "agnes@example.com") == 401
    assert sign_in(at(ELSEWHERE), "agnes@example.com") == 429

    audit.save_settings(session, audit.LogSettings())
    session.flush()
    assert unblock(custodian, by_place) == 204
    assert custodian.client.get("/throttled").json() == []
    assert sign_in(at(ELSEWHERE), "agnes@example.com") == 401
    # Once unblocked, it isn't there to unblock again.
    assert unblock(custodian, by_place) == 404

    lifted = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == "account.throttle_lifted")
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )
    assert [(e.level, str(e.actor_id)) for e in lifted] == [("notice", custodian.id)] * 2
    assert [message(e.action, "custodian", None, e.data) for e in lifted] == [
        "custodian unblocked sign-ins at agnes@example.com: over the limit of 5 failed"
        " sign-ins at one login in 15 minutes.",
        f"custodian unblocked sign-ins from {ELSEWHERE}: over the limit of 20 failed sign-ins"
        " in 15 minutes.",
    ]


def test_each_limit_a_place_is_over_is_unblocked_on_its_own(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    custodian: Person,
    session: Session,
) -> None:
    """The last try home made put it over two limits at once."""
    sign_up(client_for, "agnes")
    home = at(HOME)
    for n in range(15):
        assert sign_in(home, f"guess{n}@example.com") == 401
    for _ in range(5):
        assert sign_in(home, "agnes@example.com") == 401
    found = custodian.client.get("/throttled").json()
    assert len({t["id"] for t in found}) == len(found) == 2

    by_login = next(t for t in found if t["per_login"])
    assert unblock(custodian, by_login) == 204
    [lifted] = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "account.throttle_lifted")
    ).all()
    assert lifted.data["limit"] == "failed_at_login"
    # Agnes's five were the ones home's limit counted too.
    assert custodian.client.get("/throttled").json() == []


def test_only_the_custodian_sees_or_unblocks_who_is_held_back(
    client_for: Callable[[], TestClient], at: Callable[[str], TestClient], custodian: Person
) -> None:
    held_back(client_for, at)
    player = sign_up(client_for, "bertha")
    [first, *_] = custodian.client.get("/throttled").json()
    assert player.client.get("/throttled").status_code == 403
    assert unblock(player, first) == 403
    assert len(custodian.client.get("/throttled").json()) == 2


def test_sign_ups_held_back_can_be_unblocked(
    at: Callable[[str], TestClient], custodian: Person, session: Session
) -> None:
    home = at(HOME)
    for n in range(20):
        body = {"email": f"s{n}@example.com", "password": PASSWORD, "display_name": f"s{n}"}
        home.post("/auth/signup", json=body)
    body = {"email": "spare@example.com", "password": PASSWORD, "display_name": "spare"}
    assert home.post("/auth/signup", json=body).status_code == 429
    [held] = custodian.client.get("/throttled").json()
    assert (held["held"], held["limit"]) == ("sign_up", "20 sign-ups in an hour")
    assert unblock(custodian, held) == 204
    assert home.post("/auth/signup", json=body).status_code == 201
    [lifted] = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "account.throttle_lifted")
    ).all()
    assert message(lifted.action, "custodian", None, lifted.data) == (
        f"custodian unblocked sign-ups from {HOME}: over the limit of 20 sign-ups in an hour."
    )


def test_password_changes_held_back_show_the_account_and_can_be_unblocked(
    client_for: Callable[[], TestClient], custodian: Person, session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    for _ in range(10):
        assert change_password(agnes.client) == 403
    assert change_password(agnes.client, PASSWORD) == 429

    # Whatever the setting for IP addresses, no address: the account is held back
    # from anywhere.
    [held] = custodian.client.get("/throttled").json()
    assert {k: v for k, v in held.items() if k not in ("id", "clears")} == {
        "held": "password_change",
        "address": None,
        "masked": False,
        "per_login": True,
        "anywhere": True,
        "login": "@agnes",
        "limit": "10 password changes tried at one account in 15 minutes",
    }
    assert unblock(custodian, held) == 204
    assert custodian.client.get("/throttled").json() == []
    assert change_password(agnes.client, PASSWORD) == 204
    [lifted] = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "account.throttle_lifted")
    ).all()
    assert lifted.level == "notice"
    assert message(lifted.action, "custodian", None, lifted.data) == (
        "custodian unblocked password changes at @agnes: over the limit of 10 password"
        " changes tried at one account in 15 minutes."
    )
