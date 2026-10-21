"""Notifications that also come by email (issue #106): who gets them, at once or
in a daily digest, retries, and the unsubscribe link in each. No real email goes
anywhere: the mail server is a fake."""

import re
import smtplib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import delivery, notification_emails
from horatio.config import get_settings
from horatio.connectors import email
from horatio.models import EmailNotice
from horatio.preferences import Preferences
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_email_connector import FakeSMTP

# A Tuesday morning, before 8 o'clock in New York.
START = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSMTP]:
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    monkeypatch.setattr(delivery, "now", lambda: START)
    yield fake


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    return sign_up(client_for, "custodian", custodian=True, session=session)


@pytest.fixture
def asker(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "asker")


def choose(person: Person, **changes: object) -> None:
    response = person.client.patch("/preferences", json=changes)
    assert response.status_code == 200, response.text


def ask(person: Person, name: str = "Nights of Boston") -> str:
    response = person.client.post("/troupe-requests", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(session: Session, at: datetime = START) -> int:
    return notification_emails.send_due(session, at)


def waiting(session: Session) -> list[EmailNotice]:
    return list(session.scalars(select(EmailNotice).order_by(EmailNotice.created_at)))


def unsubscribe_token(message: EmailMessage) -> str:
    found = re.search(r"http://localhost:5173/unsubscribe/(\S+)", message.get_content())
    assert found, message.get_content()
    return found.group(1)


def test_each_kind_is_off_until_chosen(client_for: Callable[[], TestClient]) -> None:
    person = sign_up(client_for, "settler")
    shown = person.client.get("/preferences").json()
    assert {name for name in shown if name.startswith("email_")} == {
        "email_downtime",
        "email_approvals",
        "email_troupe_requests",
        "email_renames",
        "email_pictures",
        "email_digest",
    }
    assert not any(v for k, v in shown.items() if k.startswith("email_") and k != "email_digest")
    assert shown["email_digest"] == "at_once"
    assert person.client.patch("/preferences", json={"email_digest": "weekly"}).status_code == 422


def test_the_settings_say_whether_email_is_set_up(
    client_for: Callable[[], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    person = sign_up(client_for, "settler")
    assert person.client.get("/preferences/email").json() == {"available": False}
    monkeypatch.setattr(get_settings(), "smtp_host", "mail.example.org")
    monkeypatch.setattr(get_settings(), "mail_from", "horatio@example.org")
    assert person.client.get("/preferences/email").json() == {"available": True}
    assert client_for().get("/preferences/email").status_code == 401


def test_nothing_is_kept_while_the_server_has_no_email(
    custodian: Person, asker: Person, session: Session
) -> None:
    choose(custodian, email_troupe_requests=True)
    ask(asker)
    assert waiting(session) == []
    assert send(session) == 0


def test_a_chosen_kind_comes_by_email_at_once(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(custodian, email_troupe_requests=True)
    ask(asker)

    assert send(session) == 1
    [message] = mail.sent
    assert message["To"] == "custodian <custodian@example.com>"
    assert message["Subject"] == "asker asks for a new troupe, Nights of Boston"
    text = message.get_content()
    assert "http://localhost:5173/custodian/troupe-requests" in text
    assert "You asked Horatio to email you about troupe requests." in text
    assert (
        message["List-Unsubscribe"]
        == f"<http://localhost:5173/unsubscribe/{unsubscribe_token(message)}>"
    )
    # Sent once only, and the bell still has it.
    assert waiting(session) == []
    assert send(session) == 0
    assert len(custodian.client.get("/notifications").json()["items"]) == 1


def test_kinds_not_chosen_stay_in_the_bell(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(custodian, email_approvals=True, email_renames=True)
    ask(asker)
    assert waiting(session) == []


def test_messages_come_by_email_too(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(asker, email_troupe_requests=True)
    request = ask(asker)
    custodian.client.post(f"/troupe-requests/{request}/decline", json={"reason": "Too soon."})

    send(session)
    [message] = mail.sent
    assert message["To"] == "asker <asker@example.com>"
    assert message["Subject"] == (
        "Your request for the troupe Nights of Boston was declined: Too soon"
    )


def test_approvers_hear_of_requests_but_not_the_asker(
    client_for: Callable[[], TestClient], session: Session, mail: FakeSMTP
) -> None:
    troupe = Troupe(client_for, session)
    for person in (troupe.lead, troupe.storyteller, troupe.narrator, troupe.player):
        choose(person, email_approvals=True)
    character_id = new_character(troupe, troupe.player)
    troupe.player.client.post(
        f"/characters/{character_id}/home-troupe", json={"troupe_id": troupe.id}
    )

    send(session)
    # Narrators cannot approve, and the assistant did not ask for email.
    assert sorted(m["To"] for m in mail.sent) == [
        "lead <lead@example.com>",
        "storyteller <storyteller@example.com>",
    ]
    assert mail.sent[0]["Subject"] == (
        "Lords of the Night: Agnes asks to make Lords of the Night its home"
    )
    assert f"http://localhost:5173/troupes/{troupe.id}/approvals" in mail.sent[0].get_content()


def test_a_daily_digest_gathers_them_into_one(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(
        custodian,
        email_troupe_requests=True,
        email_digest="daily",
        time_zone="America/New_York",
    )
    ask(asker, "Nights of Boston")
    ask(asker, "Salem After Dark")

    # 8 o'clock in New York is noon UTC in October.
    assert send(session, START + timedelta(hours=2)) == 0
    assert mail.sent == []
    assert send(session, datetime(2026, 10, 20, 12, 0, tzinfo=UTC)) == 1
    [digest] = mail.sent
    assert digest["Subject"] == "Horatio: 2 notifications today"
    text = digest.get_content()
    assert "- asker asks for a new troupe, Nights of Boston" in text
    assert "- asker asks for a new troupe, Salem After Dark" in text
    assert "Stop emails about troupe requests: http://localhost:5173/unsubscribe/" in text
    assert "You asked Horatio to email you about any notification." in text
    assert waiting(session) == []


def test_the_digest_follows_utc_without_a_time_zone() -> None:
    prefs = Preferences()
    assert notification_emails.next_digest(prefs, START) == datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
    early = START.replace(hour=7)
    assert notification_emails.next_digest(prefs, early) == START.replace(hour=8)


def test_a_kind_turned_off_before_it_goes_is_dropped(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(custodian, email_troupe_requests=True)
    ask(asker)
    choose(custodian, email_troupe_requests=False)
    send(session)
    assert mail.sent == []
    assert waiting(session) == []


def test_a_temporary_refusal_is_tried_again_later(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(custodian, email_troupe_requests=True)
    ask(asker)

    mail.fail = smtplib.SMTPResponseException(451, b"try later")
    send(session)
    [notice] = waiting(session)
    assert notice.attempts == 1
    assert notice.due_at == START + timedelta(minutes=1)
    assert send(session) == 0

    mail.fail = None
    assert send(session, START + timedelta(minutes=1)) == 1
    assert len(mail.sent) == 1
    assert waiting(session) == []


def test_a_permanent_refusal_gives_up(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(custodian, email_troupe_requests=True)
    ask(asker)
    mail.fail = smtplib.SMTPResponseException(550, b"no such mailbox")
    send(session)
    assert waiting(session) == []


def test_the_link_in_an_email_turns_that_kind_off(
    client_for: Callable[[], TestClient],
    custodian: Person,
    asker: Person,
    session: Session,
    mail: FakeSMTP,
) -> None:
    choose(custodian, email_troupe_requests=True, email_renames=True)
    ask(asker)
    send(session)
    token = unsubscribe_token(mail.sent[0])

    # No sign-in needed: anyone with the link.
    stranger = client_for()
    shown = stranger.get(f"/unsubscribe/{token}").json()
    assert shown == {
        "display_name": "custodian",
        "email": "custodian@example.com",
        "about": "troupe requests",
        "subscribed": True,
    }
    stopped = stranger.post(f"/unsubscribe/{token}")
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["subscribed"] is False
    prefs = custodian.client.get("/preferences").json()
    assert (prefs["email_troupe_requests"], prefs["email_renames"]) == (False, True)


def test_a_digest_link_turns_every_kind_off(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(custodian, email_troupe_requests=True, email_renames=True, email_digest="daily")
    ask(asker)
    ask(asker, "Salem After Dark")
    send(session, START + timedelta(days=1))
    token = re.search(r"/unsubscribe/(\S+)", mail.sent[0]["List-Unsubscribe"])
    assert token
    assert (
        custodian.client.post(f"/unsubscribe/{token.group(1).rstrip('>')}").json()["about"]
        == "any notification"
    )
    prefs = custodian.client.get("/preferences").json()
    assert (prefs["email_troupe_requests"], prefs["email_renames"]) == (False, False)


def test_a_made_up_link_does_nothing(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(custodian, email_troupe_requests=True)
    ask(asker)
    send(session)
    token = unsubscribe_token(mail.sent[0])
    user_id, topic, _ = token.split(".")
    for forged in (
        f"{user_id}.{topic}.forged",
        f"{user_id}.all.{token.split('.')[2]}",
        f"{asker.id}.{topic}.{token.split('.')[2]}",
        f"not-an-id.{topic}.x",
        "nothing",
    ):
        refused = custodian.client.post(f"/unsubscribe/{forged}")
        assert refused.status_code == 404, forged
        assert "Account → Settings" in refused.json()["detail"]
    assert custodian.client.get("/preferences").json()["email_troupe_requests"] is True
