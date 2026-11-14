"""How every email Horatio sends looks (#830): a header and a footer the custodian
sets on Custodian › Site, around what each email says, as plain text and as HTML.

The design is one server setting (`ServerSetting` "email_design"): the site's name,
the header's colour and its text's, an accent for links and buttons, a short footer
in Markdown, and an optional header picture. Blank parts use `DEFAULTS`, so with
nothing set an email has the site's name on Horatio's night, and its gold.

`compose` fills a message from `horatio.connectors.email.new_message`: a plain-text
part, and an HTML part beside it with its pictures attached (`cid:`), never linked
from the server, so they show without signing in and nobody learns who opened it.
What an email says is a `Body`: its text, HTML made from it (or given, for an email
with more to show, such as an announcement with its picture, #831), a button, the
lines only it has (why it came, how to stop it), and pictures of its own. Under the
custodian's footer every email ends with its own lines and "Sent by Horatio, ‹site›",
which the custodian's footer cannot remove.

The HTML is built for mail clients: tables and inline styles, no web fonts, at most
600 px wide, readable with pictures blocked, and with colours that still read where
a client darkens it (a `prefers-color-scheme` block for those that ask, plain
colours for those that invert).
"""

import base64
import html
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from email.message import EmailMessage
from email.utils import make_msgid
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image
from sqlalchemy.orm import Session

from horatio import pictures
from horatio.config import get_settings
from horatio.models import ServerSetting

KEY = "email_design"

# Horatio's own: its night and parchment, and its gold.
DEFAULTS = {
    "site_name": "Horatio",
    "header_colour": "#141016",
    "header_text_colour": "#f0e6d2",
    "accent": "#c9a24a",
    "footer": "",
}
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
SITE_NAME_MAX = 80
FOOTER_MAX = 1000

# The header picture: kept at most this wide (shown at half, for sharp screens) and
# this tall, and small enough that every email can carry it.
HEADER_WIDTH = 1200
HEADER_HEIGHT = 400
# Aim for this many bytes, and refuse a picture that can't be made this small.
HEADER_TARGET = 200 * 1024
HEADER_LIMIT = 300 * 1024
HEADER_FILES = {"header.png": "image/png", "header.jpg": "image/jpeg"}

# The email itself: its page, its card, and the words under it, light and dark.
PAGE = "#f4f1ec"
CARD = "#ffffff"
INK = "#222222"
MUTED = "#6b645c"
RULE = "#e2dbd0"
DARK_PAGE = "#16131a"
DARK_CARD = "#211d26"
DARK_INK = "#ece6da"
DARK_MUTED = "#b4aa9c"
DARK_RULE = "#3a3440"
SERIF = "Georgia, 'Times New Roman', serif"
SANS = "Arial, Helvetica, sans-serif"


class DesignError(Exception):
    """A design or header picture Horatio can't use; the message says why."""


@dataclass(frozen=True)
class HeaderImage:
    id: uuid.UUID
    # "header.png" or "header.jpg".
    name: str
    width: int
    height: int
    size: int


@dataclass(frozen=True)
class Design:
    site_name: str = DEFAULTS["site_name"]
    header_colour: str = DEFAULTS["header_colour"]
    header_text_colour: str = DEFAULTS["header_text_colour"]
    accent: str = DEFAULTS["accent"]
    # Markdown: paragraphs, **bold**, *italic*, [links](https://…) and bare links.
    footer: str = DEFAULTS["footer"]
    header_image: HeaderImage | None = None


@dataclass(frozen=True)
class Line:
    """A line under the footer that this email has: why it came, or how to stop it.
    With a `url` and a `label`, plain text reads "text label: url" and HTML "text"
    and `label` as the link; with a `url` alone, "text: url", the url as the link."""

    text: str
    url: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class InlineImage:
    """A picture the email carries, shown where its HTML says `cid:<cid>`."""

    cid: str
    data: bytes
    subtype: Literal["png", "jpeg"]


@dataclass(frozen=True)
class Body:
    """What one email says, between the header and the footer."""

    # The words, as plain text: paragraphs apart by a blank line.
    text: str
    # The same as HTML, safe to put in the page; None makes it from `text`, with
    # **bold**, *italic* and links.
    html: str | None = None
    # A button: its words and where it goes. Plain text reads "words: url".
    action: tuple[str, str] | None = None
    # This email's own lines, under the custodian's footer.
    lines: Sequence[Line] = ()
    # Pictures `html` shows with cid: (#831's announcement picture).
    images: Sequence[InlineImage] = ()
    # The line mail clients show after the subject, in the list.
    preheader: str | None = None


