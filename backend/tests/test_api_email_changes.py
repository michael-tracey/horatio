"""Changing someone's email: by the custodian with a reason, or by the person with
their password, and only once confirmed at the new address."""

import re
from collections.abc import Callable, Iterator
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from horatio import notification_emails
from horatio.config import get_settings
from horatio.connectors import email
from horatio.models import AuditEvent, EmailChange, User
from tests.api_helpers import PASSWORD, Person, sign_up
from tests.test_email_connector import FakeSMTP

NEW = "new-address@example.com"


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    return sign_up(client_for, "custodian", custodian=True, session=session)


@pytest.fixture
def player(client_for: Callable[[], TestClient]) -> Person:
    return sign_up(client_for, "player")


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSMTP]:
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    yield fake


def change(by: Person, whose: Person, address: str = NEW, **body: Any) -> Any:
    return by.client.post(f"/players/{whose.id}/email-change", json={"email": address, **body})


def token_in(message: EmailMessage) -> str:
    found = re.search(r"http://localhost:5173/confirm-email/(\S+)", message.get_content())
    assert found, message.get_content()
    return found.group(1)


def token_of(url: str) -> str:
    return url.rsplit("/", 1)[1]


def confirm(client: TestClient, token: str) -> Any:
    return client.post(f"/auth/email-change/{token}")


def sign_in(client: TestClient, login: str) -> int:
    return client.post("/auth/login", json={"login": login, "password": PASSWORD}).status_code


def actions(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.action.like("account.email%"))
            .order_by(AuditEvent.id)
        )
    )


def user(session: Session, person: Person) -> User:
    found = session.scalars(select(User).where(User.handle == person.handle)).one()
    session.refresh(found)
    return found


# --- the custodian ---------------------------------------------------------------------------


def test_the_custodian_changes_an_email_confirmed_at_the_new_address(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session,
    mail: FakeSMTP,
) -> None:  # fmt: skip
    unsubscribe = notification_emails.unsubscribe_url(user(session, player), "all")
    assert client_for().get(f"/unsubscribe/{token_of(unsubscribe)}").status_code == 200

    response = change(custodian, player, reason="Lost access to their old address")

    assert response.status_code == 201, response.text
    started = response.json()
    assert (started["new_email"], started["emailed_to"], started["url"]) == (NEW, NEW, None)
    assert (started["made_by"], started["asked_themselves"]) == ("custodian", False)
    # The link goes to the new address only, and nothing has changed yet.
    assert [m["To"] for m in mail.sent] == [f"player <{NEW}>"]
    assert "custodian, Horatio's custodian, is changing" in mail.sent[0].get_content()
    assert sign_in(client_for(), player.email) == 200
    assert sign_in(client_for(), NEW) == 401

    # The player opens it, without signing in.
    fresh = client_for()
    token = token_in(mail.sent[0])
    asked = fresh.get(f"/auth/email-change/{token}").json()
    assert asked == {"display_name": "player", "handle": player.handle, "new_email": NEW}
    confirmed = confirm(fresh, token)

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"email": NEW}
    assert sign_in(client_for(), NEW) == 200
    assert sign_in(client_for(), player.email) == 401
    # The old address is told, with who to contact.
    notice = mail.sent[1]
    assert notice["To"] == f"player <{player.email}>"
    assert notice["Subject"] == "Your Horatio email has changed"
    text = notice.get_content()
    assert f"to {NEW}" in text
    assert "custodian, Horatio's custodian, made the change" in text
    assert f"contact Horatio's custodian straight away: custodian (@{custodian.handle})" in text
    # The link is spent, and old unsubscribe links stop working.
    assert confirm(client_for(), token).status_code == 404
    assert client_for().get(f"/unsubscribe/{token_of(unsubscribe)}").status_code == 404
    assert actions(session) == ["account.email_change_started", "account.email_changed"]
    log = custodian.client.get("/email-changes").json()["log"]
    assert [e["message"] for e in log] == [
        f"player confirmed their new email, {NEW}, changed by custodian from "
        f"{player.email} (Lost access to their old address).",
        f"custodian started changing player's email from {player.email} to {NEW} "
        "(Lost access to their old address).",
    ]


def test_without_email_the_custodian_gets_the_link_to_send(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session
) -> None:
    response = change(custodian, player, reason="Typo at sign-up")

    assert response.status_code == 201
    started = response.json()
    assert started["emailed_to"] is None
    assert started["email_error"] is None
    assert confirm(client_for(), token_of(started["url"])).status_code == 200
    assert user(session, player).email == NEW


def test_the_custodian_is_told_when_the_email_fails(
    custodian: Person, player: Person, session: Session, mail: FakeSMTP
) -> None:
    mail.fail = OSError("connection refused")

    started = change(custodian, player, reason="Lost access").json()

    assert "Could not reach the mail server" in started["email_error"]
    # The change waits all the same, with the link to send on.
    assert started["url"]
    assert actions(session) == [
        "account.email_change_started",
        "account.email_change_email_failed",
    ]


def test_the_custodian_gives_a_reason_and_only_the_custodian_changes_anothers(
    custodian: Person, player: Person, client_for: Callable[[], TestClient]
) -> None:
    stranger = sign_up(client_for, "stranger")

    assert change(custodian, player).status_code == 422
    assert change(custodian, player, reason="  ").json()["detail"] == "Give a reason."
    assert change(stranger, player, reason="Mine now").status_code == 403
    assert stranger.client.get("/email-changes").status_code == 403


