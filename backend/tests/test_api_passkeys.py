"""Passkeys as a second step, and a troupe asking two-step sign-in of its staff (#1057).

The browser is played by a software authenticator: a P-256 key, "none" attestation,
and the signatures WebAuthn asks for, as a phone or password manager makes them."""

import base64
import hashlib
import json
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.api.roster import message
from horatio.app import app
from horatio.auth import two_step
from horatio.config import get_settings
from horatio.models import AuditEvent, Notification, Passkey, Troupe
from tests.api_helpers import PASSWORD, Person, sign_up
from tests.api_helpers import Troupe as TroupeFixture

RP_ID = "localhost"
ORIGIN = "http://localhost:5173"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class Authenticator:
    """A passkey on a device, which signs what Horatio asks."""

    def __init__(self, origin: str = ORIGIN) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.id = os.urandom(16)
        self.count = 0
        self.origin = origin

    def client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}
        ).encode()

    def flags_and_count(self, flags: int) -> bytes:
        return hashlib.sha256(RP_ID.encode()).digest() + bytes([flags]) + self.count.to_bytes(4)

    def create(self, options: dict[str, Any]) -> dict[str, Any]:
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32), -3: numbers.y.to_bytes(32)}
        )
        attested = bytes(16) + len(self.id).to_bytes(2) + self.id + cose
        # User present and verified, with attested credential data.
        data = self.flags_and_count(0x45) + attested
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": data})
        return {
            "id": b64(self.id),
            "rawId": b64(self.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(self.client_data("webauthn.create", options["challenge"])),
                "attestationObject": b64(attestation),
                "transports": ["internal", "hybrid"],
            },
            "clientExtensionResults": {},
        }

    def get(self, options: dict[str, Any], *, count: int | None = None) -> dict[str, Any]:
        self.count = self.count + 1 if count is None else count
        client_data = self.client_data("webauthn.get", options["challenge"])
        data = self.flags_and_count(0x05)
        signature = self.key.sign(
            data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64(self.id),
            "rawId": b64(self.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "authenticatorData": b64(data),
                "signature": b64(signature),
            },
            "clientExtensionResults": {},
        }


@pytest.fixture
def required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "two_step_for_custodians", True)


def add_passkey(person: Person, name: str = "Phone") -> tuple[Authenticator, list[str]]:
    device = Authenticator()
    options = person.client.post("/two-step/passkeys/options", json={"password": PASSWORD})
    assert options.status_code == 200, options.text
    added = person.client.post(
        "/two-step/passkeys", json={"credential": device.create(options.json()), "name": name}
    )
    assert added.status_code == 200, added.text
    return device, added.json()["recovery_codes"]


def password(client: TestClient, login: str) -> Any:
    return client.post("/auth/login", json={"login": login, "password": PASSWORD})


def sign_with(client: TestClient, device: Authenticator, **how: Any) -> Any:
    options = client.post("/auth/second-step/passkey/options")
    assert options.status_code == 200, options.text
    return client.post(
        "/auth/second-step/passkey", json={"credential": device.get(options.json(), **how)}
    )


def events(session: Session, action: str) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


# --- passkeys ----------------------------------------------------------------------------


