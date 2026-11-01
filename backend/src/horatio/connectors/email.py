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
import html
import re
import smtplib
import ssl
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from typing import Any

from email_validator import EmailNotValidError, validate_email

from horatio.config import get_settings
from horatio.connectors import Connector, Message, Recipient, SendError, register


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


INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\n]+\*|https?://\S+)")


def inline_html(line: str) -> str:
    """One line of results as HTML: **bold**, *italic* and links, everything
    else escaped."""
    out: list[str] = []
    for part in INLINE.split(line):
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(f"<strong>{html.escape(part[2:-2])}</strong>")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"<em>{html.escape(part[1:-1])}</em>")
        elif part.startswith(("http://", "https://")):
            url = html.escape(part, quote=True)
            out.append(f'<a href="{url}">{url}</a>')
        else:
            out.append(html.escape(part))
    return "".join(out)


def to_html(message: Message) -> str:
    """The message as a simple HTML page: the same marks the app shows, as
    paragraphs, and a link to read it in Horatio."""
    paragraphs = "\n".join(
        "<p>" + "<br>".join(inline_html(line) for line in para.split("\n")) + "</p>"
        for para in message.text.split("\n\n")
    )
    link = html.escape(message.link, quote=True)
    troupe = html.escape(message.troupe)
    return f"""<!doctype html>
<html><body>
<div style="font-family: Georgia, serif; line-height: 1.5; color: #222222; max-width: 40em">
{paragraphs}
<p><a href="{link}">Read it in Horatio</a></p>
<p style="color: #777; font-size: 0.9em">
Sent by Horatio for {troupe}. Reply to reach the storytellers.</p>
</div>
</body></html>
"""


def to_text(message: Message) -> str:
    footer = f"Sent by Horatio for {message.troupe}. Reply to reach the storytellers."
    if message.link in message.text:
        return f"{message.text}\n\n-- \n{footer}\n"
    return f"{message.text}\n\nRead it in Horatio: {message.link}\n\n-- \n{footer}\n"


def configured() -> bool:
    """Whether the server has the SMTP settings Horatio needs to send email."""
    settings = get_settings()
    return bool(settings.smtp_host and settings.mail_from)


def new_message(to: str, subject: str) -> EmailMessage:
    """A message from Horatio's own address, ready for its content."""
    sender = get_settings().mail_from or ""
    mail = EmailMessage()
    mail["From"] = sender
    mail["To"] = to
    mail["Subject"] = subject
    domain = parseaddr(sender)[1].partition("@")[2] or None
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
        mail = new_message(target, message.subject)
        if settings.get("reply_to"):
            mail["Reply-To"] = formataddr((f"{message.troupe} storytellers", settings["reply_to"]))
        mail.set_content(to_text(message))
        mail.add_alternative(to_html(message), subtype="html")
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
