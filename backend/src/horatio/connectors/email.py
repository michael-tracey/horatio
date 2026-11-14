"""Email: downtime results sent by Horatio, from its own address, with the
troupe's storyteller address as Reply-To.

Mail goes through one SMTP service set in server configuration
(`HORATIO_SMTP_*`, `HORATIO_MAIL_FROM`), so no troupe stores mail credentials.
Each message goes to the player's account address; a player with several
characters gets one email per character, each naming it. Alert mode, the
default, says the results are ready and links to them, so secrets stay in
Horatio where storytellers can still correct them.

A temporary refusal (a 4xx reply, a dropped connection) is retried; a
permanent one (a 5xx reply, such as an unknown address) fails with the
server's reason for storytellers to follow up. Bounces reported later by the
receiving server are not tracked yet.

The same service sends password reset links (horatio.auth.resets), straight to
the account's address, and the links that confirm a new address
(horatio.email_changes).
"""

import contextlib
import smtplib
import ssl
from collections.abc import Callable, Mapping
from dataclasses import replace
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from typing import Any

from email_validator import EmailNotValidError, validate_email

from horatio.config import get_settings
from horatio.connectors import Connector, Message, Recipient, SendError, register
from horatio.email_design import Body, Design, Line, compose, page, plain
from horatio.mail_sender import Sender


def connect() -> smtplib.SMTP:
    """An SMTP connection, signed in, as the server configuration says."""
    settings = get_settings()
    assert settings.smtp_host is not None
    context = ssl.create_default_context()
    if settings.smtp_ssl:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=30, context=context
        )
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
        if settings.smtp_starttls:
            smtp.starttls(context=context)
    if settings.smtp_username:
        smtp.login(settings.smtp_username, settings.smtp_password or "")
    return smtp


# Tests swap this for a fake mail server.
smtp_factory: Callable[[], smtplib.SMTP] = connect


def address(value: Any, what: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return validate_email(text, check_deliverability=False).normalized
    except EmailNotValidError as error:
        raise ValueError(f"{what} is not an email address: {error}") from None


def results_body(message: Message) -> Body:
    """Downtime results (or a note they're ready) in the email design: the message as
    it was written, a button to read it in Horatio, and who it's from."""
    return Body(
        text=message.text,
        action=("Read it in Horatio", message.link),
        lines=(Line(f"Sent by Horatio for {message.troupe}. Reply to reach the storytellers."),),
    )


def to_html(message: Message) -> str:
    """The message as its email's HTML, without its header picture (see compose)."""
    design = message.design or Design()
    shown = replace(design, header_image=None)
    return page(results_body(message), shown, subject=message.subject, header_src=None)


def to_text(message: Message) -> str:
    return plain(results_body(message), message.design or Design())


def configured() -> bool:
    """Whether the server has the SMTP settings Horatio needs to send email."""
    settings = get_settings()
    return bool(settings.smtp_host and settings.mail_from)


def new_message(to: str, subject: str, sender: Sender | None = None) -> EmailMessage:
    """A message from Horatio's own address, ready for its content: from `sender`
    (horatio.mail_sender, with what the custodian set), or else the server's
    `HORATIO_MAIL_FROM`. The sender's default Reply-To goes on too; an email with a
    Reply-To of its own replaces it."""
    from_ = sender.from_ if sender is not None else get_settings().mail_from or ""
    mail = EmailMessage()
    mail["From"] = from_
    mail["To"] = to
    mail["Subject"] = subject
    if sender is not None and sender.reply_to:
        mail["Reply-To"] = sender.reply_to
    domain = parseaddr(from_)[1].partition("@")[2] or None
    mail["Message-ID"] = make_msgid(domain=domain)
    return mail


class EmailConnector(Connector):
    kind = "email"
    name = "Email"
    needs = ("HORATIO_SMTP_HOST", "HORATIO_MAIL_FROM")

    def unavailable(self) -> str | None:
        if configured():
            return None
        return "Email isn't set up on this server yet."

    def check_settings(
        self, settings: Mapping[str, Any], current: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "reply_to": address(settings.get("reply_to"), "The reply-to address"),
            "test_address": address(settings.get("test_address"), "The test address"),
        }

    def target(self, settings: Mapping[str, Any], recipient: Recipient, test_mode: bool) -> str:
        if test_mode:
            if not settings.get("test_address"):
                raise SendError("No test address is set for email.", retry=False)
            return settings["test_address"]
        return formataddr((recipient.player_name, recipient.player_email))

    def send(self, settings: Mapping[str, Any], target: str, message: Message) -> dict[str, Any]:
        mail = new_message(target, message.subject, message.sender)
        if settings.get("reply_to"):
            # The troupe's storytellers, over the server's default.
            del mail["Reply-To"]
            mail["Reply-To"] = formataddr((f"{message.troupe} storytellers", settings["reply_to"]))
        compose(mail, results_body(message), message.design)
        deliver(mail)
        return {"message_id": mail["Message-ID"]}


def deliver(mail: EmailMessage) -> None:
    """Hand one message to the mail server, or raise SendError saying why not."""
    try:
        smtp = smtp_factory()
        try:
            refused = smtp.send_message(mail)
        finally:
            with contextlib.suppress(smtplib.SMTPException):
                smtp.quit()
    except smtplib.SMTPAuthenticationError as error:
        raise SendError("The mail server refused Horatio's sign-in.", retry=False) from error
    except smtplib.SMTPRecipientsRefused as error:
        code, reason = next(iter(error.recipients.values()))
        raise refusal(code, reason) from error
    except smtplib.SMTPResponseException as error:
        raise refusal(error.smtp_code, error.smtp_error) from error
    except (smtplib.SMTPException, OSError) as error:
        raise SendError(f"Could not reach the mail server: {error}", retry=True) from error
    if refused:
        code, reason = next(iter(refused.values()))
        raise refusal(code, reason)


def refusal(code: int, reason: bytes | str) -> SendError:
    """A mail server's refusal: 4xx is temporary and worth retrying, 5xx is not."""
    text = reason.decode(errors="replace") if isinstance(reason, bytes) else reason
    return SendError(f"The mail server refused it ({code}): {text}", retry=400 <= code < 500)


register(EmailConnector())
