"""Push notifications to people's phones (#1054): a person turns push on per device,
chooses which kinds come by push, and the delivery worker sends each one, encrypted
to that browser and signed with the server's key, to a fake push service here. A
device the push service says is gone is forgotten; turning push off on a device
stops it; with no key set, push isn't available."""

import json
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import http_ece
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from py_vapid import Vapid
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import delivery, notifications, web_push
from horatio.config import get_settings
from horatio.models import PushDevice, PushNotice, Suspension, User
from tests.api_helpers import Person, sign_up

ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/131.0.0.0 Mobile Safari/537.36"
)
HOME_SCREEN_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Mobile/15E148"
)


@dataclass
class Browser:
    """A browser's side of a subscription: its keys, to read what is pushed to it."""

    endpoint: str
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    secret: bytes = field(default_factory=lambda: os.urandom(16))

    def subscription(self) -> dict[str, str]:
        point = self.key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        return {
            "endpoint": self.endpoint,
            "p256dh": web_push.b64url(point),
            "auth": web_push.b64url(self.secret),
        }

    def read(self, body: bytes) -> dict[str, Any]:
        return json.loads(
            http_ece.decrypt(
                body, private_key=self.key, auth_secret=self.secret, version="aes128gcm"
            )
        )


@dataclass
class FakePushService:
    """Takes pushes as a push service would, and answers each endpoint as told."""

    received: list[httpx.Request] = field(default_factory=list)
    answers: dict[str, int] = field(default_factory=dict)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.received.append(request)
        return httpx.Response(self.answers.get(str(request.url), 201))


@pytest.fixture
def pushes(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePushService]:
    """A server with its push key set, sending to a fake push service."""
    fake = FakePushService()
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_private_key", web_push.new_key())
    monkeypatch.setattr(settings, "vapid_subject", "mailto:custodian@example.org")
    monkeypatch.setattr(web_push, "transport", httpx.MockTransport(fake))
    yield fake


def endpoint(name: str) -> str:
    return f"https://fcm.googleapis.com/fcm/send/{name}-{uuid.uuid4().hex}"


def turn_on(person: Person, browser: Browser, agent: str = ANDROID) -> Any:
    return person.client.put(
        "/notification-settings/devices",
        json=browser.subscription(),
        headers={"User-Agent": agent},
    )


def ok(response: Any) -> Any:
    assert response.status_code < 300, response.text
    return response.json()


def user_of(session: Session, person: Person) -> User:
    return session.get_one(User, uuid.UUID(person.id))


def tell(session: Session, person: Person, kind: str, summary: str = "News") -> None:
    notifications.notify(session, [uuid.UUID(person.id)], kind, summary, "/characters")


def waiting(session: Session) -> list[PushNotice]:
    return list(session.scalars(select(PushNotice)))


def test_without_a_key_push_isnt_available(
    client_for: Callable[[], TestClient], session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "vapid_private_key", None)
    person = sign_up(client_for, "keyless")
    shown = ok(person.client.get("/notification-settings"))
    assert (shown["push"], shown["push_key"], shown["devices"]) == (False, None, [])
    refused = turn_on(person, Browser(endpoint("keyless")))
    assert refused.status_code == 409
    assert "aren't set up" in refused.json()["detail"]
    tell(session, person, "downtime.delivered")
    assert waiting(session) == []
    assert web_push.send_due(session) == 0


def test_a_downtime_result_is_pushed_to_the_device_and_reads_as_the_bell(
    client_for: Callable[[], TestClient], session: Session, pushes: FakePushService
) -> None:
    person = sign_up(client_for, "pushed")
    phone = Browser(endpoint("pushed"))
    shown = ok(turn_on(person, phone))
    assert shown["push"] is True
    assert shown["push_key"] == web_push.public_key()
    assert [(d["name"], d["endpoint"]) for d in shown["devices"]] == [
        ("Chrome on Android", phone.endpoint)
    ]

    tell(session, person, "downtime.delivered", "Your downtime results are ready.")
    # Queued with the event, sent by the worker, not in the request.
    assert pushes.received == []
    assert web_push.send_due(session) == 1
    [request] = pushes.received
    assert str(request.url) == phone.endpoint
    assert request.headers["TTL"] == str(12 * 60 * 60)
    assert request.headers["Content-Encoding"] == "aes128gcm"
    # Signed with the server's key, for this push service.
    authorization = request.headers["Authorization"]
    assert authorization.startswith("vapid t=")
    assert Vapid.verify(authorization)
    assert f"k={web_push.public_key()}" in authorization
    # Only the browser's keys open it, and it says no more than the bell.
    assert phone.read(request.content) == {
        "title": "Horatio",
        "body": "Your downtime results are ready.",
        "link": "/characters",
    }
    assert waiting(session) == []


