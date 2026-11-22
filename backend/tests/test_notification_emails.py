"""Notifications that also come by email (issue #106): who gets them, at once or
in a digest a day or a week (#1196), retries, and the unsubscribe link in each. No
real email goes anywhere: the mail server is a fake."""

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
from horatio.auth import two_step
from horatio.config import get_settings
from horatio.connectors import email
from horatio.models import EmailDigest, EmailNotice
from horatio.notification_choices import BY_NAME
from horatio.preferences import Preferences
from tests.api_helpers import Person, Troupe, new_character, sign_up
from tests.test_email_connector import FakeSMTP, text_of

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
    return list(
        session.scalars(select(EmailNotice).order_by(EmailNotice.created_at, EmailNotice.id))
    )


def emailed(person: Person, *topics: str) -> tuple[bool, ...]:
    """Whether each of these comes to the person by email, as their Notifications page
    shows it."""
    groups = person.client.get("/notification-settings").json()["groups"]
    on = {
        t["name"]: r["on"]
        for g in groups
        for t in g["topics"]
        for r in t["routes"]
        if r["way"] == "email"
    }
    return tuple(on[t] for t in topics)


def unsubscribe_token(message: EmailMessage) -> str:
    found = re.search(r"http://localhost:5173/unsubscribe/(\S+)", text_of(message))
    assert found, text_of(message)
    return found.group(1)


def test_each_kind_is_off_until_chosen(client_for: Callable[[], TestClient]) -> None:
    """All but troupe announcements, which are often practical (#511). Each is on
    Account › Notifications (#1053; horatio.notification_choices)."""
    person = sign_up(client_for, "settler")
    groups = person.client.get("/notification-settings").json()["groups"]
    emailed = {
        t["name"]: r["on"]
        for g in groups
        for t in g["topics"]
        for r in t["routes"]
        if r["way"] == "email" and not r["always"]
    }
    assert emailed.pop("announcements") is True
    assert not any(emailed.values())
    assert {"downtime", "downtime_reminders", "renames", "pictures", "news"} <= set(emailed)
    prefs = person.client.get("/preferences").json()
    assert (prefs["email_digest"], prefs["digest_hour"], prefs["digest_day"]) == (
        "at_once",
        8,
        "monday",
    )
    for wrong in (
        {"email_digest": "fortnightly"},
        {"digest_hour": 24},
        {"digest_day": "someday"},
        {"quiet_start": "25:00"},
        {"quiet_end": "7pm"},
    ):
        assert person.client.patch("/preferences", json=wrong).status_code == 422, wrong


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
    text = text_of(message)
    assert "http://localhost:5173/custodian/troupe-management#requests" in text
    assert "You asked Horatio to email you about troupe requests." in text
    assert (
        message["List-Unsubscribe"]
        == f"<http://localhost:5173/unsubscribe/{unsubscribe_token(message)}>"
    )
    # Sent once only, and the bell still has it.
    assert waiting(session) == []
    assert send(session) == 0
    items = custodian.client.get("/notifications").json()["items"]
    assert len([i for i in items if i["kind"] == "troupe_request"]) == 1


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
    assert f"http://localhost:5173/troupes/{troupe.id}/approvals" in text_of(mail.sent[0])


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
    text = text_of(digest)
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