# --- the setting --------------------------------------------------------------------


def stored(db: Session) -> dict[str, Any]:
    row = db.get(ServerSetting, KEY)
    return dict(row.value) if row is not None and isinstance(row.value, dict) else {}


def header_from(value: Any) -> HeaderImage | None:
    if not isinstance(value, dict):
        return None
    try:
        image = HeaderImage(
            id=uuid.UUID(str(value["id"])),
            name=str(value["name"]),
            width=int(value["width"]),
            height=int(value["height"]),
            size=int(value.get("size", 0)),
        )
    except (KeyError, ValueError, TypeError):
        return None
    return image if image.name in HEADER_FILES else None


def current(db: Session) -> Design:
    """The design now: what the custodian set, the defaults for the rest."""
    kept = stored(db)
    chosen = {
        part: str(kept[part])
        for part in DEFAULTS
        if isinstance(kept.get(part), str) and kept[part].strip()
    }
    return Design(**chosen, header_image=header_from(kept.get("header_image")))


def checked(parts: dict[str, str | None]) -> dict[str, str]:
    """What the custodian sent, tidied and checked; blank parts are left out (the
    default). Raises DesignError saying what's wrong."""
    out: dict[str, str] = {}
    name = (parts.get("site_name") or "").strip()
    if len(name) > SITE_NAME_MAX:
        raise DesignError(f"The site's name can be at most {SITE_NAME_MAX} characters.")
    if name:
        out["site_name"] = name
    for part, what in (
        ("header_colour", "The header colour"),
        ("header_text_colour", "The header's text colour"),
        ("accent", "The accent colour"),
    ):
        value = (parts.get(part) or "").strip()
        if not value:
            continue
        if not COLOUR.match(value):
            raise DesignError(f"{what} must be a colour like #c9a24a.")
        out[part] = value.lower()
    footer = (parts.get("footer") or "").strip()
    if len(footer) > FOOTER_MAX:
        raise DesignError(f"The footer can be at most {FOOTER_MAX} characters.")
    if footer:
        out["footer"] = footer
    return out


def save(db: Session, parts: dict[str, str]) -> None:
    """Keep the custodian's parts (from `checked`), keeping the header picture."""
    kept = stored(db)
    value: dict[str, Any] = dict(parts)
    if "header_image" in kept:
        value["header_image"] = kept["header_image"]
    put(db, value)


def put(db: Session, value: dict[str, Any]) -> None:
    row = db.get(ServerSetting, KEY)
    if row is None:
        db.add(ServerSetting(key=KEY, value=value))
    else:
        row.value = value
    db.flush()


# --- colours ------------------------------------------------------------------------


