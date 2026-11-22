"""Account › Sign-in's view of an account's safety (#1193): where it's signed in, signing
out there, and its recent sign-ins."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from horatio import audit
from horatio.app import app
from horatio.auth.devices import device, place
from horatio.models import AuditEvent, User
from horatio.models import Session as SignInSession
from tests.api_helpers import PASSWORD, sign_up

FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0"
IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"
)
ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/131.0.0.0 Mobile Safari/537.36"
)
EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
)
MAC_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)"
    " Version/18.1 Safari/605.1.15"
)


@pytest.fixture
def device_at(
    client_for: Callable[[], TestClient],
) -> Iterator[Callable[..., TestClient]]:
    """A client with a browser and an address of the test's choosing."""
    client_for()  # shares the test's database session
    clients: list[TestClient] = []

    def make(user_agent: str = FIREFOX, ip: str = "203.0.113.7") -> TestClient:
        client = TestClient(
            app,
            base_url="http://testserver/api",
            headers={"X-Horatio": "1", "User-Agent": user_agent},
            client=(ip, 50000),
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def signed_in(client: TestClient, login: str) -> TestClient:
    response = client.post("/auth/login", json={"login": login, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def test_a_user_agent_reads_as_a_browser_on_a_system() -> None:
    assert device(FIREFOX) == "Firefox on Windows"
    assert device(IPHONE) == "Safari on iPhone"
    assert device(ANDROID) == "Chrome on Android"
    assert device(EDGE) == "Edge on Windows"
    assert device(MAC_SAFARI) == "Safari on Mac"
    assert device("curl/8.0") == "An unknown browser"
    assert device(None) == "An unknown browser"
    assert device("Something (X11; Linux x86_64)") == "A browser on Linux"


def test_an_address_is_shown_only_as_its_network() -> None:
    assert place("203.0.113.7") == "203.0.113.…"
    assert place("2001:db8:85a3:12::7") == "2001:db8:85a3:…"
    assert place("2001:0db8:0000:0042::1") == "2001:db8:0:…"
    assert place("testclient") is None
    assert place(None) is None


def test_you_see_only_your_own_sign_ins_and_which_is_this_device(
    client_for: Callable[[], TestClient], device_at: Callable[..., TestClient]
) -> None:
    agnes = sign_up(client_for, "agnes")
    phone = signed_in(device_at(IPHONE), "agnes")
    bob = sign_up(client_for, "bob")

    from_phone = phone.get("/account/sessions").json()
    assert [(s["device"], s["this_device"]) for s in from_phone] == [
        ("Safari on iPhone", True),
        ("An unknown browser", False),
    ]
    assert all(s["signed_in_at"] and s["last_active_at"] for s in from_phone)
    assert [s["this_device"] for s in agnes.client.get("/account/sessions").json()] == [
        True,
        False,
    ]
    [own] = bob.client.get("/account/sessions").json()
    assert own["this_device"] is True
    assert own["id"] not in {s["id"] for s in from_phone}

    # Nor can anyone sign out a sign-in that isn't theirs.
    answer = bob.client.post(f"/account/sessions/{from_phone[0]['id']}/sign-out")
    assert answer.status_code == 404
    assert phone.get("/auth/me").status_code == 200


def test_signing_out_another_sign_in_ends_it_and_is_logged(
    client_for: Callable[[], TestClient],
    device_at: Callable[..., TestClient],
    session: Session,
) -> None:
    agnes = sign_up(client_for, "agnes")
    phone = signed_in(device_at(IPHONE), "agnes")
    [here, there] = agnes.client.get("/account/sessions").json()
    assert here["this_device"] and there["device"] == "Safari on iPhone"

    assert agnes.client.post(f"/account/sessions/{here['id']}/sign-out").status_code == 409
    answer = agnes.client.post(f"/account/sessions/{there['id']}/sign-out")

    assert answer.status_code == 204
    assert phone.get("/auth/me").status_code == 401
    assert [s["id"] for s in agnes.client.get("/account/sessions").json()] == [here["id"]]
    assert agnes.client.get("/auth/me").status_code == 200
    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "account.session_ended")
    ).one()
    assert event.actor_id is not None and str(event.actor_id) == agnes.id
    assert event.level == "info"
    assert event.data["device"] == "Safari on iPhone"
    assert agnes.client.post(f"/account/sessions/{there['id']}/sign-out").status_code == 404


def test_signing_out_everywhere_else_keeps_this_one(
    client_for: Callable[[], TestClient],
    device_at: Callable[..., TestClient],
    session: Session,
) -> None:
    agnes = sign_up(client_for, "agnes")
    others = [signed_in(device_at(ua), "agnes") for ua in (IPHONE, ANDROID)]
    bob = sign_up(client_for, "bob")

    answer = agnes.client.post("/account/sessions/sign-out-others")

    assert answer.json() == {"ended": 2}
    assert [o.get("/auth/me").status_code for o in others] == [401, 401]
    assert agnes.client.get("/auth/me").status_code == 200
    assert bob.client.get("/auth/me").status_code == 200
    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "account.other_sessions_ended")
    ).one()
    assert event.data["ended"] == "2 sign-ins"
    assert event.level == "info"
    # Nothing else to end: still said, as it was asked.
    assert agnes.client.post("/account/sessions/sign-out-others").json() == {"ended": 0}