def test_a_weekly_digest_goes_on_the_day_and_at_the_hour_chosen(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(
        custodian,
        email_troupe_requests=True,
        email_digest="weekly",
        digest_day="thursday",
        digest_hour=18,
        time_zone="Europe/London",
    )
    ask(asker, "Nights of Boston")
    ask(asker, "Salem After Dark")
    # 6 pm on Thursday in London is 5 pm UTC in October, while the clocks are forward.
    thursday = datetime(2026, 10, 22, 17, 0, tzinfo=UTC)
    assert {n.due_at for n in waiting(session)} == {thursday}

    assert send(session, thursday - timedelta(minutes=1)) == 0
    assert send(session, thursday) == 1
    [digest] = mail.sent
    assert digest["Subject"] == "Horatio: 2 notifications this week"
    text = text_of(digest)
    assert "Here is the week's news from Horatio." in text
    # Grouped by topic, under its title.
    assert "Troupe requests\n\n- asker asks for a new troupe, Nights of Boston" in text
    assert waiting(session) == []
    assert session.scalar(select(EmailDigest.window)) == "2026-W43"


def test_a_digest_goes_once_a_window(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    """A second worker, or the hour moved after the day's digest went, sends no other
    that day: what comes in later waits for the next."""
    choose(custodian, email_troupe_requests=True, email_digest="daily", time_zone="UTC")
    ask(asker, "Nights of Boston")
    eight = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
    assert send(session, eight) == 1
    assert send(session, eight) == 0
    assert len(mail.sent) == 1

    # Later that morning: the digest moved to 10 o'clock, and another request.
    later = eight + timedelta(hours=1)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(delivery, "now", lambda: later)
        choose(custodian, digest_hour=10)
        ask(asker, "Salem After Dark")
    [notice] = waiting(session)
    tomorrow = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
    assert notice.due_at == tomorrow

    # Even one due today by some slip waits: today's went.
    notice.due_at = later
    session.flush()
    assert send(session, eight + timedelta(hours=2)) == 0
    assert notice.due_at == tomorrow
    assert send(session, tomorrow) == 1
    assert len(mail.sent) == 2


def test_choosing_at_once_again_sends_what_waits(
    custodian: Person, asker: Person, session: Session, mail: FakeSMTP
) -> None:
    choose(custodian, email_troupe_requests=True, email_digest="daily")
    ask(asker)
    assert send(session) == 0
    choose(custodian, email_digest="at_once")
    assert send(session) == 1
    assert mail.sent[0]["Subject"] == "asker asks for a new troupe, Nights of Boston"


def test_word_about_the_accounts_safety_never_waits_for_the_digest(
    client_for: Callable[[], TestClient], session: Session, mail: FakeSMTP
) -> None:
    agnes = sign_up(client_for, "agnes")
    choose(agnes, email_digest="weekly", email_troupe_requests=True)

    assert two_step.reset_by_server(session, agnes.email) == 0

    [sent] = mail.sent
    assert sent["Subject"] == "Your Horatio two-step sign-in was reset"
    assert waiting(session) == []
    # Should a notice of an urgent topic wait in the queue, it is due at once, alone.
    for urgent in ("security", "account_emails"):
        assert BY_NAME[urgent].urgent
        assert notification_emails.at_once(BY_NAME[urgent], forced=False)
    assert not notification_emails.at_once(BY_NAME["downtime"], forced=False)
    assert notification_emails.at_once(BY_NAME["announcements"], forced=True)


@pytest.mark.parametrize(
    ("zone", "hour", "after", "expected"),
    [
        # New York in summer time, then standard time from 1 November: 8 am moves from
        # 12:00 to 13:00 UTC.
        ("America/New_York", 8, datetime(2026, 10, 31, 12, 0, tzinfo=UTC), (2026, 11, 1, 13)),
        # 1 am on 1 November comes twice in New York: the first of the two.
        ("America/New_York", 1, datetime(2026, 10, 31, 6, 0, tzinfo=UTC), (2026, 11, 1, 5)),
        # 2 am on 14 March 2027 isn't a time in New York: by the offset before, 3 am.
        ("America/New_York", 2, datetime(2027, 3, 13, 8, 0, tzinfo=UTC), (2027, 3, 14, 7)),
        # Sydney goes forward on 4 October 2026: 8 am is 22:00 UTC the day before, then 21:00.
        ("Australia/Sydney", 8, datetime(2026, 10, 2, 21, 0, tzinfo=UTC), (2026, 10, 2, 22)),
        ("Australia/Sydney", 8, datetime(2026, 10, 3, 0, 0, tzinfo=UTC), (2026, 10, 3, 21)),
    ],
)
def test_the_digest_keeps_its_hour_over_a_change_of_clocks(
    zone: str, hour: int, after: datetime, expected: tuple[int, int, int, int]
) -> None:
    prefs = Preferences(email_digest="daily", digest_hour=hour, time_zone=zone)
    assert notification_emails.next_digest(prefs, after) == datetime(*expected, tzinfo=UTC)


def test_a_weekly_digest_keeps_its_day_and_window_in_the_persons_zone() -> None:
    # Monday 8 am in Auckland is Sunday 7 pm UTC.
    prefs = Preferences(email_digest="weekly", digest_day="monday", time_zone="Pacific/Auckland")
    friday = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)
    sunday = datetime(2026, 11, 22, 19, 0, tzinfo=UTC)
    assert notification_emails.next_digest(prefs, friday) == sunday
    assert notification_emails.window(prefs, sunday) == "2026-W48"
    # The window already sent is skipped: the week after.
    assert notification_emails.next_digest(prefs, friday, "2026-W48") == sunday + timedelta(days=7)
    daily = Preferences(email_digest="daily", time_zone="Pacific/Auckland")
    assert notification_emails.window(daily, sunday) == "2026-11-23"


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
    assert emailed(custodian, "troupe_requests", "renames") == (False, True)


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
    assert emailed(custodian, "troupe_requests", "renames") == (False, False)


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
        assert "Account › Notifications" in refused.json()["detail"]
    assert emailed(custodian, "troupe_requests") == (True,)
