"""What a troupe announcement's email carries (#831): the announcement itself, not
just its title. Announcements are out of character, for everyone in the troupe, and
the one kind of email that is on until turned off, so the email brings the title,
who it is from and their role, the troupe, its picture and its words, with a button
to read it in Horatio. Only the one-at-a-time email does: the daily digest keeps a
title line and a link for each, so one digest never carries several large pictures.

The announcement is found from the notice's link when the email goes, as the bell
finds its picture (horatio.notifications.announcement_pictures): it is sent as it
then stands, and only while it is still a published announcement and the person
is still in its troupe. Otherwise the email is the plain line it always was.
Editing an announcement once it is out sends no new email.

The picture goes inside the email (`cid:`), never linked from the server: a JPEG at
most `PICTURE_WIDTH` wide, made from the announcement's stored picture, and left
out if it cannot be made smaller than `PICTURE_LIMIT`. Never WebP, which not every
mail client shows.
"""

import html
import re
import uuid
from dataclasses import dataclass
from email.utils import make_msgid
from functools import lru_cache
from io import BytesIO

from PIL import Image
from sqlalchemy.orm import Session

from horatio import pictures
from horatio.email_design import (
    CARD,
    MUTED,
    SANS,
    Design,
    InlineImage,
    markdown_html,
    markdown_text,
    readable,
)
from horatio.models import EmailNotice, Post, Troupe, User
from horatio.permissions import member_troupe_ids

# Where an announcement is read, as its notices link to it (horatio.posts.link).
ANNOUNCEMENT_LINK = re.compile(r"^/troupes/[0-9a-f-]{36}/announcements/([0-9a-f-]{36})$")
# The stored picture the email's is made from: wide enough to look sharp at 600.
SOURCE = "1200.webp"
PICTURE_WIDTH = 600
PICTURE_LIMIT = 200 * 1024
QUALITIES = (85, 78, 70, 62)


@dataclass(frozen=True)
class Content:
    """What the email says, between the design's header and footer."""

    text: str
    html: str
    images: tuple[InlineImage, ...]
    preheader: str


def found(db: Session, user: User, notice: EmailNotice) -> Post | None:
    """The published announcement a notice is about, if `user` may still read it."""
    if notice.topic != "announcements":
        return None
    matched = ANNOUNCEMENT_LINK.match(notice.link)
    if matched is None:
        return None
    post = db.get(Post, uuid.UUID(matched.group(1)))
    if post is None or post.kind != "announcement" or post.status != "published":
        return None
    return post if post.troupe_id in member_troupe_ids(db, user) else None


@lru_cache(maxsize=16)
def _jpeg(troupe_id: uuid.UUID, picture_id: uuid.UUID) -> bytes | None:
    """The picture for an email, or None if there is none or it can't be made small.
    A picture is never changed in place (a new one gets a new id), so it is kept."""
    root = pictures.upload_dir()
    if root is None:
        return None
    path = pictures.post_picture_file(root, troupe_id, picture_id, SOURCE)
    if path is None:
        return None
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    image.thumbnail((PICTURE_WIDTH, PICTURE_WIDTH * 4), Image.Resampling.LANCZOS)
    flat = Image.new("RGB", image.size, (255, 255, 255))
    flat.paste(image, mask=image.getchannel("A"))
    for quality in QUALITIES:
        out = BytesIO()
        flat.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        if out.tell() <= PICTURE_LIMIT:
            return out.getvalue()
    return None


def picture(post: Post) -> InlineImage | None:
    if post.picture_id is None:
        return None
    data = _jpeg(post.troupe_id, post.picture_id)
    if data is None:
        return None
    return InlineImage(cid=make_msgid(domain="horatio")[1:-1], data=data, subtype="jpeg")


def content(db: Session, user: User, notice: EmailNotice, design: Design) -> Content | None:
    """The announcement a notice is about, as its email shows it; None to send the
    plain line instead."""
    post = found(db, user, notice)
    if post is None:
        return None
    troupe = db.get_one(Troupe, post.troupe_id)
    image = picture(post)
    link = readable(design.accent, CARD, "#000000")
    small = f"margin: 0 0 4px 0; font-family: {SANS}; font-size: 13px; color: {MUTED}"
    shown = [
        # In a h-muted block, so a mail client that darkens the email keeps it muted.
        f'<div class="h-muted"><p style="{small}">'
        f"Announcement · {html.escape(troupe.name)}</p></div>",
        f'<h1 style="margin: 0 0 6px 0; font-size: 24px; line-height: 1.25; '
        f'font-weight: normal">{html.escape(post.title)}</h1>',
    ]
    if post.byline:
        shown.append(
            f'<div class="h-muted"><p style="{small}; font-size: 14px; margin-bottom: 16px">'
            f"{html.escape(post.byline)}</p></div>"
        )
    if image is not None:
        shown.append(
            f'<img src="cid:{image.cid}" width="{PICTURE_WIDTH}" alt="" '
            'style="display: block; width: 100%; max-width: 600px; height: auto; '
            'border: 0; border-radius: 4px; margin: 0 0 16px 0">'
        )
    if post.body.strip():
        shown.append(markdown_html(post.body, link))
    words = [f"{troupe.name}: announcement", "", post.title]
    if post.byline:
        words.append(post.byline)
    if post.body.strip():
        words += ["", markdown_text(post.body)]
    return Content(
        text="\n".join(words),
        html="\n".join(shown),
        images=(image,) if image is not None else (),
        preheader=f"{troupe.name}: {post.title}",
    )
