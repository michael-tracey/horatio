"""Password resets from the Custodian menu, and "Forgot your password?": what is
emailed, what is never given away, how often a link may be asked for, and the log."""

import re
import smtplib
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from horatio.api import auth as auth_api
from horatio.auth import resets
from horatio.config import get_settings
from horatio.connectors import email
from horatio.models import AuditEvent
from tests.api_helpers import PASSWORD, Person, sign_up
from tests.test_email_connector import FakeSMTP

ON_ITS_WAY = {
    "message": "If an account uses that address, a reset link is on its way. "
    "It works once, for the next 24 hours."
}


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    return sign_up(client_for, "custodian", custodian=True, session=session)


@pytest.fixture
def player(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "player")


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch, session: Session) -> Iterator[FakeSMTP]:
    """Email set up against a fake mail server. The links people ask for are sent
    after the response, in a session of their own: here, the test's."""
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    monkeypatch.setattr(auth_api, "background_session", lambda: nullcontext(session))
    yield fake


def forgot(client: TestClient, address: str) -> Any:
    return client.post("/auth/forgot", json={"email": address})


def link_in(message: EmailMessage) -> str:
    """The token from the reset link an email holds."""
    found = re.search(r"http://localhost:5173/reset-password/(\S+)", message.get_content())
    assert found, message.get_content()
    return found.group(1)


def events(session: Session, action: str) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
        )
    )


def actions(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.action.startswith("account."))
            .order_by(AuditEvent.id)
        )
    )


def an_hour_later(session: Session) -> None:
    """Move every request back in time, past the short limits but within the day."""
    session.execute(
        update(AuditEvent)
        .where(AuditEvent.action == resets.REQUESTED)
        .values(created_at=AuditEvent.created_at - timedelta(hours=1))
    )
    session.flush()


def sign_in(client: TestClient, address: str, password: str) -> int:
    return client.post("/auth/login", json={"login": address, "password": password}).status_code


# --- forgot your password ----------------------------------------------------------------------


def test_without_email_the_page_says_to_ask_the_custodian(
    client_for: Callable[[], TestClient], player: Person, session: Session
) -> None:
    anyone = client_for()

    assert anyone.get("/auth/forgot").json() == {"can_email": False}
    response = forgot(anyone, player.email)
    assert response.status_code == 503
    assert "ask the custodian" in response.json()["detail"]
    assert actions(session) == []


def test_known_and_unknown_addresses_get_the_same_answer(
    client_for: Callable[[], TestClient], player: Person, session: Session, mail: FakeSMTP
) -> None:
    anyone = client_for()
    assert anyone.get("/auth/forgot").json() == {"can_email": True}

    known = forgot(anyone, player.email)
    unknown = forgot(anyone, "nobody@example.com")

    assert (known.status_code, known.json()) == (202, ON_ITS_WAY)
    assert (unknown.status_code, unknown.json()) == (202, ON_ITS_WAY)
    assert set(known.headers) == set(unknown.headers)
    # Only the account's own address gets an email.
    assert [m["To"] for m in mail.sent] == [f"player <{player.email}>"]
    assert mail.sent[0]["Subject"] == "Reset your Horatio password"
    assert "hopefully you" in mail.sent[0].get_content()
    # Both requests are logged, for the custodian.
    requested = events(session, "account.reset_requested")
    assert [(e.actor_id is not None, e.data["email"]) for e in requested] == [
        (True, player.email),
        (False, "nobody@example.com"),
    ]
    assert requested[0].data["ip"] == "testclient"
    assert requested[1].data["kind"] == "unknown"


