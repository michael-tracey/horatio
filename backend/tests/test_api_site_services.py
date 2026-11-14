"""Mail and Discord on Custodian › Site (#833, #834): what each card shows, with no
secret ever in an answer; who emails come from; the test email and the bot check;
connected troupes; and recent failures. No real mail or Discord: both are fakes."""

import json
import smtplib
import socket
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.connectors import Message, discord, email
from horatio.mail_sender import Sender
from horatio.models import AuditEvent, TroupeConnector
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_email_connector import FakeSMTP
from tests.test_notification_emails import ask, choose, send

PASSWORD = "s3cret-smtp-pass"
CLIENT_SECRET = "s3cret-client-secret"
BOT_TOKEN = "s3cret-bot-token"
# After anything the tests queue is due.
LATER = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    return sign_up(client_for, "custodian", custodian=True, session=session)


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSMTP]:
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "horatio@example.org")
    monkeypatch.setattr(settings, "smtp_password", PASSWORD)
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    yield fake


@pytest.fixture
def discord_env(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "discord_client_id", "1234567890")
    monkeypatch.setattr(settings, "discord_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(settings, "discord_bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "public_url", "https://horatio.example.org")


def no_secrets(response: Any) -> None:
    """No credential anywhere in an answer (the test client's response)."""
    for secret in (PASSWORD, CLIENT_SECRET, BOT_TOKEN):
        assert secret not in response.text


# --- mail -------------------------------------------------------------------------


def test_only_the_custodian_sees_the_cards(client_for: Callable[[], TestClient]) -> None:
    someone = sign_up(client_for, "someone")
    assert someone.client.get("/site/mail").status_code == 403
    assert someone.client.get("/site/discord").status_code == 403
    assert someone.client.post("/site/mail/test").status_code == 403
    assert someone.client.post("/site/discord/check").status_code == 403
    assert someone.client.put("/site/mail", json={}).status_code == 403


def test_mail_off_says_which_settings_are_missing(custodian: Person) -> None:
    found = custodian.client.get("/site/mail").json()
    assert found["on"] is False
    assert found["off_reason"] == "HORATIO_SMTP_HOST and HORATIO_MAIL_FROM are not set."
    assert found["password_set"] is False
    assert found["where"] == "deploy/production.env"
    assert custodian.client.post("/site/mail/test").status_code == 409


def test_the_mail_card_shows_what_it_uses_and_never_the_password(
    custodian: Person, mail: FakeSMTP
) -> None:
    response = custodian.client.get("/site/mail")
    no_secrets(response)
    found = response.json()
    assert found["on"] is True
    assert found["off_reason"] is None
    assert (found["host"], found["port"], found["security"]) == (
        "mail.example.org",
        587,
        "starttls",
    )
    assert found["security_note"] is None
    assert found["username"] == "ho•••@example.org"
    assert found["password_set"] is True
    assert found["server_from"] == "Horatio <horatio@example.org>"
    assert found["sends_from"] == "Horatio <horatio@example.org>"


def test_unencrypted_mail_is_flagged(
    custodian: Person, mail: FakeSMTP, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "smtp_starttls", False)
    found = custodian.client.get("/site/mail").json()
    assert found["security"] == "none"
    assert "unencrypted" in found["security_note"]


def test_from_and_reply_to_go_on_every_email(
    custodian: Person, mail: FakeSMTP, session: Session, client_for: Callable[[], TestClient]
) -> None:
    response = custodian.client.put(
        "/site/mail",
        json={
            "from_name": "  The Night   Desk ",
            "from_address": "desk@example.org",
            "reply_to": "help@example.org",
        },
    )
    assert response.status_code == 200, response.text
    found = response.json()
    assert found["sends_from"] == "The Night Desk <desk@example.org>"
    assert (found["from_name"], found["reply_to"]) == ("The Night Desk", "help@example.org")
    event = session.scalars(select(AuditEvent).where(AuditEvent.action == "mail.sender_set")).one()
    assert event.data["sends_from"] == "The Night Desk <desk@example.org>"

    # The test email, and a notification email, both come from it.
    assert custodian.client.post("/site/mail/test").json()["ok"] is True
    choose(custodian, email_troupe_requests=True)
    ask(sign_up(client_for, "asker"))
    send(session, LATER)
    assert len(mail.sent) == 2
    for sent in mail.sent:
        assert sent["From"] == "The Night Desk <desk@example.org>"
        assert sent["Reply-To"] == "help@example.org"

    # Blank puts back the server's.
    found = custodian.client.put("/site/mail", json={}).json()
    assert found["sends_from"] == "Horatio <horatio@example.org>"
    assert found["reply_to"] is None


def test_a_bad_address_is_refused(custodian: Person, mail: FakeSMTP) -> None:
    response = custodian.client.put("/site/mail", json={"from_address": "not an address"})
    assert response.status_code == 422
    assert "The From address" in response.json()["detail"]


def test_a_troupes_own_reply_to_wins_on_its_results(mail: FakeSMTP) -> None:
    message = Message(
        troupe="Lords of the Night",
        subject="Results",
        text="Your results are ready.",
        link="https://horatio.example.org/characters/x/results",
        sender=Sender("The Night Desk <desk@example.org>", "help@example.org"),
    )
    email.EmailConnector().send({"reply_to": "sts@example.org"}, "player@example.org", message)
    sent = mail.sent[0]
    assert sent["From"] == "The Night Desk <desk@example.org>"
    assert sent.get_all("Reply-To") == ["Lords of the Night storytellers <sts@example.org>"]


