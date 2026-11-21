"""Two-step sign-in (#1057): setting up an authenticator app, signing in with it or a
recovery code, its limits, and who must have one."""

import base64
import smtplib
import uuid
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pyotp.totp import TOTP
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import audit, notification_choices
from horatio.api import auth as auth_api
from horatio.api.roster import message
from horatio.app import app
from horatio.auth import two_step
from horatio.config import get_settings
from horatio.connectors import email
from horatio.models import (
    AuditEvent,
    AuthenticatorApp,
    Notification,
    RecoveryCode,
    SecondStepSignIn,
    User,
)
from tests.api_helpers import PASSWORD, Person, sign_up
from tests.test_email_connector import FakeSMTP, text_of

START = 1_800_000_000.0


class Clock:
    """The time two-step sign-in reads, moved on by the test."""

    def __init__(self) -> None:
        self.at = START

    def step(self, steps: int = 1) -> None:
        self.at += 30 * steps


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(two_step, "now", lambda: clock.at)
    return clock


@pytest.fixture
def required(monkeypatch: pytest.MonkeyPatch) -> None:
    """The custodian must have a second step, as in production."""
    monkeypatch.setattr(get_settings(), "two_step_for_custodians", True)


@pytest.fixture
def limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "auth_limits", True)


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch, session: Session) -> Iterator[FakeSMTP]:
    """Email set up against a fake mail server. What goes after the response goes in
    a session of its own: here, the test's."""
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    monkeypatch.setattr(auth_api, "background_session", lambda: nullcontext(session))
    yield fake


def no_email_wanted(session: Session, person: Person) -> None:
    """Turn off every notification email they can turn off."""
    user = session.get_one(User, uuid.UUID(person.id))
    user.preferences = {
        t.setting("email"): False for t in notification_choices.TOPICS if t.choosable("email")
    }
    session.flush()


def bell(session: Session, person: Person, kind: str) -> list[str]:
    return list(
        session.scalars(
            select(Notification.summary).where(
                Notification.user_id == uuid.UUID(person.id), Notification.kind == kind
            )
        )
    )


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


def code(secret: str, clock: Clock) -> str:
    return TOTP(secret).at(int(clock.at))


def set_up_app(person: Person, clock: Clock) -> tuple[str, list[str]]:
    """Set up an authenticator app for `person`: its secret, and their recovery codes."""
    started = person.client.post("/two-step/app", json={"password": PASSWORD})
    assert started.status_code == 200, started.text
    secret = started.json()["secret"]
    confirmed = person.client.post("/two-step/app/confirm", json={"code": code(secret, clock)})
    assert confirmed.status_code == 200, confirmed.text
    # A code works once: the next sign-in takes the next one.
    clock.step()
    return secret, confirmed.json()["recovery_codes"]


def password(client: TestClient, login: str, typed: str = PASSWORD) -> Any:
    return client.post("/auth/login", json={"login": login, "password": typed})


def second(client: TestClient, given: str) -> Any:
    return client.post("/auth/second-step", json={"code": given})


def events(session: Session, action: str) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == action)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def said(event: AuditEvent) -> str:
    return message(event.action, None, None, event.data)


# --- setting it up -----------------------------------------------------------------------