def test_an_address_in_use_is_refused(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session,
    mail: FakeSMTP,
) -> None:  # fmt: skip
    other = sign_up(client_for, "other")

    taken = change(custodian, player, other.email.upper(), reason="Lost access")
    same = change(custodian, player, player.email, reason="Lost access")

    assert taken.status_code == 409
    assert taken.json()["detail"] == (
        f"other (@{other.handle}) uses OTHER@example.com already. If both accounts are "
        "the same person's, merge them instead."
    )
    assert same.status_code == 422
    # Someone changing their own isn't told whose it is.
    own = change(player, player, other.email, password=PASSWORD)
    assert own.status_code == 409
    assert "ask the custodian to merge the two" in own.json()["detail"]
    assert mail.sent == []
    assert actions(session) == []


def test_an_address_taken_before_the_link_is_opened_is_refused(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session
) -> None:
    url = change(custodian, player, reason="Lost access").json()["url"]
    sign_up(client_for, "new-address")

    response = confirm(client_for(), token_of(url))

    assert response.status_code == 409
    assert user(session, player).email == player.email


def test_the_custodian_resends_and_cancels(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session
) -> None:
    first = change(custodian, player, reason="Lost access").json()["url"]

    resent = custodian.client.post(f"/players/{player.id}/email-change/resend")

    assert resent.status_code == 200
    second = resent.json()["url"]
    assert client_for().get(f"/auth/email-change/{token_of(first)}").status_code == 404
    assert client_for().get(f"/auth/email-change/{token_of(second)}").status_code == 200

    assert custodian.client.delete(f"/players/{player.id}/email-change").status_code == 204

    assert client_for().get(f"/auth/email-change/{token_of(second)}").status_code == 404
    assert custodian.client.delete(f"/players/{player.id}/email-change").status_code == 404
    assert custodian.client.post(f"/players/{player.id}/email-change/resend").status_code == 404
    assert actions(session) == [
        "account.email_change_started",
        "account.email_change_resent",
        "account.email_change_cancelled",
    ]
    assert [e["message"] for e in custodian.client.get("/email-changes").json()["log"]] == [
        f"custodian cancelled changing player's email to {NEW}.",
        f"custodian made a new link for player to confirm {NEW}.",
        f"custodian started changing player's email from {player.email} to {NEW} (Lost access).",
    ]


def test_who_sees_a_change_waiting(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session
) -> None:
    stranger = sign_up(client_for, "stranger")
    started = change(custodian, player, reason="Lost access").json()

    waiting = custodian.client.get("/email-changes").json()["pending"]
    assert [(p["display_name"], p["email"], p["new_email"]) for p in waiting] == [
        ("player", player.email, NEW)
    ]
    found = custodian.client.get("/players", params={"q": "player"}).json()
    assert next(p for p in found if p["id"] == player.id)["email_change_to"] == NEW
    own = player.client.get(f"/players/{player.id}").json()["email_change"]
    assert own == {
        "new_email": NEW,
        "expires_at": started["expires_at"],
        "made_by": "custodian",
        "asked_themselves": False,
    }
    assert stranger.client.get(f"/players/{player.id}").json()["email_change"] is None
    # A week on, the link has expired.
    session.execute(
        update(EmailChange).values(expires_at=EmailChange.expires_at - timedelta(days=7))
    )
    session.flush()
    assert client_for().get(f"/auth/email-change/{token_of(started['url'])}").status_code == 404
    assert player.client.get(f"/players/{player.id}").json()["email_change"] is None


# --- the player themself ---------------------------------------------------------------------


def test_a_player_changes_their_own_with_their_password(
    custodian: Person, player: Person, client_for: Callable[[], TestClient], session: Session,
    mail: FakeSMTP,
) -> None:  # fmt: skip
    assert change(player, player).status_code == 403
    wrong = change(player, player, password="not my password")
    assert (wrong.status_code, wrong.json()["detail"]) == (403, "That's not your password.")

    response = change(player, player, password=PASSWORD)

    assert response.status_code == 201, response.text
    started = response.json()
    # They never see the link: it goes to the new address.
    assert (started["emailed_to"], started["url"], started["asked_themselves"]) == (NEW, None, True)
    assert "You asked to change the email" in mail.sent[0].get_content()
    # They can have it sent again, or cancel it.
    assert player.client.post(f"/players/{player.id}/email-change/resend").status_code == 200
    assert confirm(client_for(), token_in(mail.sent[0])).status_code == 404
    assert confirm(client_for(), token_in(mail.sent[1])).status_code == 200

    assert player.client.get("/auth/me").json()["email"] == NEW
    notice = mail.sent[2].get_content()
    assert "Horatio's custodian, made the change" not in notice
    assert "contact Horatio's custodian straight away" in notice
    assert [e["message"] for e in custodian.client.get("/email-changes").json()["log"]] == [
        f"player confirmed their new email, {NEW}, changed from {player.email}.",
        f"player asked for a new link to confirm {NEW}.",
        f"player asked to change their email from {player.email} to {NEW}.",
    ]


def test_without_email_a_player_cannot_change_their_own(player: Person) -> None:
    response = change(player, player, password=PASSWORD)

    assert response.status_code == 409
    assert "ask the custodian" in response.json()["detail"]
