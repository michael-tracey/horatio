"""The email design (#830): every email Horatio sends has a plain-text and an HTML part,
in the header and footer the custodian sets on Custodian › Site, with its header
picture carried in the email (cid:), never linked; the fixed lines under the footer
stay whatever the footer says; and the card, its preview and its test."""

from collections.abc import Callable, Iterator
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import email_design
from horatio.api import auth as auth_api
from horatio.config import get_settings
from horatio.connectors import email
from horatio.email_design import Body, Design, DesignError, InlineImage, Line
from horatio.models import AuditEvent
from tests.api_helpers import Person, sign_up
from tests.test_email_connector import FakeSMTP, text_of

LATER = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture
def custodian(client_for: Callable[[], TestClient], session: Session) -> Person:
    return sign_up(client_for, "designcust", custodian=True, session=session)


@pytest.fixture
def mail(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSMTP]:
    fake = FakeSMTP()
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    monkeypatch.setattr(email, "smtp_factory", fake)
    yield fake


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def picture(size: tuple[int, int], kind: str = "PNG", mode: str = "RGB") -> bytes:
    colour = (200, 160, 70, 120) if mode == "RGBA" else (200, 160, 70)
    image = Image.new(mode, size, colour)
    out = BytesIO()
    image.save(out, kind)
    return out.getvalue()


def html_of(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("html",))
    assert part is not None
    return part.get_content()


def made(body: Body, design: Design | None = None) -> EmailMessage:
    mail = email.new_message("someone@example.org", "A subject")
    return email_design.compose(mail, body, design)


# --- the frame --------------------------------------------------------------------


def test_an_email_has_plain_text_and_html_in_the_design() -> None:
    design = Design(site_name="Night Court Mail", accent="#336699", footer="Run by **the Court**.")
    message = made(
        Body(
            text="Hello Ann,\n\nYour results are ready.",
            action=("Read it", "https://horatio.example.org/r"),
            lines=(Line("Why you got this."),),
        ),
        design,
    )

    assert message.get_content_type() == "multipart/alternative"
    text = text_of(message)
    assert text.startswith("Night Court Mail\n\nHello Ann,")
    assert "Read it: https://horatio.example.org/r" in text
    assert "Run by the Court." in text
    assert "Why you got this." in text
    assert text.rstrip().endswith("Sent by Horatio, http://localhost:5173")

    page = html_of(message)
    assert "Night Court Mail" in page
    assert "<strong>the Court</strong>" in page
    assert 'href="https://horatio.example.org/r"' in page
    assert "Sent by Horatio" in page
    assert "#336699" in page
    assert 'name="color-scheme" content="light dark"' in page
    assert "prefers-color-scheme: dark" in page
    assert "max-width: 600px" in page


def test_the_footer_cannot_remove_the_fixed_lines() -> None:
    design = Design(footer="-- \nNothing more.\n\n[Contact us](mailto:court@example.org)")
    message = made(
        Body(text="Hi.", lines=(Line("Stop these", "https://example.org/stop", "Stop"),)),
        design,
    )
    text = text_of(message)
    assert "Stop these Stop: https://example.org/stop" in text
    assert "Sent by Horatio" in text
    assert "Contact us (mailto:court@example.org)" in text
    page = html_of(message)
    assert '<a href="https://example.org/stop"' in page
    assert '<a href="mailto:court@example.org"' in page
    assert "Sent by Horatio" in page


def test_what_the_custodian_writes_is_escaped() -> None:
    footer = "<script>x()</script> [x](javascript:alert(1))"
    design = Design(site_name="<b>Court</b>", footer=footer)
    page = html_of(made(Body(text="Hi."), design))
    assert "<script>" not in page
    assert "&lt;b&gt;Court&lt;/b&gt;" in page
    assert 'href="javascript' not in page


MARKDOWN = """# Venue

The game moves to **Saturday**, at *the Lantern Rooms*.
Doors at seven.

- Bring your [sheet](https://example.org/sheet)
- Pay at the door
<!-- a note for staff -->

3. Third
4. Fourth

> Quoted words
> on two lines

```
<b>kept as written</b>
```

---

<script>alert(1)</script> [no](javascript:alert(1))"""