def test_the_test_email_goes_to_the_custodian(
    custodian: Person, mail: FakeSMTP, session: Session
) -> None:
    found = custodian.client.post("/site/mail/test").json()
    assert found == {"ok": True, "to": custodian.email, "reason": None, "detail": None}
    assert mail.sent[0]["To"].endswith(f"<{custodian.email}>")
    assert session.scalars(select(AuditEvent).where(AuditEvent.action == "mail.test_sent")).one()


@pytest.mark.parametrize(
    ("failure", "words"),
    [
        (
            smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"),
            "HORATIO_SMTP_USERNAME and HORATIO_SMTP_PASSWORD",
        ),
        (socket.gaierror(-2, "Name or service not known"), "Check HORATIO_SMTP_HOST."),
        (ConnectionRefusedError(111, "Connection refused"), "Check HORATIO_SMTP_PORT."),
    ],
)
def test_a_failed_test_says_why_in_plain_words(
    custodian: Person, mail: FakeSMTP, failure: Exception, words: str
) -> None:
    mail.fail = failure
    response = custodian.client.post("/site/mail/test")
    no_secrets(response)
    found = response.json()
    assert found["ok"] is False
    assert words in found["reason"]
    assert found["detail"]


def test_notification_emails_given_up_show_as_failures(
    custodian: Person, mail: FakeSMTP, session: Session, client_for: Callable[[], TestClient]
) -> None:
    choose(custodian, email_troupe_requests=True)
    ask(sign_up(client_for, "asker"))
    mail.fail = smtplib.SMTPResponseException(550, b"no such mailbox")
    send(session, LATER)
    failures = custodian.client.get("/site/mail").json()["failures"]
    assert len(failures) == 1
    failure = failures[0]
    assert failure["kind"] == "notifications"
    assert failure["state"] == "failed"
    assert failure["about"] == "1 notification to custodian"
    assert "no such mailbox" in failure["reason"]
    assert failure["retry"] is None


def test_mail_masks_short_usernames() -> None:
    from horatio.api.site_services import masked

    assert masked("apikey") == "ap•••"
    assert masked("bob@example.org") == "b•••@example.org"


# --- Discord ----------------------------------------------------------------------


def test_discord_off_names_what_is_missing(custodian: Person) -> None:
    found = custodian.client.get("/site/discord").json()
    assert found["on"] is False
    assert found["missing"] == [
        "HORATIO_DISCORD_CLIENT_ID",
        "HORATIO_DISCORD_CLIENT_SECRET",
        "HORATIO_DISCORD_BOT_TOKEN",
    ]
    assert found["invite"] is None
    assert found["redirect"].endswith("/api/discord/callback")
    assert custodian.client.post("/site/discord/check").status_code == 409


def test_the_discord_card_shows_what_to_copy_and_never_the_secrets(
    custodian: Person, discord_env: None
) -> None:
    response = custodian.client.get("/site/discord")
    no_secrets(response)
    found = response.json()
    assert found["on"] is True
    assert found["missing"] == []
    assert found["client_id"] == "1234567890"
    assert (found["client_secret_set"], found["bot_token_set"]) == (True, True)
    assert found["redirect"] == "https://horatio.example.org/api/discord/callback"
    invite = httpx.URL(found["invite"])
    assert invite.params["client_id"] == "1234567890"
    assert invite.params["scope"] == "bot"
    assert invite.params["permissions"] == str(discord.FOR_INVITE)


def fake_discord(monkeypatch: pytest.MonkeyPatch, handle: Callable[[httpx.Request], Any]) -> None:
    monkeypatch.setattr(discord, "transport", httpx.MockTransport(handle))


def test_check_the_bot_asks_discord_who_it_is(
    custodian: Person, discord_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bot {BOT_TOKEN}"
        if request.url.path.endswith("/users/@me"):
            return httpx.Response(200, json={"id": "42", "username": "Horatio"})
        return httpx.Response(200, json=[{"id": "1"}, {"id": "2"}])

    fake_discord(monkeypatch, handle)
    response = custodian.client.post("/site/discord/check")
    no_secrets(response)
    assert response.json() == {
        "ok": True,
        "name": "Horatio",
        "id": "42",
        "servers": 2,
        "more": False,
        "reason": None,
        "detail": None,
    }


def test_a_refused_token_says_which_setting(
    custodian: Person, discord_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_discord(monkeypatch, lambda request: httpx.Response(401, json={"message": "401"}))
    response = custodian.client.post("/site/discord/check")
    no_secrets(response)
    found = response.json()
    assert found["ok"] is False
    assert "HORATIO_DISCORD_BOT_TOKEN" in found["reason"]


def test_connected_troupes_are_listed(
    discord_env: None, client_for: Callable[[], TestClient], session: Session
) -> None:
    troupe = Troupe(client_for, session)
    session.add(
        TroupeConnector(
            troupe_id=uuid.UUID(troupe.id),
            kind="discord",
            enabled=True,
            settings={
                "guild_id": "999",
                "guild_name": "Night Court",
                "channels": {str(uuid.uuid4()): "111", str(uuid.uuid4()): ""},
                "test_channel": "222",
                "post_channels": {"news": "333"},
            },
        )
    )
    session.flush()
    found = troupe.custodian.client.get("/site/discord").json()
    assert found["troupes"] == [
        {
            "troupe_id": troupe.id,
            "troupe_name": "Lords of the Night",
            "archived": False,
            "server": "Night Court",
            "characters": 1,
            "test_channel": True,
            "posts": ["news"],
        }
    ]
    assert json.dumps(found).count("999") == 0