def test_each_kind_pushes_as_the_person_chose(
    client_for: Callable[[], TestClient], session: Session, pushes: FakePushService
) -> None:
    person = sign_up(client_for, "chooses-push")
    ok(turn_on(person, Browser(endpoint("chooses"))))
    # Pushed until turned off: downtime results, boons, powers used, bonds,
    # announcements. Not until turned on: the rest.
    tell(session, person, "boon.accepted")
    tell(session, person, "character.renamed")
    assert [n.topic for n in waiting(session)] == ["boons"]
    web_push.send_due(session)

    ok(
        person.client.put(
            "/notification-settings", json={"topic": "boons", "way": "push", "on": False}
        )
    )
    ok(
        person.client.put(
            "/notification-settings", json={"topic": "renames", "way": "push", "on": True}
        )
    )
    shown = {
        t["name"]: {r["way"]: r["on"] for r in t["routes"]}
        for g in ok(person.client.get("/notification-settings"))["groups"]
        for t in g["topics"]
    }
    assert shown["boons"] == {"bell": True, "email": False, "push": False}
    assert shown["renames"] == {"bell": True, "email": False, "push": True}
    # Never pushed: the account's safety, and the tasks with nowhere to send them from.
    assert "push" not in shown["security"]
    assert "push" not in shown["teaching"]
    tell(session, person, "boon.accepted")
    tell(session, person, "character.renamed")
    assert [n.topic for n in waiting(session)] == ["renames"]
    # Turned off after it was queued: dropped, not sent.
    ok(
        person.client.put(
            "/notification-settings", json={"topic": "renames", "way": "push", "on": False}
        )
    )
    pushes.received.clear()
    assert web_push.send_due(session) == 0
    assert pushes.received == []
    assert waiting(session) == []


def test_each_device_gets_its_own_and_turning_one_off_stops_it(
    client_for: Callable[[], TestClient], session: Session, pushes: FakePushService
) -> None:
    person = sign_up(client_for, "two-devices")
    phone, tablet = Browser(endpoint("phone")), Browser(endpoint("tablet"))
    ok(turn_on(person, phone))
    shown = ok(turn_on(person, tablet, HOME_SCREEN_IPHONE))
    assert [d["name"] for d in shown["devices"]] == ["Chrome on Android", "iPhone"]
    tell(session, person, "downtime.delivered", "Both")
    web_push.send_due(session)
    assert {str(r.url) for r in pushes.received} == {phone.endpoint, tablet.endpoint}
    for request in pushes.received:
        reader = phone if str(request.url) == phone.endpoint else tablet
        assert reader.read(request.content)["body"] == "Both"

    # Turned off on the phone: what waits for it goes too.
    tell(session, person, "downtime.delivered", "Only the tablet")
    phone_id = next(d["id"] for d in shown["devices"] if d["endpoint"] == phone.endpoint)
    shown = ok(person.client.delete(f"/notification-settings/devices/{phone_id}"))
    assert [d["endpoint"] for d in shown["devices"]] == [tablet.endpoint]
    pushes.received.clear()
    web_push.send_due(session)
    assert [str(r.url) for r in pushes.received] == [tablet.endpoint]
    # Only their own.
    other = sign_up(client_for, "not-theirs")
    tablet_id = shown["devices"][0]["id"]
    assert other.client.delete(f"/notification-settings/devices/{tablet_id}").status_code == 404


def test_a_device_the_push_service_says_is_gone_is_forgotten(
    client_for: Callable[[], TestClient], session: Session, pushes: FakePushService
) -> None:
    person = sign_up(client_for, "gone-device")
    gone, kept = Browser(endpoint("gone")), Browser(endpoint("kept"))
    ok(turn_on(person, gone))
    ok(turn_on(person, kept))
    pushes.answers[gone.endpoint] = 410
    tell(session, person, "downtime.delivered")
    assert web_push.send_due(session) == 2
    devices = session.scalars(
        select(PushDevice.endpoint).where(PushDevice.user_id == uuid.UUID(person.id))
    )
    assert list(devices) == [kept.endpoint]
    assert waiting(session) == []
    # A 404 too.
    pushes.answers[kept.endpoint] = 404
    tell(session, person, "downtime.delivered")
    web_push.send_due(session)
    assert ok(person.client.get("/notification-settings"))["devices"] == []