def test_markdown_becomes_email_html_built_from_the_text() -> None:
    """#831: an announcement's Markdown as the app reads it, and nothing that could
    run or link anywhere but the web."""
    page = email_design.markdown_html(MARKDOWN, "#123456")
    assert 'font-weight: bold; line-height: 1.3">Venue</p>' in page
    assert "The game moves to <strong>Saturday</strong>, at <em>the Lantern Rooms</em>.<br>" in page
    assert "Doors at seven.</p>" in page
    assert '<a href="https://example.org/sheet" style="color: #123456">sheet</a>' in page
    assert page.count("<li ") == 4
    assert '<ol start="3"' in page and "<ul " in page
    assert "<blockquote" in page and "Quoted words<br>on two lines" in page
    assert "&lt;b&gt;kept as written&lt;/b&gt;" in page
    assert '<hr class="h-rule"' in page
    assert "a note for staff" not in page
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert 'href="javascript' not in page


def test_markdown_as_plain_text() -> None:
    text = email_design.markdown_text(MARKDOWN)
    assert text.startswith("Venue\n\nThe game moves to Saturday, at the Lantern Rooms.")
    assert "- Bring your sheet (https://example.org/sheet)" in text
    assert "a note for staff" not in text
    assert "<script>alert(1)</script>" in text  # plain text: shown, never run


def test_a_button_replaces_the_bare_link_in_html_only() -> None:
    url = "https://horatio.example.org/reset/abc"
    message = made(Body(text=f"Hello,\n\nFollow this:\n\n{url}\n\nThanks.", action=("Reset", url)))
    assert url in text_of(message)
    page = html_of(message)
    assert page.count(f'href="{url}"') == 1
    assert ">Reset</a>" in page


def test_without_a_header_picture_the_header_is_the_site_name(kept: Path) -> None:
    message = made(Body(text="Hi."))
    assert len(list(message.walk())) == 3  # alternative, plain, html: nothing attached
    assert "cid:" not in html_of(message)
    assert ">Horatio</td>" in html_of(message)


def test_the_header_picture_is_carried_in_the_email(kept: Path) -> None:
    image = email_design.keep_header(kept, picture((2400, 1200)))
    assert image.width <= 1200 and image.height <= 400
    assert image.name == "header.jpg"
    message = made(Body(text="Hi."), Design(header_image=image))

    assert [p for p in message.walk() if p.get_content_type() == "multipart/related"]
    [attached] = [p for p in message.walk() if p.get_content_maintype() == "image"]
    assert attached.get_content_type() == "image/jpeg"
    cid = str(attached["Content-ID"]).strip("<>")
    page = html_of(message)
    assert f'src="cid:{cid}"' in page
    assert 'alt="Horatio"' in page
    assert "http" not in page.split('src="')[1].split('"')[0]


def test_a_transparent_header_stays_a_png_never_webp(kept: Path) -> None:
    image = email_design.keep_header(kept, picture((300, 100), "WEBP", "RGBA"))
    assert image.name == "header.png"
    assert (email_design.header_dir(kept, image.id) / "header.png").read_bytes()[:4] == b"\x89PNG"


def test_a_header_too_big_for_email_is_refused(kept: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_design, "HEADER_LIMIT", 100)
    with pytest.raises(DesignError):
        email_design.keep_header(kept, picture((600, 200)))


def test_pictures_of_the_email_are_attached_for_its_html() -> None:
    body = Body(
        text="A picture.",
        html='<p>A picture.</p><img src="cid:pic-1@horatio" alt="">',
        images=(InlineImage("pic-1@horatio", picture((40, 40)), "png"),),
    )
    message = made(body)
    [attached] = [p for p in message.walk() if p.get_content_maintype() == "image"]
    assert str(attached["Content-ID"]) == "<pic-1@horatio>"


def test_colours_are_checked() -> None:
    with pytest.raises(DesignError):
        email_design.checked({"accent": "gold"})
    with pytest.raises(DesignError):
        email_design.checked({"footer": "x" * (email_design.FOOTER_MAX + 1)})
    assert email_design.checked({"accent": "#ABCDEF", "site_name": "  "}) == {"accent": "#abcdef"}


def test_links_stay_readable_whatever_the_accent() -> None:
    link = email_design.readable("#ffff00", email_design.CARD, "#000000")
    assert email_design.contrast(link, email_design.CARD) >= 4.5


# --- the emails Horatio sends -----------------------------------------------------