def test_signing_out_elsewhere_is_refused_while_viewing_as_someone(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    keeper = sign_up(client_for, "keeper", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    started = keeper.client.post(
        f"/players/{agnes.id}/view-as", json={"reason": "A question about sign-in"}
    )
    assert started.status_code == 201, started.text

    seen = keeper.client.get("/account/sessions").json()

    assert [s["this_device"] for s in seen] == [False]
    assert keeper.client.post("/account/sessions/sign-out-others").status_code == 403
    assert agnes.client.get("/auth/me").status_code == 200


def last_active(session: Session, user_id: str) -> datetime | None:
    return session.scalars(
        select(SignInSession.last_active_at).where(SignInSession.user_id == user_id)
    ).one()


def test_last_active_is_written_at_most_once_every_few_minutes(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    a_while_ago = datetime.now(UTC) - timedelta(minutes=2)
    session.execute(update(SignInSession).values(last_active_at=a_while_ago))

    agnes.client.get("/auth/me")

    assert last_active(session, agnes.id) == a_while_ago

    longer_ago = datetime.now(UTC) - timedelta(minutes=6)
    session.execute(update(SignInSession).values(last_active_at=longer_ago))
    agnes.client.get("/auth/me")
    moved = last_active(session, agnes.id)

    assert moved is not None and moved > datetime.now(UTC) - timedelta(minutes=1)


def test_addresses_follow_the_custodians_setting(
    client_for: Callable[[], TestClient],
    device_at: Callable[..., TestClient],
    session: Session,
) -> None:
    audit.save_settings(session, audit.LogSettings(record="debug", sign_in_ips=True))
    sign_up(client_for, "agnes")
    phone = signed_in(device_at(IPHONE, "198.51.100.23"), "agnes")

    [here, _] = phone.get("/account/sessions").json()
    [latest, *_] = phone.get("/account/sign-ins").json()["sign_ins"]
    assert here["place"] == "198.51.100.…"
    assert latest["place"] == "198.51.100.…"

    # Turned off: kept addresses aren't shown, and no new one is kept.
    audit.save_settings(session, audit.LogSettings(record="debug", sign_in_ips=False))
    laptop = signed_in(device_at(FIREFOX, "192.0.2.40"), "agnes")
    assert {s["place"] for s in laptop.get("/account/sessions").json()} == {None}
    assert {s["place"] for s in laptop.get("/account/sign-ins").json()["sign_ins"]} == {None}

    # On again: the one started while it was off has none.
    audit.save_settings(session, audit.LogSettings(record="debug", sign_in_ips=True))
    places = {s["device"]: s["place"] for s in laptop.get("/account/sessions").json()}
    assert places["Firefox on Windows"] is None
    assert places["Safari on iPhone"] == "198.51.100.…"
    stored = session.scalars(
        select(SignInSession.ip_address).where(SignInSession.user_agent == FIREFOX)
    ).one()
    assert stored is None


def test_recent_sign_ins_come_from_the_log_newest_first(
    client_for: Callable[[], TestClient],
    device_at: Callable[..., TestClient],
    session: Session,
) -> None:
    audit.save_settings(session, audit.LogSettings(record="debug"))
    sign_up(client_for, "agnes")
    bob = sign_up(client_for, "bob")
    phone = device_at(IPHONE)
    wrong = phone.post("/auth/login", json={"login": "agnes", "password": "not it at all"})
    assert wrong.status_code == 401
    signed_in(phone, "agnes")
    bob.client.post("/auth/login", json={"login": "bob", "password": "not it either"})

    answer = phone.get("/account/sign-ins").json()

    assert answer["all_kept"] is True
    assert [(s["outcome"], s["how"]) for s in answer["sign_ins"]] == [
        ("signed_in", "Password"),
        ("failed", "Wrong password"),
    ]
    # Bob's own wrong password is only his.
    assert [s["how"] for s in bob.client.get("/account/sign-ins").json()["sign_ins"]] == [
        "Wrong password"
    ]


def test_recent_sign_ins_say_when_the_log_keeps_only_some(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    user = session.scalars(select(User).where(User.handle == agnes.handle)).one()
    audit.record(session, user, "account.second_step_failed", kind="app", ip="203.0.113.9")
    audit.record(session, user, "account.signed_in", kind="app", after="discord", ip="203.0.113.9")
    session.flush()

    answer = agnes.client.get("/account/sign-ins").json()

    # Signing in is a debug event, not recorded while the custodian records from info.
    assert answer["all_kept"] is False
    assert [(s["outcome"], s["how"], s["place"]) for s in answer["sign_ins"]] == [
        ("failed", "A wrong code from the authenticator app", "203.0.113.…")
    ]
    audit.save_settings(session, audit.LogSettings(record="debug"))
    audit.record(session, user, "account.signed_in", kind="app", after="discord", ip="203.0.113.9")
    session.flush()
    [latest, *_] = agnes.client.get("/account/sign-ins").json()["sign_ins"]
    assert latest["how"] == "Discord, then authenticator app"