def test_an_emailed_link_works_once_and_signs_out_everywhere(
    client_for: Callable[[], TestClient], player: Person, session: Session, mail: FakeSMTP
) -> None:
    # Addresses are matched whatever their case.
    assert forgot(client_for(), player.email.upper()).status_code == 202
    token = link_in(mail.sent[0])
    fresh = client_for()

    reset = fresh.post("/auth/reset", json={"token": token, "password": "a new password!"})

    assert reset.status_code == 200, reset.text
    assert fresh.get("/auth/me").json()["id"] == player.id
    assert player.client.get("/auth/me").status_code == 401
    assert sign_in(client_for(), player.email, PASSWORD) == 401
    again = client_for().post("/auth/reset", json={"token": token, "password": "another one!!"})
    assert again.status_code == 404
    assert again.json()["detail"] == "This reset link has expired or been used. Ask for a new one."
    assert actions(session) == [
        "account.reset_requested",
        "account.reset_sent",
        "account.password_reset",
    ]
    assert events(session, "account.reset_sent")[0].data["kind"] == "self"


def test_asking_again_cancels_the_earlier_link(
    client_for: Callable[[], TestClient], player: Person, session: Session, mail: FakeSMTP
) -> None:
    forgot(client_for(), player.email)
    an_hour_later(session)
    forgot(client_for(), player.email)

    first, second = (link_in(m) for m in mail.sent)
    assert client_for().get(f"/auth/reset/{first}").status_code == 404
    assert client_for().get(f"/auth/reset/{second}").status_code == 200


def test_an_address_is_limited_whether_or_not_an_account_uses_it(
    client_for: Callable[[], TestClient], player: Person, session: Session, mail: FakeSMTP
) -> None:
    anyone = client_for()
    forgot(anyone, player.email)
    forgot(anyone, "nobody@example.com")

    known = forgot(anyone, player.email)
    unknown = forgot(anyone, "nobody@example.com")

    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json() == {"detail": resets.ADDRESS_WAIT}
    # Turned away, nothing is sent or logged.
    assert len(mail.sent) == 1
    assert len(events(session, "account.reset_requested")) == 2
    # A few minutes on, they may ask again; but only a handful of times a day.
    for _ in range(4):
        an_hour_later(session)
        assert forgot(anyone, player.email).status_code == 202
    an_hour_later(session)
    assert forgot(anyone, player.email).status_code == 429
    assert len(mail.sent) == 5


def test_one_ip_address_is_limited_however_many_addresses_it_tries(
    client_for: Callable[[], TestClient], session: Session, mail: FakeSMTP
) -> None:
    anyone = client_for()
    for n in range(5):
        assert forgot(anyone, f"guess{n}@example.com").status_code == 202

    response = forgot(anyone, "guess5@example.com")

    assert response.status_code == 429
    assert response.json() == {"detail": resets.IP_WAIT}
    for n in range(6, 21):
        an_hour_later(session)
        forgot(anyone, f"guess{n}@example.com")
    an_hour_later(session)
    assert forgot(anyone, "one-more@example.com").json() == {"detail": resets.IP_WAIT}


def test_a_refused_email_is_logged_and_the_answer_is_the_same(
    client_for: Callable[[], TestClient], player: Person, session: Session, mail: FakeSMTP
) -> None:
    mail.fail = smtplib.SMTPResponseException(550, b"No such mailbox")

    response = forgot(client_for(), player.email)

    assert (response.status_code, response.json()) == (202, ON_ITS_WAY)
    failed = events(session, "account.reset_email_failed")
    assert "No such mailbox" in failed[0].data["error"]


# --- the custodian ---------------------------------------------------------------------------


def test_the_custodian_has_horatio_email_the_link(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session,
    mail: FakeSMTP,
) -> None:  # fmt: skip
    response = custodian.client.post(f"/players/{player.id}/password-reset", json={"email": True})

    assert response.status_code == 201, response.text
    link = response.json()
    assert link["emailed_to"] == player.email
    assert link["email_error"] is None
    assert link_in(mail.sent[0]) == link["url"].rsplit("/", 1)[1]
    assert "custodian, Horatio's custodian, made you a link" in mail.sent[0].get_content()
    assert actions(session) == ["account.reset_link", "account.reset_sent"]
    assert events(session, "account.reset_sent")[0].actor_id is not None