def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    r, g, b = (int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mix(colour: str, towards: str, amount: float) -> str:
    parts = []
    for i in (1, 3, 5):
        a, b = int(colour[i : i + 2], 16), int(towards[i : i + 2], 16)
        parts.append(round(a + (b - a) * amount))
    return "#" + "".join(f"{p:02x}" for p in parts)


def readable(colour: str, on: str, towards: str) -> str:
    """`colour`, moved towards `towards` until it reads on `on` (4.5:1)."""
    for step in range(11):
        tried = _mix(colour, towards, step / 10)
        if contrast(tried, on) >= 4.5:
            return tried
    return towards


def button_text(accent: str) -> str:
    return "#111111" if contrast(accent, "#111111") >= contrast(accent, "#ffffff") else "#ffffff"


def warnings(design: Design) -> list[str]:
    """What may be hard to read, for the custodian to see."""
    found: list[str] = []
    if contrast(design.header_colour, design.header_text_colour) < 4.5:
        found.append("The header's text is hard to read on its colour. Pick colours further apart.")
    return found


# --- the header picture -------------------------------------------------------------


def header_dir(root: Path, image_id: uuid.UUID) -> Path:
    return root / "email" / str(image_id)


def header_file(root: Path, image: HeaderImage) -> Path | None:
    path = header_dir(root, image.id) / image.name
    return path if path.is_file() else None


def _encoded(image: Image.Image) -> tuple[bytes, str]:
    """The picture as small a PNG (with transparency) or JPEG as reads well."""
    lowest = image.getchannel("A").getextrema()[0] if image.mode == "RGBA" else 255
    if isinstance(lowest, int | float) and lowest < 255:
        out = BytesIO()
        image.save(out, "PNG", optimize=True)
        if out.tell() > HEADER_TARGET:
            out = BytesIO()
            image.quantize(256).save(out, "PNG", optimize=True)
        return out.getvalue(), "header.png"
    flat = image.convert("RGB")
    data = b""
    for quality in (88, 80, 72, 64):
        out = BytesIO()
        flat.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        data = out.getvalue()
        if len(data) <= HEADER_TARGET:
            break
    return data, "header.jpg"


def header_for_email(image: Image.Image) -> tuple[bytes, str, int, int]:
    """The header picture, made for email: never wider than HEADER_WIDTH or taller
    than HEADER_HEIGHT, as PNG or JPEG (never WebP: not every mail client shows it).
    Its bytes, file name, width and height. Refused if it can't be made small."""
    fitted = image.copy()
    fitted.thumbnail((HEADER_WIDTH, HEADER_HEIGHT), Image.Resampling.LANCZOS)
    data, name = _encoded(fitted)
    if len(data) > HEADER_LIMIT:
        raise DesignError(
            "That picture is too detailed to send in every email, even made smaller. "
            "Try a simpler one, such as a logo on a plain background."
        )
    return data, name, fitted.width, fitted.height


def keep_header(root: Path, upload: bytes) -> HeaderImage:
    """Write an uploaded header picture under `root`, in a new directory. Raises
    pictures.PictureError or DesignError when it can't be used."""
    image = pictures.read_image(upload)
    data, name, width, height = header_for_email(image)
    image_id = uuid.uuid4()
    directory = header_dir(root, image_id)
    directory.mkdir(parents=True)
    (directory / name).write_bytes(data)
    return HeaderImage(id=image_id, name=name, width=width, height=height, size=len(data))


def header_value(image: HeaderImage) -> dict[str, Any]:
    return {
        "id": str(image.id),
        "name": image.name,
        "width": image.width,
        "height": image.height,
        "size": image.size,
    }


def header_bytes(design: Design) -> tuple[bytes, Literal["png", "jpeg"]] | None:
    image = design.header_image
    root = pictures.upload_dir()
    if image is None or root is None:
        return None
    path = header_file(root, image)
    if path is None:
        return None
    return path.read_bytes(), "png" if image.name.endswith(".png") else "jpeg"


# --- words --------------------------------------------------------------------------

INLINE = re.compile(
    r"(\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\((?:https?://|mailto:)[^)\s]+\)|https?://\S+)"
)
LINK = re.compile(r"\[([^\]\n]+)\]\(((?:https?://|mailto:)[^)\s]+)\)")


def inline_html(line: str, link_colour: str | None = None) -> str:
    """One line as HTML: **bold**, *italic*, [words](link) and bare links; everything
    else escaped."""
    style = f' style="color: {link_colour}"' if link_colour else ""
    out: list[str] = []
    for part in INLINE.split(line):
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(f"<strong>{html.escape(part[2:-2])}</strong>")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"<em>{html.escape(part[1:-1])}</em>")
        elif (found := LINK.fullmatch(part)) is not None:
            url = html.escape(found.group(2), quote=True)
            out.append(f'<a href="{url}"{style}>{html.escape(found.group(1))}</a>')
        elif part.startswith(("http://", "https://")):
            url = html.escape(part, quote=True)
            out.append(f'<a href="{url}"{style}>{url}</a>')
        else:
            out.append(html.escape(part))
    return "".join(out)


def inline_text(line: str) -> str:
    """One line as plain text: marks dropped, [words](link) as "words (link)"."""
    line = LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", line)
    return re.sub(r"\*\*([^*\n]+)\*\*|\*([^*\n]+)\*", lambda m: m.group(1) or m.group(2), line)