def test_a_password_reset_comes_in_the_design(
    client_for: Callable[[], TestClient],
    session: Session,
    mail: FakeSMTP,
    custodian: Person,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The link someone asks for is sent after the answer, in its own session: the test's.
    monkeypatch.setattr(auth_api, "background_session", lambda: nullcontext(session))
    custodian.client.put("/site/email-design", json={"site_name": "Court Mail"})
    sign_up(client_for, "forgetful")
    client_for().post("/auth/forgot", json={"email": "forgetful@example.com"})
    [sent] = mail.sent
    assert text_of(sent).startswith("Court Mail\n\n")
    assert "Court Mail" in html_of(sent)
    assert ">Set a new password</a>" in html_of(sent)


# --- the card ---------------------------------------------------------------------


def test_only_the_custodian_has_the_card(client_for: Callable[[], TestClient]) -> None:
    someone = sign_up(client_for, "notcust")
    assert someone.client.get("/site/email-design").status_code == 403
    assert someone.client.put("/site/email-design", json={}).status_code == 403
    assert someone.client.get("/site/email-design/preview").status_code == 403
    assert someone.client.post("/site/email-design/test").status_code == 403
    assert someone.client.delete("/site/email-design/header").status_code == 403


def test_the_card_starts_with_horatios_own_and_saves_what_is_set(
    custodian: Person, session: Session
) -> None:
    found = custodian.client.get("/site/email-design").json()
    assert found["site_name"] == "Horatio"
    assert found["accent"] == "#c9a24a"
    assert found["chosen"] == []
    assert found["header_image"] is None

    saved = custodian.client.put(
        "/site/email-design",
        json={"site_name": "Court Mail", "accent": "#336699", "footer": "Run by the Court."},
    ).json()
    assert saved["site_name"] == "Court Mail"
    assert sorted(saved["chosen"]) == ["accent", "footer", "site_name"]
    logged = session.scalars(select(AuditEvent).where(AuditEvent.action == "mail.design_set")).all()
    assert len(logged) == 1
    assert "the accent colour" in logged[0].data["changed"]

    back = custodian.client.put("/site/email-design", json={}).json()
    assert back["site_name"] == "Horatio"
    assert back["chosen"] == []


def test_a_bad_colour_is_refused(custodian: Person) -> None:
    answer = custodian.client.put("/site/email-design", json={"accent": "red"})
    assert answer.status_code == 422
    assert "colour like" in answer.json()["detail"]


def test_hard_to_read_header_colours_are_warned_about(custodian: Person) -> None:
    found = custodian.client.put(
        "/site/email-design", json={"header_colour": "#777777", "header_text_colour": "#888888"}
    ).json()
    assert found["warnings"]


def test_uploading_and_removing_the_header(custodian: Person, kept: Path) -> None:
    files = {"file": ("logo.png", picture((800, 200)), "image/png")}
    found = custodian.client.post("/site/email-design/header", files=files).json()
    image = found["header_image"]
    assert image["width"] == 800
    shown = custodian.client.get(image["url"].removeprefix("/api"))
    assert shown.status_code == 200
    assert shown.headers["content-type"] in ("image/jpeg", "image/png")

    preview = custodian.client.get("/site/email-design/preview?scheme=dark").json()
    assert "data:image/" in preview["html"]
    assert "cid:" not in preview["html"]
    assert preview["text"].startswith("Horatio\n\n")

    replaced = custodian.client.post("/site/email-design/header", files=files).json()
    assert replaced["header_image"]["url"] != image["url"]
    assert len(list((kept / "email").iterdir())) == 1

    gone = custodian.client.delete("/site/email-design/header").json()
    assert gone["header_image"] is None
    assert list((kept / "email").iterdir()) == []


def test_a_file_that_is_not_a_picture_is_refused(custodian: Person, kept: Path) -> None:
    files = {"file": ("logo.png", b"not a picture", "image/png")}
    assert custodian.client.post("/site/email-design/header", files=files).status_code == 422


def test_the_test_email_goes_to_the_custodian_in_the_design(
    custodian: Person, mail: FakeSMTP, session: Session
) -> None:
    custodian.client.put("/site/email-design", json={"footer": "With love from the Court."})
    answer = custodian.client.post("/site/email-design/test").json()
    assert answer["ok"] is True
    [sent] = mail.sent
    assert "designcust@example.com" in str(sent["To"])
    assert "With love from the Court." in text_of(sent)
    assert "With love from the Court." in html_of(sent)
    assert session.scalar(select(AuditEvent).where(AuditEvent.action == "mail.design_test_sent"))


def test_no_test_while_mail_is_off(custodian: Person) -> None:
    assert custodian.client.post("/site/email-design/test").status_code == 409
