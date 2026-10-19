"""The email connector against a fake mail server: what the email says, where it
goes, and which refusals are worth retrying."""

import smtplib
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import pytest
from sqlalchemy.orm import Session

from horatio import delivery
from horatio.config import get_settings
from horatio.connectors import Message, email
from tests.test_api_responses import Scene
from tests.test_delivery_connectors import START, agnes_on, deliver, scene  # noqa: F401


class FakeSMTP:
    """Takes messages, or refuses them as told."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail: Exception | None = None
        self.refused: dict[str, tuple[int, bytes]] = {}

    def __call__(self) -> "FakeSMTP":
        if isinstance(self.fail, OSError):
            raise self.fail
        return self

    def send_message(self, message: EmailMessage) -> dict[str, tuple[int, bytes]]:
        if self.fail is not None:
            raise self.fail
        self.sent.append(message)
        return self.refused

    def quit(self) -> None:
        pass


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSMTP]:
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    yield fake


def set_up(ready: Scene, **change: Any) -> Any:
    troupe = ready.troupe
    body = {
        "enabled": True,
        "settings": {"reply_to": "sts@example.com", "test_address": "st-test@example.com"},
        **change,
    }
    return troupe.storyteller.client.put(f"/troupes/{troupe.id}/connectors/email", json=body)


def send(ready: Scene, session: Session) -> None:
    deliver(ready)
    delivery.send_due(session, START)


def body(message: EmailMessage, subtype: str) -> str:
    part = message.get_body(preferencelist=(subtype,))
    assert part is not None
    return part.get_content()


def test_without_server_configuration_email_is_unavailable(scene: Scene) -> None:  # noqa: F811
    troupe = scene.troupe
    listed = troupe.storyteller.client.get(f"/troupes/{troupe.id}/connectors").json()

    found = next(c for c in listed if c["kind"] == "email")
    assert "HORATIO_SMTP_HOST" in found["unavailable"]
    assert set_up(scene).status_code == 409


def test_settings_need_real_addresses(scene: Scene, mail: FakeSMTP) -> None:  # noqa: F811
    assert set_up(scene, settings={"reply_to": "not an address"}).status_code == 422

    saved = set_up(scene, settings={"reply_to": "STs@Example.com", "test_address": ""})

    assert saved.status_code == 200, saved.text
    assert saved.json()["settings"] == {"reply_to": "STs@example.com", "test_address": None}
    # Email defaults to an alert, keeping the results in Horatio.
    assert saved.json()["mode"] == "alert"


def test_an_alert_goes_to_the_player_with_the_troupe_as_reply_to(
    scene: Scene,  # noqa: F811
    mail: FakeSMTP,
    session: Session,
) -> None:
    set_up(scene)
    send(scene, session)

    [message] = mail.sent
    assert message["To"] == "player <player@example.com>"
    assert message["From"] == "Horatio <horatio@example.org>"
    assert message["Reply-To"] == "Lords of the Night storytellers <sts@example.com>"
    assert message["Subject"] == "Lords of the Night: downtime results for Agnes (October 2026)"
    link = f"http://localhost:5173/characters/{scene.agnes}/results"
    text = body(message, "plain")
    assert text.startswith("Your downtime results for Agnes (October 2026) are ready: ")
    assert link in text
    assert "Feed at the docks" not in text
    assert f'<a href="{link}">Read it in Horatio</a>' in body(message, "html")
    assert agnes_on(scene, "email")["status"] == "sent"


def test_full_text_carries_the_results(
    scene: Scene,  # noqa: F811
    mail: FakeSMTP,
    session: Session,
) -> None:
    set_up(scene, mode="full")
    send(scene, session)

    [message] = mail.sent
    assert "*Your action:* Feed at the docks" in body(message, "plain")
    html = body(message, "html")
    assert "<strong>Downtime results for Agnes (October 2026)</strong>" in html
    assert "<em>Result:</em> You feed well." in html


def test_test_mode_sends_to_the_test_address(
    scene: Scene,  # noqa: F811
    mail: FakeSMTP,
    session: Session,
) -> None:
    set_up(scene, test_mode=True)
    send(scene, session)

    assert [m["To"] for m in mail.sent] == ["st-test@example.com"]


@pytest.mark.parametrize(
    ("failure", "status", "error"),
    [
        (
            smtplib.SMTPRecipientsRefused({"player@example.com": (550, b"No such user")}),
            "failed",
            "The mail server refused it (550): No such user",
        ),
        (
            smtplib.SMTPSenderRefused(451, b"Try again later", "horatio@example.org"),
            "pending",
            "The mail server refused it (451): Try again later",
        ),
        (ConnectionRefusedError("refused"), "pending", "Could not reach the mail server: refused"),
        (
            smtplib.SMTPAuthenticationError(535, b"Bad credentials"),
            "failed",
            "The mail server refused Horatio's sign-in.",
        ),
    ],
)
def test_temporary_refusals_are_retried_and_permanent_ones_fail(
    scene: Scene,  # noqa: F811
    mail: FakeSMTP,
    session: Session,
    failure: Exception,
    status: str,
    error: str,
) -> None:
    set_up(scene)
    mail.fail = failure

    send(scene, session)

    shown = agnes_on(scene, "email")
    assert (shown["status"], shown["last_error"]) == (status, error)


def test_html_escapes_what_players_wrote() -> None:
    message = Message(
        troupe="Court <of> Ash",
        subject="s",
        text="**Bold** and <script>alert(1)</script>\nsee https://example.com/a?b=1&c=2",
        link="https://horatio.example/characters/1/results",
    )

    page = email.to_html(message)

    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "<strong>Bold</strong>" in page
    assert '<a href="https://example.com/a?b=1&amp;c=2">' in page
    assert "Court &lt;of&gt; Ash" in page