def test_setting_up_an_authenticator_app_gives_recovery_codes_and_keeps_the_secret_sealed(
    client_for: Callable[[], TestClient], session: Session, clock: Clock
) -> None:
    agnes = sign_up(client_for, "agnes")
    assert agnes.client.get("/two-step").json() == {
        "app": False,
        "apps_available": True,
        "passkeys": [],
        "passkeys_available": True,
        "recovery_codes_left": 0,
        "required_by": [],
        "needed": False,
        "has_password": True,
        "can_confirm_with_discord": False,
        "confirmed_until": None,
    }

    started = agnes.client.post("/two-step/app", json={"password": PASSWORD}).json()
    assert started["uri"].startswith("otpauth://totp/Horatio:%40agnes?secret=")
    assert "issuer=Horatio" in started["uri"]
    # Not on until a code from it is given; a wrong one is refused.
    assert agnes.client.get("/two-step").json()["app"] is False
    wrong = agnes.client.post("/two-step/app/confirm", json={"code": "000000"})
    assert wrong.status_code == 422
    assert "isn't right" in wrong.json()["detail"]

    confirmed = agnes.client.post(
        "/two-step/app/confirm", json={"code": code(started["secret"], clock)}
    )
    assert confirmed.status_code == 200, confirmed.text
    codes = confirmed.json()["recovery_codes"]
    assert len(codes) == len(set(codes)) == 10
    assert all(len(c) == 11 and c[5] == "-" for c in codes)
    assert agnes.client.get("/two-step").json()["app"] is True
    assert agnes.client.get("/two-step").json()["recovery_codes_left"] == 10
    # Starting again is refused while one is on.
    assert agnes.client.post("/two-step/app", json={"password": PASSWORD}).status_code == 409

    # The secret is sealed with the server's key, for this account only, and the
    # recovery codes are kept only as hashes.
    kept = session.scalars(select(AuthenticatorApp)).one()
    assert started["secret"].encode() not in kept.secret
    assert two_step.decrypt(kept.user_id, kept.secret) == started["secret"]
    assert two_step.decrypt(uuid.uuid4(), kept.secret) is None
    hashes = set(session.scalars(select(RecoveryCode.code_hash)))
    assert not {c.replace("-", "") for c in codes} & hashes
    assert [e.data["kind"] for e in events(session, "account.two_step_added")] == ["app"]
    assert audit.level("account.two_step_added") == "notice"


def test_setting_up_an_app_asks_for_the_password_first_and_counts_towards_its_limit(
    client_for: Callable[[], TestClient], session: Session, limits: None
) -> None:
    agnes = sign_up(client_for, "agnes")
    wrong = {"password": "not my password"}

    # A wrong password shows no secret, and leaves nothing being set up.
    refused = agnes.client.post("/two-step/app", json=wrong)
    assert (refused.status_code, refused.json()) == (403, {"detail": "That's not your password."})
    assert session.scalars(select(AuthenticatorApp)).all() == []
    # Every try counts, right or wrong, with the other password tries at the account:
    # 10 in a quarter of an hour.
    for _ in range(8):
        agnes.client.post("/two-step/app", json=wrong)
    assert agnes.client.post("/two-step/app", json={"password": PASSWORD}).status_code == 200

    held = agnes.client.post("/two-step/app", json={"password": PASSWORD})
    assert (held.status_code, held.json()["detail"]) == (
        429,
        "Too many tries at your password. Try again later.",
    )
    change = {"current": PASSWORD, "password": "a new password 123"}
    assert agnes.client.post("/auth/password", json=change).status_code == 429
    [event] = events(session, "account.password_change_throttled")
    assert event.data["kind"] == "two_step"


def test_without_the_servers_key_only_passkeys_can_be_set_up(
    client_for: Callable[[], TestClient],
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    required: None,
) -> None:
    monkeypatch.setattr(get_settings(), "totp_key", None)
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    assert mina.client.post("/two-step/app", json={"password": PASSWORD}).status_code == 409
    state = mina.client.get("/two-step").json()
    assert (state["apps_available"], state["passkeys_available"], state["needed"]) == (
        False,
        True,
        True,
    )
    # With neither, there's no way to set one up, so no one is held to it.
    monkeypatch.setattr(get_settings(), "public_url", "http://horatio.example")
    state = mina.client.get("/two-step").json()
    assert (state["passkeys_available"], state["needed"]) == (False, False)
    assert mina.client.get("/troupes").status_code == 200