def test_a_busy_push_service_is_tried_again_then_given_up(
    client_for: Callable[[], TestClient], session: Session, pushes: FakePushService
) -> None:
    person = sign_up(client_for, "busy-service")
    phone = Browser(endpoint("busy"))
    ok(turn_on(person, phone))
    pushes.answers[phone.endpoint] = 503
    tell(session, person, "downtime.delivered")
    at = delivery.now()
    for attempt in range(1, web_push.MAX_ATTEMPTS):
        assert web_push.send_due(session, at) == 1
        [notice] = waiting(session)
        assert notice.attempts == attempt
        # Not before its wait is over.
        assert web_push.send_due(session, at) == 0
        at = notice.due_at
    assert web_push.send_due(session, at) == 1
    assert waiting(session) == []
    # The device stays: only the push was dropped. The bell still has it.
    assert ok(person.client.get("/notification-settings"))["devices"] != []
    # A refusal not worth trying again is dropped at once.
    pushes.answers[phone.endpoint] = 400
    tell(session, person, "downtime.delivered")
    web_push.send_due(session)
    assert waiting(session) == []


def test_old_pushes_and_suspended_people_get_nothing(
    client_for: Callable[[], TestClient], session: Session, pushes: FakePushService
) -> None:
    person = sign_up(client_for, "late-push")
    ok(turn_on(person, Browser(endpoint("late"))))
    tell(session, person, "downtime.delivered")
    assert web_push.send_due(session, delivery.now() + web_push.KEEP_FOR) == 0
    assert waiting(session) == []
    # Someone suspended gets none.
    session.add(
        Suspension(
            user_id=uuid.UUID(person.id), reason="Testing", suspended_by_id=uuid.UUID(person.id)
        )
    )
    session.flush()
    tell(session, person, "downtime.delivered")
    assert waiting(session) == []


def test_only_a_push_service_with_proper_keys_is_taken(
    client_for: Callable[[], TestClient], pushes: FakePushService
) -> None:
    person = sign_up(client_for, "bad-device")
    for bad in (
        "http://fcm.googleapis.com/fcm/send/x",
        "https://example.org/push",
        "https://169.254.169.254/",
    ):
        refused = turn_on(person, Browser(bad))
        assert refused.status_code == 422, bad
    for good in (
        "https://web.push.apple.com/QGuQyavXutnMH",
        "https://updates.push.services.mozilla.com/wpush/v2/gAAAA",
        "https://wns2-par02p.notify.windows.com/w/?token=BQYA",
    ):
        assert web_push.known_service(good), good
    wrong_keys = {**Browser(endpoint("wrong")).subscription(), "p256dh": "bm90IGEga2V5"}
    refused = person.client.put("/notification-settings/devices", json=wrong_keys)
    assert refused.status_code == 422
    short_secret = {**Browser(endpoint("short")).subscription(), "auth": "c2hvcnQ"}
    assert person.client.put("/notification-settings/devices", json=short_secret).status_code == 422


def test_a_browser_turned_on_by_someone_else_becomes_yours(
    client_for: Callable[[], TestClient], session: Session, pushes: FakePushService
) -> None:
    """Someone signed out without turning it off, on a shared device."""
    first, second = sign_up(client_for, "first-on"), sign_up(client_for, "second-on")
    shared = Browser(endpoint("shared"))
    ok(turn_on(first, shared))
    tell(session, first, "downtime.delivered", "For the first")
    ok(turn_on(second, shared))
    assert ok(first.client.get("/notification-settings"))["devices"] == []
    assert len(ok(second.client.get("/notification-settings"))["devices"]) == 1
    # What waited for the first person doesn't go to the second's device.
    assert waiting(session) == []
    tell(session, first, "downtime.delivered", "For the first")
    tell(session, second, "downtime.delivered", "For the second")
    web_push.send_due(session)
    assert [shared.read(r.content)["body"] for r in pushes.received] == ["For the second"]


def test_a_troupe_and_a_long_line_as_the_bell_shows_them(
    client_for: Callable[[], TestClient], session: Session, pushes: FakePushService
) -> None:
    person = sign_up(client_for, "long-push")
    phone = Browser(endpoint("long"))
    ok(turn_on(person, phone))
    notice = PushNotice(
        device_id=uuid.uuid4(),
        topic="downtime",
        troupe="Lords of the Night",
        summary="x" * 3000,
        link="/",
    )
    shown = json.loads(web_push.payload(notice))
    assert shown["title"] == "Lords of the Night"
    assert len(shown["body"]) == web_push.LONGEST
    assert shown["body"].endswith("…")


@pytest.mark.parametrize(
    ("agent", "name"),
    [
        (ANDROID, "Chrome on Android"),
        (HOME_SCREEN_IPHONE, "iPhone"),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like"
            " Gecko) Version/18.1 Safari/605.1.15",
            "Safari on Mac",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Firefox on Windows",
        ),
        (None, "A device"),
    ],
)
def test_devices_are_named_from_their_browser(agent: str | None, name: str) -> None:
    assert web_push.device_name(agent) == name


def test_the_key_made_for_production_env_works() -> None:
    key = web_push.new_key()
    assert len(web_push.unb64url(key)) == 32
    vapid = Vapid.from_string(key)
    assert vapid.private_key is not None
