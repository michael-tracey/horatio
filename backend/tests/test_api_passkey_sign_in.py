"""Signing in with a passkey alone, no password (#1098): its challenge, kept on the
server and working once, both steps at once, who is refused, and its limits.

The browser is played by the software authenticator of test_api_passkeys, keeping the
account's user handle with the passkey as a discoverable one does."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.api.roster import message
from horatio.app import app
from horatio.auth import passkeys
from horatio.config import get_settings
from horatio.models import AuditEvent, Passkey, PasskeySignIn, SecondStepSignIn, User
from tests.api_helpers import PASSWORD, Person, sign_up
from tests.test_api_passkeys import Authenticator, b64


class Device(Authenticator):
    """A passkey kept with its account, as a phone or password manager keeps one, which
    says so (credProps) when made, unless `says` is None."""

    def __init__(self, says: bool | None = True) -> None:
        super().__init__()
        self.says = says
        self.user_handle: str | None = None
        self.verified = True

    def create(self, options: dict[str, Any]) -> dict[str, Any]:
        self.user_handle = options["user"]["id"]
        made = super().create(options)
        if self.says is not None:
            made["clientExtensionResults"] = {"credProps": {"rk": self.says}}
        return made

    def flags_and_count(self, flags: int) -> bytes:
        # Present only, not verified, for a device that didn't ask for a face or PIN.
        return super().flags_and_count(flags if self.verified else flags & ~0x04)

    def get(self, options: dict[str, Any], *, count: int | None = None) -> dict[str, Any]:
        signed = super().get(options, count=count)
        signed["response"]["userHandle"] = self.user_handle
        return signed


@pytest.fixture
def required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "two_step_for_custodians", True)


@pytest.fixture
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
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


def add(person: Person, device: Device, name: str = "Phone") -> None:
    options = person.client.post("/two-step/passkeys/options")
    assert options.status_code == 200, options.text
    added = person.client.post(
        "/two-step/passkeys", json={"credential": device.create(options.json()), "name": name}
    )
    assert added.status_code == 200, added.text


def options(client: TestClient) -> dict[str, Any]:
    asked = client.post("/auth/passkey/options")
    assert asked.status_code == 200, asked.text
    return asked.json()


def answer(client: TestClient, credential: dict[str, Any]) -> Any:
    return client.post("/auth/passkey", json={"credential": credential})


def sign_in(client: TestClient, device: Device) -> Any:
    return answer(client, device.get(options(client)))


def events(session: Session, action: str) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def record_debug(custodian: Person) -> None:
    """Have the audit log keep debug events, such as signing in, as the custodian can."""
    body = {"record": "debug", "keep_debug": 30, "keep_info": 365, "sign_in_ips": True}
    assert custodian.client.put("/audit/settings", json=body).status_code == 200


def said(event: AuditEvent) -> str:
    return message(event.action, None, None, event.data)


def test_a_passkey_alone_signs_in_as_both_steps_even_where_two_step_is_required(
    client_for: Callable[[], TestClient], session: Session, required: None
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    device = Device()
    add(mina, device)
    record_debug(mina)
    fresh = client_for()

    asked = options(fresh)
    signed_in = answer(fresh, device.get(asked))

    # The options name no account, so the browser offers any passkey it keeps here, and
    # it must check the person's face, finger or PIN.
    assert "allowCredentials" not in asked or asked["allowCredentials"] == []
    assert asked["userVerification"] == "required"
    assert signed_in.status_code == 200, signed_in.text
    me = fresh.get("/auth/me").json()
    assert (me["handle"], me["two_step_needed"]) == ("mina", False)
    # No second step was asked for, and nothing is left waiting.
    assert session.scalars(select(SecondStepSignIn)).all() == []
    assert session.scalars(select(PasskeySignIn)).all() == []
    kept = session.scalars(select(Passkey)).one()
    assert (kept.sign_count, kept.last_used_at is not None) == (1, True)
    [event] = [e for e in events(session, "account.signed_in") if e.data.get("kind")]
    assert event.data["kind"] == "passkey_alone"
    assert message(event.action, "mina", None, event.data) == (
        "mina signed in from testclient with a passkey alone, no password."
    )
    # The password stays, and with it the second step.
    again = client_for().post("/auth/login", json={"login": "mina", "password": PASSWORD})
    assert again.status_code == 202


def test_the_challenge_is_kept_on_the_server_and_works_once(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    device = Device()
    add(agnes, device)
    fresh = client_for()

    # None asked for: nothing to sign.
    assert answer(fresh, device.get({"challenge": b64(b"made up")})).status_code == 410
    asked = options(fresh)
    [waiting] = session.scalars(select(PasskeySignIn)).all()
    assert waiting.expires_at - datetime.now(UTC) <= passkeys.CHALLENGE_FOR
    assert fresh.cookies.get(passkeys.COOKIE) is not None
    # A wrong answer uses it up as surely as a right one.
    wrong = answer(fresh, device.get({"challenge": b64(b"another")}))
    assert wrong.status_code == 401
    assert answer(fresh, device.get(asked)).status_code == 410
    assert session.scalars(select(PasskeySignIn)).all() == []

    # A right answer works once: given again, to a new challenge, it signs no one in.
    signed = device.get(options(fresh))
    assert answer(fresh, signed).status_code == 200
    replay = client_for()
    options(replay)
    assert answer(replay, signed).status_code == 401
    assert replay.get("/auth/me").status_code == 401

    # And for 5 minutes.
    late = client_for()
    asked = options(late)
    session.scalars(select(PasskeySignIn)).one().expires_at = datetime.now(UTC) - timedelta(
        seconds=1
    )
    session.flush()
    timed_out = answer(late, device.get(asked))
    assert timed_out.status_code == 410
    assert timed_out.json()["detail"] == "That took too long. Try again."


def test_only_a_verified_passkey_of_the_account_it_names_signs_in(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    record_debug(sign_up(client_for, "mina", custodian=True, session=session))
    agnes = sign_up(client_for, "agnes")
    bram = sign_up(client_for, "bram")
    device = Device()
    add(agnes, device)
    add(bram, Device())
    fresh = client_for()

    # Without the person's face, finger or PIN, a passkey is only one step.
    device.verified = False
    assert sign_in(fresh, device).status_code == 401
    device.verified = True
    # Claiming another account's user handle signs no one in.
    agnes_handle = device.user_handle
    device.user_handle = b64(uuid.UUID(bram.id).bytes)
    assert sign_in(fresh, device).status_code == 401
    device.user_handle = None
    assert sign_in(fresh, device).status_code == 401
    device.user_handle = agnes_handle
    # A passkey Horatio doesn't know.
    stranger = Device()
    stranger.user_handle = agnes_handle
    assert sign_in(fresh, stranger).status_code == 401

    assert fresh.get("/auth/me").status_code == 401
    failed = [e for e in events(session, "account.sign_in_failed")]
    assert [e.data["kind"] for e in failed] == ["passkey"] * 3 + ["passkey_unknown"]
    assert said(failed[0]) == (
        "Someone failed to sign in as agnes from testclient with a passkey: it didn't check out."
    )
    assert said(failed[-1]) == (
        "Someone failed to sign in from testclient with a passkey no account here has."
    )
    assert sign_in(fresh, device).status_code == 200


def test_a_suspended_or_merged_account_is_refused(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    twice = sign_up(client_for, "agnes2")
    agnes_device, twice_device = Device(), Device()
    add(agnes, agnes_device)
    add(twice, twice_device)
    mina.client.post(f"/players/{agnes.id}/suspension", json={"reason": "Harassment"})

    suspended = sign_in(client_for(), agnes_device)

    assert suspended.status_code == 403
    assert "suspended" in suspended.json()["detail"]
    # A merge forgets the merged account's passkeys; one left over still signs no one in.
    session.get_one(User, uuid.UUID(twice.id)).merged_into_id = uuid.UUID(agnes.id)
    session.flush()
    merged = client_for()
    assert sign_in(merged, twice_device).status_code == 401
    assert merged.get("/auth/me").status_code == 401


def test_whether_a_passkey_can_sign_in_alone_is_kept_and_learnt(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    agnes = sign_up(client_for, "agnes")
    older, kept_alone, second_only = Device(says=None), Device(), Device(says=False)
    add(agnes, older, "Older")
    add(agnes, kept_alone, "Phone")
    add(agnes, second_only, "Key")

    state = agnes.client.get("/two-step").json()
    assert {p["name"]: p["discoverable"] for p in state["passkeys"]} == {
        "Older": None,
        "Phone": True,
        "Key": False,
    }
    # Asked to say, and only those known to sign in alone are kept from being made
    # again: a device holding another may make a new one in its place.
    adding = agnes.client.post("/two-step/passkeys/options").json()
    assert adding["extensions"] == {"credProps": True}
    assert adding["authenticatorSelection"]["residentKey"] == "preferred"
    assert [c["id"] for c in adding["excludeCredentials"]] == [b64(kept_alone.id)]
    # One that signs in alone is discoverable after all.
    assert sign_in(client_for(), older).status_code == 200
    state = agnes.client.get("/two-step").json()
    assert {p["name"]: p["discoverable"] for p in state["passkeys"]}["Older"] is True


# --- replacing one that may not sign in alone (#1110) ---------------------------------------


def replacing(person: Person, passkey_id: str) -> dict[str, Any]:
    asked = person.client.post(f"/two-step/passkeys/{passkey_id}/replace/options")
    assert asked.status_code == 200, asked.text
    return asked.json()


def replace(person: Person, passkey_id: str, credential: dict[str, Any]) -> Any:
    return person.client.post(
        f"/two-step/passkeys/{passkey_id}/replace", json={"credential": credential}
    )


def test_a_passkey_that_may_not_sign_in_alone_is_replaced_by_one_that_does(
    client_for: Callable[[], TestClient], session: Session, required: None
) -> None:
    # The custodian must have a second step, and this is their only one.
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    older = Device(says=None)
    add(mina, older, "Older")
    [old] = mina.client.get("/two-step").json()["passkeys"]

    asked = replacing(mina, old["id"])
    # The device must make one that signs in alone, or make none.
    assert asked["authenticatorSelection"]["residentKey"] == "required"
    assert asked["authenticatorSelection"]["userVerification"] == "required"
    assert asked["extensions"] == {"credProps": True}
    # A device saying nothing of it was told to make it so: it is.
    phone = Device(says=None)
    replaced = replace(mina, old["id"], phone.create(asked))

    assert replaced.status_code == 200, replaced.text
    assert (replaced.json()["name"], replaced.json()["discoverable"]) == ("Older", True)
    state = mina.client.get("/two-step").json()
    assert [(p["id"], p["name"]) for p in state["passkeys"]] == [(replaced.json()["id"], "Older")]
    assert state["recovery_codes_left"] == 10
    assert mina.client.get("/auth/me").json()["two_step_needed"] is False
    assert session.scalars(select(Passkey.credential_id)).all() == [phone.id]
    # The new one signs in alone; the old one signs no one in.
    assert sign_in(client_for(), phone).status_code == 200
    assert sign_in(client_for(), older).status_code == 401
    [event] = events(session, "account.two_step_replaced")
    assert event.level == "notice"
    assert message(event.action, "Mina", None, event.data) == (
        "Mina replaced their passkey Older with a new one that signs in alone, with no password."
    )
    assert len(events(session, "account.two_step_added")) == 1
    assert events(session, "account.two_step_removed") == []


def test_a_cancelled_or_failed_replacement_leaves_the_old_passkey_as_it_was(
    client_for: Callable[[], TestClient], session: Session, required: None
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    add(mina, Device(says=False), "Key")
    [old] = mina.client.get("/two-step").json()["passkeys"]

    # Cancelled on the device: nothing comes back, and nothing changes.
    replacing(mina, old["id"])
    # A device that can't keep one that signs in alone, or didn't check the person's
    # face, finger or PIN, or one made for another site.
    still_not = Device(says=False)
    unverified = Device()
    unverified.verified = False
    elsewhere = Device()
    elsewhere.origin = "https://evil.example"
    refused = {
        name: replace(mina, old["id"], device.create(replacing(mina, old["id"])))
        for name, device in (("not", still_not), ("unverified", unverified), ("evil", elsewhere))
    }

    assert {k: r.status_code for k, r in refused.items()} == {
        "not": 422,
        "unverified": 422,
        "evil": 422,
    }
    assert refused["not"].json()["detail"] == (
        "This device can't keep a passkey that signs you in alone."
    )
    state = mina.client.get("/two-step").json()
    assert [p["id"] for p in state["passkeys"]] == [old["id"]]
    assert mina.client.get("/auth/me").json()["two_step_needed"] is False
    assert events(session, "account.two_step_replaced") == []


def test_only_ones_own_passkey_that_may_not_sign_in_alone_is_replaced(
    client_for: Callable[[], TestClient],
) -> None:
    agnes = sign_up(client_for, "agnes")
    bram = sign_up(client_for, "bram")
    phone, older = Device(), Device(says=None)
    add(agnes, phone, "Phone")
    add(agnes, older, "Older")
    by_name = {p["name"]: p["id"] for p in agnes.client.get("/two-step").json()["passkeys"]}

    # One that signs in alone already needs no replacing.
    already = agnes.client.post(f"/two-step/passkeys/{by_name['Phone']}/replace/options")
    assert (already.status_code, already.json()["detail"]) == (
        409,
        "Phone signs you in alone already.",
    )
    # Someone else's is no one's to replace.
    brams = bram.client.post(f"/two-step/passkeys/{by_name['Older']}/replace/options")
    assert brams.status_code == 404
    asked = replacing(agnes, by_name["Older"])
    taken = replace(bram, by_name["Older"], Device().create(asked))
    assert taken.status_code == 404
    # The device keeping the old one may make the new: only Phone is kept from it.
    assert [c["id"] for c in asked["excludeCredentials"]] == [b64(phone.id)]
    names = [p["name"] for p in agnes.client.get("/two-step").json()["passkeys"]]
    assert names == ["Phone", "Older"]


def test_passkey_sign_ins_are_limited_from_one_address(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    session: Session,
    limits: None,
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    device = Device()
    add(agnes, device)
    venue = at("198.51.100.7")
    device.verified = False
    for _ in range(5):
        assert sign_in(venue, device).status_code == 401
    device.verified = True

    held = sign_in(venue, device)

    assert held.status_code == 429
    assert held.json()["detail"].startswith("Too many failed sign-ins from here.")
    [event] = events(session, "account.sign_in_throttled")
    assert (event.data["kind"], event.data["limit"]) == ("passkey", "failed_at_login")
    assert said(event) == (
        "Someone was turned away from signing in with a passkey from 198.51.100.7: too many"
        " failed sign-ins from where they were."
    )
    # Counted at a login of their own: a password from there still signs in, and a passkey
    # from elsewhere.
    password = venue.post("/auth/login", json={"login": "mina", "password": PASSWORD})
    assert password.status_code == 200
    assert sign_in(at("203.0.113.9"), device).status_code == 200

    # The custodian sees it as at "a passkey", and unblocks it.
    [shown] = [t for t in mina.client.get("/throttled").json() if t["per_login"]]
    assert shown["login"] == "a passkey"
    assert mina.client.post("/throttled/unblock", json={"id": shown["id"]}).status_code == 204
    assert sign_in(venue, device).status_code == 200


def test_one_place_can_keep_only_so_many_challenges_waiting(
    at: Callable[[str], TestClient],
    session: Session,
    limits: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(passkeys, "WAITING_FROM_ONE_PLACE", 3)
    venue = at("198.51.100.7")
    for _ in range(3):
        options(venue)

    assert venue.post("/auth/passkey/options").status_code == 429
    assert at("203.0.113.9").post("/auth/passkey/options").status_code == 200
    # Those timed out make room again.
    for waiting in session.scalars(select(PasskeySignIn)):
        waiting.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()
    assert venue.post("/auth/passkey/options").status_code == 200