def test_a_secret_sealed_with_another_key_signs_no_one_in(
    client_for: Callable[[], TestClient], monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> None:
    agnes = sign_up(client_for, "agnes")
    secret, _ = set_up_app(agnes, clock)
    other = base64.urlsafe_b64encode(b"another key, thirty-two bytes!!!").decode()
    monkeypatch.setattr(get_settings(), "totp_key", other)
    fresh = client_for()
    assert password(fresh, "agnes").status_code == 202
    assert second(fresh, code(secret, clock)).status_code == 401


# --- signing in --------------------------------------------------------------------------


def test_a_password_alone_gives_no_session_once_there_is_a_second_step(
    client_for: Callable[[], TestClient], session: Session, clock: Clock
) -> None:
    audit.save_settings(session, audit.LogSettings(record="debug", sign_in_ips=False))
    agnes = sign_up(client_for, "agnes")
    secret, _ = set_up_app(agnes, clock)
    fresh = client_for()

    asked = password(fresh, "agnes")

    assert asked.status_code == 202
    assert asked.json() == {"second_step": ["app", "recovery_code"]}
    assert fresh.get("/auth/me").status_code == 401
    assert fresh.get("/troupes").status_code == 401
    assert fresh.get("/auth/second-step").json() == {"second_step": ["app", "recovery_code"]}
    # A wrong password is still just a wrong password.
    assert password(client_for(), "agnes", "not my password").status_code == 401

    signed_in = second(fresh, code(secret, clock))

    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["handle"] == "agnes"
    assert fresh.get("/auth/me").json()["handle"] == "agnes"
    assert session.scalars(select(SecondStepSignIn)).all() == []
    # Signed in, the waiting sign-in is gone: nothing to give a second code to.
    assert fresh.get("/auth/second-step").status_code == 410
    assert events(session, "account.second_step_asked")
    [event] = events(session, "account.signed_in")
    assert said(event) == "Someone signed in, with their authenticator app."


def test_a_code_works_once_and_only_near_its_time(
    client_for: Callable[[], TestClient], clock: Clock
) -> None:
    agnes = sign_up(client_for, "agnes")
    secret, _ = set_up_app(agnes, clock)
    first = client_for()
    password(first, "agnes")
    given = code(secret, clock)
    assert second(first, given).status_code == 200

    # The same code again, even within its 30 seconds, is refused.
    again = client_for()
    password(again, "agnes")
    assert second(again, given).status_code == 401
    # A code from two steps ago or ahead is too far out; one step either side will do.
    clock.step()
    assert second(again, TOTP(secret).at(int(clock.at), counter_offset=-2)).status_code == 401
    assert second(again, TOTP(secret).at(int(clock.at), counter_offset=2)).status_code == 401
    assert second(again, TOTP(secret).at(int(clock.at), counter_offset=1)).status_code == 200


def test_five_wrong_codes_end_the_sign_in_and_each_is_logged(
    client_for: Callable[[], TestClient], session: Session, clock: Clock
) -> None:
    agnes = sign_up(client_for, "agnes")
    secret, _ = set_up_app(agnes, clock)
    fresh = client_for()
    password(fresh, "agnes")

    answers = [second(fresh, "123456") for _ in range(5)]

    assert [a.status_code for a in answers] == [401, 401, 401, 401, 410]
    assert answers[0].json()["detail"] == "That code isn't right."
    assert answers[4].json()["detail"] == "Too many wrong tries. Sign in again."
    # Even the right code is no good now: sign in again.
    assert second(fresh, code(secret, clock)).status_code == 410
    failed = events(session, "account.second_step_failed")
    assert len(failed) == 5
    assert audit.level("account.second_step_failed") == "info"
    assert said(failed[0]) == (
        "Someone signing in as agnes from testclient gave a wrong code from an authenticator app."
    )
    assert password(fresh, "agnes").status_code == 202
    assert second(fresh, code(secret, clock)).status_code == 200


def test_a_recovery_code_signs_in_once(
    client_for: Callable[[], TestClient], session: Session, clock: Clock
) -> None:
    agnes = sign_up(client_for, "agnes")
    _, codes = set_up_app(agnes, clock)
    fresh = client_for()
    password(fresh, "agnes")

    # However it is typed.
    signed_in = second(fresh, f"  {codes[3].upper().replace('-', ' ')} ")

    assert signed_in.status_code == 200, signed_in.text
    assert agnes.client.get("/two-step").json()["recovery_codes_left"] == 9
    [used] = events(session, "account.recovery_code_used")
    assert said(used) == "Someone signed in with a recovery code from testclient: 9 left."
    assert audit.level("account.recovery_code_used") == "notice"
    again = client_for()
    password(again, "agnes")
    refused = second(again, codes[3])
    assert refused.status_code == 401
    assert refused.json()["detail"] == "That recovery code isn't right, or has been used."


def test_a_recovery_code_used_is_in_the_bell_and_emailed_whatever_they_chose(
    client_for: Callable[[], TestClient], session: Session, clock: Clock, mail: FakeSMTP
) -> None:
    agnes = sign_up(client_for, "agnes")
    secret, codes = set_up_app(agnes, clock)
    no_email_wanted(session, agnes)
    fresh = client_for()
    password(fresh, "agnes")

    assert second(fresh, codes[0]).status_code == 200

    assert bell(session, agnes, "account.recovery_code_used") == [
        "Someone signed in to your account with one of your recovery codes: 9 left. If it"
        " wasn't you, change your password and make new recovery codes."
    ]
    [sent] = mail.sent
    assert sent["To"] == f"agnes <{agnes.email}>"
    assert sent["Subject"] == "A recovery code was used to sign in to Horatio"
    text = text_of(sent)
    # What happened and when, in their time zone (UTC until they choose one).
    assert (
        f"signed in to your Horatio account ({agnes.email}) with one of your recovery codes on"
        in text
    )
    assert "(UTC). That code is used now: you have 9 left." in text
    assert "If it wasn't you, someone has your password" in text
    assert "contact the custodian at once" in text
    assert "http://localhost:5173/account/sign-in" in text
    # An app's code tells no one.
    again = client_for()
    password(again, "agnes")
    clock.step()
    assert second(again, code(secret, clock)).status_code == 200
    assert len(mail.sent) == 1


def test_new_recovery_codes_take_the_place_of_the_old_and_ask_for_the_password(
    client_for: Callable[[], TestClient], clock: Clock
) -> None:
    agnes = sign_up(client_for, "agnes")
    assert (
        agnes.client.post("/two-step/recovery-codes", json={"password": PASSWORD}).status_code
        == 409
    )
    _, old = set_up_app(agnes, clock)
    assert (
        agnes.client.post("/two-step/recovery-codes", json={"password": "nope"}).status_code == 403
    )

    new = agnes.client.post("/two-step/recovery-codes", json={"password": PASSWORD})

    assert len(new.json()["recovery_codes"]) == 10
    fresh = client_for()
    password(fresh, "agnes")
    assert second(fresh, old[0]).status_code == 401
    assert second(fresh, new.json()["recovery_codes"][0]).status_code == 200


def test_a_reset_link_sets_the_password_but_still_asks_for_the_second_step(
    client_for: Callable[[], TestClient], session: Session, clock: Clock
) -> None:
    custodian = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    secret, _ = set_up_app(agnes, clock)
    link = custodian.client.post(f"/players/{agnes.id}/password-reset").json()["url"]
    fresh = client_for()

    reset = fresh.post(
        "/auth/reset", json={"token": link.rsplit("/", 1)[1], "password": "a new password!"}
    )

    assert reset.status_code == 202, reset.text
    assert fresh.get("/auth/me").status_code == 401
    # The old sign-in is over, as for any reset.
    assert agnes.client.get("/auth/me").status_code == 401
    assert second(fresh, code(secret, clock)).status_code == 200
    assert password(client_for(), "agnes", "a new password!").status_code == 202


def test_a_suspended_account_gets_no_second_step_to_give(
    client_for: Callable[[], TestClient], session: Session, clock: Clock
) -> None:
    custodian = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    set_up_app(agnes, clock)
    custodian.client.post(f"/players/{agnes.id}/suspension", json={"reason": "Harassment"})

    refused = password(client_for(), "agnes")

    assert refused.status_code == 403
    assert "suspended" in refused.json()["detail"]
    assert session.scalars(select(SecondStepSignIn)).all() == []


# --- limits ------------------------------------------------------------------------------


def test_wrong_codes_are_limited_at_the_account_from_anywhere(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    session: Session,
    clock: Clock,
    limits: None,
) -> None:
    custodian = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    secret, _ = set_up_app(agnes, clock)

    # Ten wrong codes, spread over five addresses, two from each.
    for n in range(5):
        guesser = at(f"198.51.100.{n + 1}")
        assert password(guesser, "agnes").status_code == 202
        assert [second(guesser, "000000").status_code for _ in range(2)] == [401, 401]
    elsewhere = at("203.0.113.9")
    assert password(elsewhere, "agnes").status_code == 202
    held = second(elsewhere, code(secret, clock))

    assert held.status_code == 429
    assert held.json()["detail"] == "Too many wrong codes. Try again later, or ask the custodian."
    [event] = events(session, "account.second_step_throttled")
    assert event.data["limit"] == "wrong_codes_at_account"
    assert said(event).endswith("was turned away: too many wrong codes at the account.")
    # Again is debug.
    assert second(elsewhere, code(secret, clock)).status_code == 429
    assert audit.level("account.second_step_throttled_again") == "debug"

    # The custodian sees it, at the account rather than an address, and unblocks it.
    [shown] = [t for t in custodian.client.get("/throttled").json() if t["held"] == "second_step"]
    assert (shown["anywhere"], shown["login"], shown["address"]) == (True, "@agnes", None)
    assert shown["limit"] == "10 wrong second-step codes at one account in 15 minutes"
    unblocked = custodian.client.post("/throttled/unblock", json={"id": shown["id"]})
    assert unblocked.status_code == 204
    [lifted] = events(session, "account.throttle_lifted")
    assert said(lifted) == (
        "Someone unblocked second steps at @agnes: over the limit of 10 wrong second-step"
        " codes at one account in 15 minutes."
    )
    assert second(elsewhere, code(secret, clock)).status_code == 200


def test_wrong_codes_are_limited_from_one_address_too(
    client_for: Callable[[], TestClient],
    at: Callable[[str], TestClient],
    session: Session,
    clock: Clock,
    limits: None,
) -> None:
    people = [sign_up(client_for, f"player{n}") for n in range(3)]
    for person in people:
        set_up_app(person, clock)
    home = at("198.51.100.7")
    # Twenty wrong codes from one address, at three accounts: none over its own limit,
    # and none of the sign-ins given more than four.
    for person, wrong in ((0, 4), (0, 3), (1, 4), (1, 3), (2, 4), (2, 2)):
        assert password(home, people[person].handle).status_code == 202
        assert [second(home, "000000").status_code for _ in range(wrong)] == [401] * wrong

    held = second(home, "000000")

    assert held.status_code == 429
    [event] = events(session, "account.second_step_throttled")
    assert event.data["limit"] == "wrong_codes"


# --- who must have one -------------------------------------------------------------------


def test_the_custodian_is_sent_to_set_up_a_second_step_before_anything_else(
    client_for: Callable[[], TestClient], session: Session, clock: Clock, required: None
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)

    me = mina.client.get("/auth/me")
    refused = mina.client.get("/troupes")

    assert me.status_code == 200
    assert me.json()["two_step_needed"] is True
    assert refused.status_code == 403
    assert refused.json()["detail"] == two_step.NEEDED
    assert mina.client.get("/players").status_code == 403
    assert mina.client.get("/appearance").status_code == 200
    state = mina.client.get("/two-step").json()
    assert (state["required_by"], state["needed"]) == (["the custodian"], True)

    set_up_app(mina, clock)

    assert mina.client.get("/auth/me").json()["two_step_needed"] is False
    assert mina.client.get("/troupes").status_code == 200
    # The last second step stays while it's needed.
    kept = mina.client.post("/two-step/app/remove", json={"password": PASSWORD})
    assert kept.status_code == 409
    assert "as the custodian" in kept.json()["detail"]


def test_a_custodian_with_a_second_step_still_views_as_someone(
    client_for: Callable[[], TestClient], session: Session, clock: Clock, required: None
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    set_up_app(mina, clock)

    viewing = mina.client.post(f"/players/{agnes.id}/view-as", json={"reason": "A question"})

    assert viewing.status_code == 201, viewing.text
    me = mina.client.get("/auth/me").json()
    assert (me["handle"], me["two_step_needed"]) == ("agnes", False)
    assert mina.client.get("/troupes").status_code == 200
    assert mina.client.post("/view-as/stop").status_code == 204


def test_turning_off_the_app_asks_for_the_password_and_takes_the_recovery_codes(
    client_for: Callable[[], TestClient], session: Session, clock: Clock
) -> None:
    agnes = sign_up(client_for, "agnes")
    set_up_app(agnes, clock)
    assert agnes.client.post("/two-step/app/remove", json={"password": "nope"}).status_code == 403

    off = agnes.client.post("/two-step/app/remove", json={"password": PASSWORD})

    assert off.status_code == 204
    assert agnes.client.get("/two-step").json()["recovery_codes_left"] == 0
    assert password(client_for(), "agnes").status_code == 200
    assert [e.data["kind"] for e in events(session, "account.two_step_removed")] == ["app"]


# --- the custodian resets it -------------------------------------------------------------


def test_the_custodian_resets_a_lost_second_step_and_the_person_is_told(
    client_for: Callable[[], TestClient], session: Session, clock: Clock, mail: FakeSMTP
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    set_up_app(agnes, clock)
    assert next(p for p in mina.client.get("/players").json() if p["handle"] == "agnes")["two_step"]
    assert agnes.client.post(f"/two-step/reset/{agnes.id}", json={"reason": "x"}).status_code == 403

    reset = mina.client.post(f"/two-step/reset/{agnes.id}", json={"reason": "Lost her phone"})

    assert reset.status_code == 204
    assert password(client_for(), "agnes").status_code == 200
    assert agnes.client.get("/two-step").json()["recovery_codes_left"] == 0
    [event] = events(session, "account.two_step_reset")
    assert event.level == "notice"
    assert message(event.action, "Mina", None, event.data) == (
        "Mina reset agnes's two-step sign-in (Lost her phone)."
    )
    bell = agnes.client.get("/notifications").json()["items"]
    assert any("reset your two-step sign-in: Lost her phone" in i["summary"] for i in bell)
    # And by email, whatever they chose for other email.
    [sent] = mail.sent
    assert sent["To"] == f"agnes <{agnes.email}>"
    assert sent["Subject"] == "Your Horatio two-step sign-in was reset"
    text = text_of(sent)
    assert "mina, Horatio's custodian, reset two-step sign-in for your Horatio account" in text
    assert "(UTC): Lost her phone." in text
    assert "Your password alone does, until you set two-step sign-in up again" in text
    assert "If you didn't ask for this, contact the custodian at once" in text
    # Nothing left to reset.
    assert (
        mina.client.post(f"/two-step/reset/{agnes.id}", json={"reason": "again"}).status_code == 409
    )


def test_an_email_the_mail_server_refuses_is_logged_and_the_reset_stands(
    client_for: Callable[[], TestClient], session: Session, clock: Clock, mail: FakeSMTP
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    set_up_app(agnes, clock)
    mail.fail = smtplib.SMTPDataError(554, b"No such mailbox")

    reset = mina.client.post(f"/two-step/reset/{agnes.id}", json={"reason": "Lost her phone"})

    assert reset.status_code == 204
    assert agnes.client.get("/two-step").json()["app"] is False
    [failed] = events(session, two_step.EMAIL_FAILED)
    assert failed.level == "notice"
    assert said(failed) == (
        "Horatio could not email agnes that their two-step sign-in was reset: The mail server"
        " refused it (554): No such mailbox"
    )


def test_a_reset_on_the_server_is_in_the_bell_and_emailed(
    client_for: Callable[[], TestClient],
    session: Session,
    clock: Clock,
    mail: FakeSMTP,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agnes = sign_up(client_for, "agnes")
    set_up_app(agnes, clock)

    assert two_step.reset_by_server(session, agnes.email.upper()) == 0

    assert agnes.client.get("/two-step").json()["app"] is False
    assert capsys.readouterr().out == (
        f"{agnes.email.upper()} has no second step now, and can sign in with their password.\n"
        "They have been emailed about it.\n"
    )
    [event] = events(session, "account.two_step_reset")
    assert said(event) == "agnes's two-step sign-in was reset on the server."
    assert bell(session, agnes, "account.two_step_reset") == [two_step.RESET_ON_SERVER]
    [sent] = mail.sent
    assert (
        f"Two-step sign-in for your Horatio account ({agnes.email}) was reset on the server on"
        in text_of(sent)
    )
    assert two_step.reset_by_server(session, "nobody@example.com") == 1


def test_the_key_command_prints_a_key_for_production_env(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert two_step.main([]) == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith("HORATIO_TOTP_KEY=")
    assert len(base64.urlsafe_b64decode(line.split("=", 1)[1])) == 32
    assert two_step.main(["nonsense"]) == 2


def test_merging_accounts_forgets_the_merged_ones_second_steps(
    client_for: Callable[[], TestClient], session: Session, clock: Clock
) -> None:
    mina = sign_up(client_for, "mina", custodian=True, session=session)
    agnes = sign_up(client_for, "agnes")
    twice = sign_up(client_for, "agnes2")
    set_up_app(twice, clock)

    merged = mina.client.post(
        "/accounts/merge",
        json={"keep": agnes.handle, "merge": twice.handle, "reason": "Signed up twice"},
    )

    assert merged.status_code == 204, merged.text
    assert session.scalars(select(AuthenticatorApp)).all() == []
    assert session.scalars(select(RecoveryCode)).all() == []
    assert password(client_for(), agnes.email).status_code == 200