def paragraphs(text: str) -> list[str]:
    return [p.strip("\n") for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def text_html(text: str, link_colour: str | None = None, style: str = "") -> str:
    """Paragraphs of text as HTML paragraphs, lines kept."""
    attr = f' style="{style}"' if style else ""
    return "\n".join(
        f"<p{attr}>" + "<br>".join(inline_html(ln, link_colour) for ln in p.split("\n")) + "</p>"
        for p in paragraphs(text)
    )


def site() -> str:
    return get_settings().public_url.rstrip("/")


# --- putting an email together ------------------------------------------------------


def line_text(line: Line) -> str:
    if line.url is None:
        return line.text
    if line.label:
        return f"{line.text} {line.label}: {line.url}"
    return f"{line.text}: {line.url}"


def line_html(line: Line, link: str, style: str) -> str:
    if line.url is None:
        return f'<p style="{style}">{html.escape(line.text)}</p>'
    anchor = (
        f'<a href="{html.escape(line.url, quote=True)}" style="color: {link}">'
        f"{html.escape(line.label or line.url)}</a>"
    )
    joiner = " " if line.label else ": "
    return f'<p style="{style}">{html.escape(line.text)}{joiner}{anchor}</p>'


def plain(body: Body, design: Design) -> str:
    parts = [design.site_name, "", body.text.strip()]
    if body.action is not None and body.action[1] not in body.text:
        parts += ["", f"{body.action[0]}: {body.action[1]}"]
    parts += ["", "-- "]
    if design.footer:
        parts += [inline_text(p) for p in paragraphs(design.footer)] + [""]
    for line in body.lines:
        parts.append(line_text(line))
    parts.append(f"Sent by Horatio, {site()}")
    return "\n".join(parts) + "\n"


DARK_CSS = f"""
.h-page {{ background: {DARK_PAGE} !important; }}
.h-card {{ background: {DARK_CARD} !important; color: {DARK_INK} !important; }}
.h-card p, .h-card li, .h-card td {{ color: {DARK_INK} !important; }}
.h-muted, .h-muted p {{ color: {DARK_MUTED} !important; }}
.h-rule {{ border-color: {DARK_RULE} !important; }}
"""


def page(
    body: Body,
    design: Design,
    *,
    subject: str,
    header_src: str | None,
    scheme: Literal["auto", "light", "dark"] = "auto",
) -> str:
    """The email as an HTML page. `header_src` is where its header picture is
    (cid: in an email, data: in a preview); `scheme` forces light or dark, for the
    preview, where "auto" follows the reader's mail client."""
    accent = design.accent
    link = readable(accent, CARD, "#000000")
    dark_link = readable(accent, DARK_CARD, "#ffffff")
    dark_rule = f".h-card a, .h-muted a {{ color: {dark_link} !important; }}"
    if scheme == "dark":
        dark = f"<style>{DARK_CSS}{dark_rule}</style>"
    elif scheme == "light":
        dark = ""
    else:
        dark = f"<style>@media (prefers-color-scheme: dark) {{{DARK_CSS}{dark_rule}}}</style>"
    name = html.escape(design.site_name)
    if header_src is not None and design.header_image is not None:
        shown_width = min(600, round(design.header_image.width / 2) or 600)
        header = (
            f'<img src="{html.escape(header_src, quote=True)}" width="{shown_width}" '
            f'alt="{name}" style="display: block; margin: 0 auto; width: 100%; '
            f"max-width: {shown_width}px; height: auto; border: 0; outline: none; "
            f"background: {design.header_colour}; color: {design.header_text_colour}; "
            f'font-family: {SERIF}; font-size: 22px; line-height: 1.3">'
        )
        header_pad = "12px 16px"
    else:
        header = name
        header_pad = "20px 28px"
    if body.html is not None:
        content = body.html
    else:
        # The button carries the link, so a paragraph of only its address goes.
        shown = [p for p in paragraphs(body.text) if body.action is None or p != body.action[1]]
        content = text_html("\n\n".join(shown), link, "margin: 0 0 16px 0")
    button = ""
    if body.action is not None:
        words, url = body.action
        button = (
            '<table role="presentation" cellpadding="0" cellspacing="0" '
            'style="margin: 8px 0 4px 0"><tr>'
            f'<td style="background: {accent}; border-radius: 4px">'
            f'<a href="{html.escape(url, quote=True)}" style="display: inline-block; '
            f"padding: 10px 18px; font-family: {SANS}; font-size: 15px; font-weight: bold; "
            f'color: {button_text(accent)}; text-decoration: none">{html.escape(words)}</a>'
            "</td></tr></table>"
        )
    muted = "margin: 0 0 8px 0"
    footer = text_html(design.footer, link, muted) if design.footer else ""
    lines = "".join(line_html(line, link, muted) for line in body.lines)
    rule = f'<hr class="h-rule" style="border: 0; border-top: 1px solid {RULE}; margin: 12px 0">'
    sent = (
        f'<p style="margin: 0">Sent by Horatio, '
        f'<a href="{html.escape(site(), quote=True)}" style="color: {link}">'
        f"{html.escape(site())}</a></p>"
    )
    preheader = (
        '<div style="display: none; max-height: 0; overflow: hidden; mso-hide: all">'
        f"{html.escape(body.preheader)}</div>"
        if body.preheader
        else ""
    )
    table = 'role="presentation" cellpadding="0" cellspacing="0"'
    narrow = (
        "@media (max-width: 620px) { .h-wrap { width: 100% !important; }"
        " .h-pad { padding: 16px !important; } }"
    )
    header_style = (
        f"background: {design.header_colour}; color: {design.header_text_colour}; "
        f"padding: {header_pad}; font-family: {SERIF}; font-size: 22px; line-height: 1.3; "
        "border-radius: 6px 6px 0 0"
    )
    card_style = (
        f"background: {CARD}; color: {INK}; padding: 24px 28px; font-family: {SERIF}; "
        f"font-size: 16px; line-height: 1.55; border-top: 3px solid {accent}"
    )
    foot_style = (
        f"padding: 16px 28px; color: {MUTED}; font-family: {SANS}; font-size: 13px; "
        "line-height: 1.5"
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>{html.escape(subject)}</title>
<style>
body {{ margin: 0; padding: 0; }}
{narrow}
</style>
{dark}
</head>
<body class="h-page" style="margin: 0; padding: 0; background: {PAGE}">
{preheader}
<table {table} width="100%" class="h-page" style="background: {PAGE}">
<tr><td align="center" style="padding: 24px 12px">
<table {table} width="600" class="h-wrap" style="width: 600px; max-width: 600px">
<tr><td align="center" style="{header_style}">{header}</td></tr>
<tr><td class="h-card h-pad" style="{card_style}">
{content}
{button}
</td></tr>
<tr><td class="h-muted h-pad" style="{foot_style}">
{footer}{rule if footer else ""}{lines}{sent}
</td></tr>
</table>
</td></tr></table>
</body></html>
"""


def compose(mail: EmailMessage, body: Body, design: Design | None = None) -> EmailMessage:
    """Fill `mail` (from new_message) with `body` in `design` (or the defaults): a
    plain-text part and an HTML part, its pictures attached to it. Returns `mail`."""
    design = design or Design()
    header = header_bytes(design)
    header_cid = make_msgid(domain="horatio") if header is not None else None
    src = f"cid:{header_cid[1:-1]}" if header_cid is not None else None
    subject = str(mail["Subject"] or "")
    mail.set_content(plain(body, design))
    shown = design if header is not None else replace(design, header_image=None)
    mail.add_alternative(page(body, shown, subject=subject, header_src=src), subtype="html")
    part = mail.get_body(preferencelist=("html",))
    assert part is not None
    if header is not None and header_cid is not None:
        data, subtype = header
        part.add_related(data, maintype="image", subtype=subtype, cid=header_cid)
    for image in body.images:
        part.add_related(image.data, maintype="image", subtype=image.subtype, cid=f"<{image.cid}>")
    return mail


def preview(
    body: Body, design: Design, *, subject: str, scheme: Literal["light", "dark"]
) -> tuple[str, str]:
    """The email as the custodian's preview shows it: its HTML, with its pictures as
    data: addresses in place of cid:, and its plain text."""
    header = header_bytes(design)
    src = None
    shown = design
    if header is not None:
        data, subtype = header
        src = f"data:image/{subtype};base64,{base64.b64encode(data).decode()}"
    else:
        shown = replace(design, header_image=None)
    page_html = page(body, shown, subject=subject, header_src=src, scheme=scheme)
    for image in body.images:
        page_html = page_html.replace(
            f"cid:{image.cid}",
            f"data:image/{image.subtype};base64,{base64.b64encode(image.data).decode()}",
        )
    return page_html, plain(body, design)


@dataclass(frozen=True)
class Sample:
    """The email the preview and the test show."""

    subject: str
    body: Body = field(default_factory=lambda: Body(text=""))


def sample(name: str) -> Sample:
    return Sample(
        subject="A test email from Horatio",
        body=Body(
            text=(
                f"Hello {name},\n\n"
                "This is how Horatio's emails look: the header and footer set on "
                "Custodian › Site, around what each email says.\n\n"
                "**Bold**, *italic* and links such as https://example.org show as they "
                "would in a notification."
            ),
            action=("Open Horatio", site()),
            lines=(
                Line("You get this because you're Horatio's custodian."),
                Line("Choose which emails you get.", f"{site()}/account/settings", "Settings"),
            ),
            preheader="How Horatio's emails look.",
        ),
    )