def test_the_custodian_is_told_when_the_email_fails(
    custodian: Person, player: Person, mail: FakeSMTP
) -> None:
    mail.fail = OSError("connection refused")

    response = custodian.client.post(f"/players/{player.id}/password-reset", json={"email": True})

    # The link is made all the same, to copy.
    assert response.status_code == 201
    assert response.json()["emailed_to"] is None
    assert "Could not reach the mail server" in response.json()["email_error"]


def test_without_email_the_custodian_copies_the_link(
    custodian: Person, player: Person, session: Session
) -> None:
    emailed = custodian.client.post(f"/players/{player.id}/password-reset", json={"email": True})
    copied = custodian.client.post(f"/players/{player.id}/password-reset", json={})

    assert emailed.status_code == 409
    assert copied.status_code == 201
    assert copied.json()["emailed_to"] is None
    assert actions(session) == ["account.reset_link"]


def test_the_custodian_sees_who_has_a_live_link(
    custodian: Person, player: Person, session: Session
) -> None:
    def summary() -> dict[str, Any]:
        found = custodian.client.get("/players", params={"q": "player"}).json()
        return next(p for p in found if p["id"] == player.id)

    assert summary()["reset_expires_at"] is None
    made = custodian.client.post(f"/players/{player.id}/password-reset").json()

    assert summary()["reset_expires_at"] == made["expires_at"]
    profile = custodian.client.get(f"/players/{player.id}").json()
    assert profile["reset_expires_at"] == made["expires_at"]
    # Nobody else sees it, not even the player.
    assert player.client.get(f"/players/{player.id}").json()["reset_expires_at"] is None


def test_the_custodian_cancels_a_link(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session
) -> None:
    url = custodian.client.post(f"/players/{player.id}/password-reset").json()["url"]

    assert player.client.delete(f"/players/{player.id}/password-reset").status_code == 403
    assert custodian.client.delete(f"/players/{player.id}/password-reset").status_code == 204

    assert client_for().get(f"/auth/reset/{url.rsplit('/', 1)[1]}").status_code == 404
    assert custodian.client.get(f"/players/{player.id}").json()["reset_expires_at"] is None
    assert custodian.client.delete(f"/players/{player.id}/password-reset").status_code == 404
    assert actions(session) == ["account.reset_link", "account.reset_cancelled"]


def test_the_custodian_reads_who_reset_and_when(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], mail: FakeSMTP
) -> None:
    custodian.client.post(f"/players/{player.id}/password-reset")
    forgot(client_for(), "nobody@example.com")
    forgot(client_for(), "player@example.com")
    stranger = sign_up(client_for, "stranger")
    custodian.client.post(f"/players/{stranger.id}/password-reset")

    assert player.client.get("/password-resets").status_code == 403
    resets_now = custodian.client.get("/password-resets").json()

    live = [(r["display_name"], r["made_by"], r["asked_themselves"]) for r in resets_now["live"]]
    assert live == [("player", "player", True), ("stranger", "custodian", False)]
    assert [e["message"] for e in resets_now["log"]] == [
        "custodian made a password reset link for stranger.",
        "Horatio emailed player the reset link they asked for.",
        "player asked for a password reset link.",
        "Someone asked for a reset link for nobody@example.com; no account uses it.",
        "custodian made a password reset link for player.",
    ]


def test_using_a_link_reads_in_the_log(
    custodian: Person, player: Person, client_for: Callable[[], TestClient]
) -> None:
    url = custodian.client.post(f"/players/{player.id}/password-reset").json()["url"]
    custodian.client.delete(f"/players/{player.id}/password-reset")
    url = custodian.client.post(f"/players/{player.id}/password-reset").json()["url"]
    token = url.rsplit("/", 1)[1]
    client_for().post("/auth/reset", json={"token": token, "password": "a new password!"})

    log = custodian.client.get("/password-resets").json()["log"]

    assert [e["message"] for e in log] == [
        "player set a new password with a reset link.",
        "custodian made a password reset link for player.",
        "custodian cancelled player's reset link.",
        "custodian made a password reset link for player.",
    ]