def test_a_passkey_is_added_from_account_with_recovery_codes(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")

    options = agnes.client.post("/two-step/passkeys/options", json={"password": PASSWORD}).json()
    assert options["rp"] == {"id": RP_ID, "name": "Horatio"}
    assert options["user"]["name"] == "@agnes"
    device = Authenticator()
    added = agnes.client.post(
        "/two-step/passkeys", json={"credential": device.create(options), "name": "Phone"}
    )

    assert added.status_code == 200, added.text
    assert len(added.json()["recovery_codes"]) == 10
    state = agnes.client.get("/two-step").json()
    assert [p["name"] for p in state["passkeys"]] == ["Phone"]
    kept = session.scalars(select(Passkey)).one()
    assert (kept.credential_id, kept.transports) == (device.id, ["internal", "hybrid"])
    [event] = events(session, "account.two_step_added")
    assert message(event.action, "Agnes", None, event.data) == (
        "Agnes added a passkey, Phone, for two-step sign-in."
    )
    # Its challenge works once; a second passkey brings no more codes.
    again = agnes.client.post(
        "/two-step/passkeys", json={"credential": device.create(options), "name": "Again"}
    )
    assert again.status_code == 409
    _, codes = add_passkey(agnes, "Laptop")
    assert codes == []


def test_a_passkey_made_for_another_site_is_refused(
    client_for: Callable[[], TestClient],
) -> None:
    agnes = sign_up(client_for, "agnes")
    options = agnes.client.post("/two-step/passkeys/options", json={"password": PASSWORD}).json()
    elsewhere = Authenticator(origin="https://evil.example")
    refused = agnes.client.post(
        "/two-step/passkeys", json={"credential": elsewhere.create(options), "name": "Phone"}
    )
    assert refused.status_code == 422
    assert agnes.client.get("/two-step").json()["passkeys"] == []


def test_signing_in_with_a_passkey(client_for: Callable[[], TestClient], session: Session) -> None:
    agnes = sign_up(client_for, "agnes")
    device, _ = add_passkey(agnes)
    fresh = client_for()

    asked = password(fresh, "agnes")

    assert asked.status_code == 202
    assert asked.json() == {"second_step": ["passkey", "recovery_code"]}
    signed_in = sign_with(fresh, device)
    assert signed_in.status_code == 200, signed_in.text
    assert fresh.get("/auth/me").json()["handle"] == "agnes"
    kept = session.scalars(select(Passkey)).one()
    assert (kept.sign_count, kept.last_used_at is not None) == (1, True)


def test_a_passkey_answer_works_once_and_a_count_going_back_is_refused(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    device, _ = add_passkey(agnes)
    first = client_for()
    password(first, "agnes")
    options = first.post("/auth/second-step/passkey/options").json()
    answer = device.get(options)
    assert first.post("/auth/second-step/passkey", json={"credential": answer}).status_code == 200

    # The same answer again, to a new sign-in's challenge, is refused.
    again = client_for()
    password(again, "agnes")
    again.post("/auth/second-step/passkey/options")
    replayed = again.post("/auth/second-step/passkey", json={"credential": answer})
    assert replayed.status_code == 401
    # A copied key's count goes back: refused.
    assert sign_with(again, device, count=1).status_code == 401
    assert sign_with(again, device).status_code == 200
    failed = events(session, "account.second_step_failed")
    assert [e.data["kind"] for e in failed] == ["passkey", "passkey"]
    assert message(failed[0].action, None, None, failed[0].data) == (
        "Someone signing in as agnes from testclient gave a passkey that isn't theirs."
    )


def test_someone_elses_passkey_signs_no_one_in(
    client_for: Callable[[], TestClient],
) -> None:
    agnes = sign_up(client_for, "agnes")
    bram = sign_up(client_for, "bram")
    add_passkey(agnes)
    brams, _ = add_passkey(bram)
    fresh = client_for()
    password(fresh, "agnes")
    assert sign_with(fresh, brams).status_code == 401
    assert fresh.get("/auth/me").status_code == 401


def test_removing_a_passkey_asks_for_the_password_and_keeps_the_last_for_the_custodian(
    client_for: Callable[[], TestClient], session: Session, required: None
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    assert mina.client.get("/auth/me").json()["two_step_needed"] is True
    add_passkey(mina, "Phone")
    add_passkey(mina, "Laptop")
    assert mina.client.get("/auth/me").json()["two_step_needed"] is False
    phone, laptop = mina.client.get("/two-step").json()["passkeys"]

    wrong = mina.client.post(f"/two-step/passkeys/{phone['id']}/remove", json={"password": "x"})
    removed = mina.client.post(
        f"/two-step/passkeys/{phone['id']}/remove", json={"password": PASSWORD}
    )
    last = mina.client.post(
        f"/two-step/passkeys/{laptop['id']}/remove", json={"password": PASSWORD}
    )

    assert (wrong.status_code, removed.status_code, last.status_code) == (403, 204, 409)
    assert [p["name"] for p in mina.client.get("/two-step").json()["passkeys"]] == ["Laptop"]
    # Someone else's is no one's to remove.
    bram = sign_up(client_for, "bram")
    gone = bram.client.post(
        f"/two-step/passkeys/{laptop['id']}/remove", json={"password": PASSWORD}
    )
    assert gone.status_code == 404


# --- a troupe asking it of its staff -----------------------------------------------------


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> TroupeFixture:
    return TroupeFixture(client_for, session)


def ask(person: Person, troupe_id: str, required: bool = True) -> Any:
    return person.client.put(f"/troupes/{troupe_id}/staff-two-step", json={"required": required})


def test_the_lead_storyteller_asks_two_step_sign_in_of_the_staff(
    troupe: TroupeFixture, session: Session
) -> None:
    # The lead storyteller needs one of their own first, as it asks it of them too.
    refused = ask(troupe.lead, troupe.id)
    assert refused.status_code == 409
    assert "yourself first" in refused.json()["detail"]
    # Only the lead storyteller (or the custodian) asks it.
    assert ask(troupe.storyteller, troupe.id).status_code == 403
    add_passkey(troupe.lead)

    on = ask(troupe.lead, troupe.id)

    assert on.status_code == 200, on.text
    assert on.json()["required"] is True
    has = {s["user_id"]: s["two_step"] for s in on.json()["staff"]}
    assert has == {
        troupe.lead.id: True,
        troupe.storyteller.id: False,
        troupe.assistant.id: False,
        troupe.narrator.id: False,
    }
    # Each of the staff without one is sent to set it up; a player isn't.
    for staff in (troupe.storyteller, troupe.assistant, troupe.narrator):
        assert staff.client.get("/auth/me").json()["two_step_needed"] is True
        assert staff.client.get(f"/troupes/{troupe.id}").status_code == 403
    assert troupe.player.client.get("/auth/me").json()["two_step_needed"] is False
    state = troupe.narrator.client.get("/two-step").json()
    assert state["required_by"] == ["staff of Lords of the Night"]
    add_passkey(troupe.narrator)
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}").status_code == 200
    [event] = events(session, "troupe.staff_two_step")
    assert (event.level, str(event.troupe_id)) == ("notice", troupe.id)
    assert message(event.action, "Lead", None, event.data) == (
        "Lead set two-step sign-in for the troupe's staff: on."
    )

    # Turned off, no one is held to it.
    assert ask(troupe.lead, troupe.id, False).json()["required"] is False
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}").status_code == 200


def told(session: Session) -> dict[str, str]:
    """Who was told their troupe asks two-step sign-in of its staff, and what."""
    found = session.scalars(
        select(Notification).where(Notification.kind == "troupe.staff_two_step")
    )
    return {str(n.user_id): n.summary for n in found}


def test_the_staff_are_told_in_the_bell_as_their_troupe_starts_asking(
    troupe: TroupeFixture, session: Session
) -> None:
    add_passkey(troupe.lead)
    add_passkey(troupe.assistant)

    assert ask(troupe.lead, troupe.id).status_code == 200

    asked = "lead asked the troupe's staff to sign in with two steps."
    set_it_up = f"{asked} Set it up in Account › Sign-in and email: Horatio sends you there first."
    # Not the lead who turned it on, nor a player.
    assert told(session) == {
        troupe.storyteller.id: set_it_up,
        troupe.narrator.id: set_it_up,
        troupe.assistant.id: f"{asked} You have it set up already, so nothing changes for you.",
    }
    [item] = [
        i
        for i in troupe.assistant.client.get("/notifications").json()["items"]
        if i["kind"] == "troupe.staff_two_step"
    ]
    assert (item["troupe_name"], item["link"]) == ("Lords of the Night", "/account/sign-in")
    # Someone held reads it before they set one up (#1111), and it's still there after.
    assert any(
        i["summary"] == set_it_up
        for i in troupe.narrator.client.get("/notifications").json()["items"]
    )
    add_passkey(troupe.narrator)
    assert any(
        i["summary"] == set_it_up
        for i in troupe.narrator.client.get("/notifications").json()["items"]
    )

    # Turned off, no one is told; a setting already on tells no one again.
    assert ask(troupe.lead, troupe.id, False).status_code == 200
    assert ask(troupe.custodian, troupe.id, False).status_code == 200
    assert len(told(session)) == 3
    session.get_one(Troupe, uuid.UUID(troupe.id)).archived_at = datetime.now(UTC)
    session.flush()
    # An archived troupe asks nothing, so turning it on tells no one.
    ask(troupe.custodian, troupe.id)
    assert len(told(session)) == 3


def test_staff_held_to_it_may_read_their_bell_and_nothing_else_first(troupe: TroupeFixture) -> None:
    add_passkey(troupe.lead)
    assert ask(troupe.lead, troupe.id).status_code == 200
    narrator = troupe.narrator.client
    assert narrator.get("/auth/me").json()["two_step_needed"] is True

    # The bell, its count and marking read answer them (#1111).
    bell = narrator.get("/notifications")
    assert bell.status_code == 200, bell.text
    [item] = [i for i in bell.json()["items"] if i["kind"] == "troupe.staff_two_step"]
    assert item["read"] is False
    waiting = bell.json()["count"]
    assert waiting >= 1
    read = narrator.post("/notifications/read", json={"ids": [item["id"]]})
    assert read.status_code == 204
    assert narrator.get("/notifications").json()["count"] == waiting - 1
    assert narrator.post("/notifications/read", json={}).status_code == 204

    # Nothing else: not the bell's settings, nor the troupe and pages its notices link to.
    for refused in (
        narrator.get("/notification-settings"),
        narrator.put("/notification-settings", json={}),
        narrator.get("/preferences"),
        narrator.get(f"/troupes/{troupe.id}"),
        narrator.get("/characters"),
        narrator.get("/troupes"),
    ):
        assert refused.status_code == 403
        assert refused.json()["detail"] == two_step.NEEDED


def test_only_reading_the_bell_is_allowed_first_of_the_notifications() -> None:
    allowed = {
        (method, route.path)
        for route in iter_route_contexts(app.routes)
        if route.endpoint in two_step.ALLOWED_FIRST
        and (route.path or "").startswith(("/api/notification", "/api/preferences"))
        for method in route.methods or ()
    }
    assert allowed == {("GET", "/api/notifications"), ("POST", "/api/notifications/read")}


def test_staff_of_two_troupes_need_it_if_either_asks(
    troupe: TroupeFixture, session: Session, client_for: Callable[[], TestClient]
) -> None:
    other = troupe.custodian.client.post(
        "/troupes", json={"name": "Court of Owls", "lead_handle": troupe.storyteller.handle}
    )
    assert other.status_code == 201, other.text
    other_id = other.json()["id"]
    troupe.storyteller.client.put(
        f"/troupes/{other_id}/staff", json={"handle": troupe.narrator.handle, "role": "narrator"}
    )
    # The custodian may ask it of a troupe's staff, without one of their own.
    assert ask(troupe.custodian, other_id).status_code == 200

    assert troupe.narrator.client.get("/two-step").json()["required_by"] == [
        "staff of Court of Owls"
    ]
    # Their one sign-in reaches both troupes, so the one that doesn't ask is held too.
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}").status_code == 403
    # An archived troupe asks nothing.
    session.get_one(Troupe, uuid.UUID(other_id)).archived_at = datetime.now(UTC)
    session.flush()
    assert troupe.narrator.client.get(f"/troupes/{troupe.id}").status_code == 200
