"""What a link to one of Horatio's public pages shows where it is shared (#1162): in a
chat, on social media or in a search result. The app draws its pages in the browser,
so the API puts each page's own title, description and picture into index.html for
the sites that only read the page's head (horatio.app.serve_frontend).

Public pages have their own: the landing page (/, #1164), a troupe's public profile
(/t/<troupe>), the blog
(/blog), an article (/blog/<slug>), a tag's page (/blog/tags/<tag>) and an author's
page (/blog/authors/<handle>). Only what anyone may read goes in: an article that is
not published, a tag that has gone, or an author whose page is not shown, keeps the
site's own preview, which says nothing about it.
"""

import html
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import pictures
from horatio.api import blog_authors, troupe_profiles
from horatio.api.blog_public import authors_of, published
from horatio.blog import tags_of
from horatio.email_design import MD_FIGURE, MD_HEADING, markdown_text
from horatio.models import BlogPost, BlogTag

# What the landing page says Horatio is (frontend/src/pages/LandingPage.tsx).
HOME_TITLE = "Horatio"
HOME_DESCRIPTION = (
    "Character sheets, downtimes and game nights for Mind's Eye Theatre LARP troupes."
    " Read the blog, and find a troupe to play in."
)

# What the blog says it is: as its page's subtitle (frontend/src/pages/blog/BlogPage.tsx).
BLOG_TITLE = "Horatio's blog"
BLOG_DESCRIPTION = (
    "Essays by the staff of troupes on Horatio: on playing, running a game, and the tricks of both."
)
# The longest description a preview gives: sites cut them shorter anyway.
LONGEST = 200

PUBLIC_PROFILE = re.compile(r"t/([0-9a-fA-F-]{36})/?")
ARTICLE = re.compile(r"blog/([^/]+)/?")
TAG = re.compile(r"blog/tags/([^/]+)/?")
AUTHOR = re.compile(r"blog/authors/([^/]+)/?")


@dataclass(frozen=True)
class Feed:
    """A feed to name in the page's head, for feed readers to find."""

    title: str
    path: str


@dataclass(frozen=True)
class LinkPreview:
    title: str
    description: str
    # The page's <title>, as the app sets it once it has loaded.
    page_title: str
    # The picture's address on this site; empty keeps the site's own picture.
    image: str = ""
    # Its width and height, where known.
    image_size: tuple[int, int] | None = None
    # twitter:card: "summary" for a small square picture, "summary_large_image" for a
    # wide one; empty keeps the site's.
    card: str = ""
    # og:type.
    kind: str = "website"
    # The page's own address on this site (og:url), if it has one to give.
    path: str = ""
    # More <meta property=...> tags, such as an article's dates.
    more: tuple[tuple[str, str], ...] = ()
    feeds: tuple[Feed, ...] = ()


def with_preview(index: str, preview: LinkPreview, public_url: str) -> str:
    """index.html with its link preview made `preview`."""

    def meta(attribute: str, name: str, value: str, page: str) -> str:
        tag = re.compile(rf'<meta {attribute}="{re.escape(name)}" content="[^"]*" />')
        return tag.sub(
            lambda _: f'<meta {attribute}="{name}" content="{html.escape(value)}" />', page
        )

    page = meta("property", "og:title", preview.title, index)
    page = meta("property", "og:description", preview.description, page)
    page = meta("name", "description", preview.description, page)
    page = meta("property", "og:type", preview.kind, page)
    if preview.image:
        page = meta("property", "og:image", public_url + preview.image, page)
        if preview.image_size:
            page = meta("property", "og:image:width", str(preview.image_size[0]), page)
            page = meta("property", "og:image:height", str(preview.image_size[1]), page)
        else:
            # The site's picture's size is not this one's.
            page = re.sub(
                r'\s*<meta property="og:image:(width|height)" content="[^"]*" />', "", page
            )
    if preview.card:
        page = meta("name", "twitter:card", preview.card, page)
    added: list[str] = ['<meta property="og:site_name" content="Horatio" />']
    if preview.path:
        url = html.escape(public_url + preview.path)
        added += [
            f'<meta property="og:url" content="{url}" />',
            f'<link rel="canonical" href="{url}" />',
        ]
    added += [
        f'<meta property="{html.escape(name)}" content="{html.escape(value)}" />'
        for name, value in preview.more
    ]
    added += [
        f'<link rel="alternate" type="application/atom+xml" title="{html.escape(feed.title)}" '
        f'href="{html.escape(public_url + feed.path)}" />'
        for feed in preview.feeds
    ]
    page = page.replace("</head>", "".join(f"    {tag}\n" for tag in added) + "  </head>", 1)
    return page.replace(
        "<title>Horatio</title>", f"<title>{html.escape(preview.page_title)}</title>"
    )


def for_path(db: Session, path: str) -> LinkPreview | None:
    """The link preview of the page at `path` (with no leading slash), or None for the
    site's own."""
    if path == "":
        return home()
    if found := PUBLIC_PROFILE.fullmatch(path):
        return troupe(db, found.group(1))
    if path.rstrip("/") == "blog":
        return blog()
    if found := TAG.fullmatch(path):
        return tag(db, found.group(1))
    if found := AUTHOR.fullmatch(path):
        return author(db, found.group(1))
    if found := ARTICLE.fullmatch(path):
        return article(db, found.group(1))
    return None


def shortened(text: str) -> str:
    """The first paragraph of `text`, no longer than a preview shows."""
    first = text.strip().split("\n\n")[0].replace("\n", " ").strip()
    return first if len(first) <= LONGEST else first[: LONGEST - 1].rstrip() + "…"


def troupe(db: Session, troupe_id: str) -> LinkPreview | None:
    try:
        found = troupe_profiles.link_preview(db, uuid.UUID(troupe_id))
    except ValueError:
        return None
    if found is None:
        return None
    return LinkPreview(
        title=found["title"],
        description=found["description"],
        page_title=f"{found['title']} · Horatio",
        image=found["image"],
        image_size=(512, 512) if found["image"] else None,
        card="summary" if found["image"] else "",
        path=f"/t/{troupe_id.lower()}",
    )


def home() -> LinkPreview:
    """The landing page, as people signed out see it: anyone signed in goes on to their
    characters, but a link to / is still the site's."""
    return LinkPreview(
        title=HOME_TITLE,
        description=HOME_DESCRIPTION,
        page_title="Welcome · Horatio",
        path="/",
        feeds=(blog_feed(),),
    )


# --- the blog ------------------------------------------------------------------------


def blog_feed() -> Feed:
    return Feed(BLOG_TITLE, "/blog/feed.xml")


def tag_feed(found: BlogTag) -> Feed:
    return Feed(f"{found.name} · {BLOG_TITLE}", f"/blog/tags/{found.slug}/feed.xml")


def blog() -> LinkPreview:
    return LinkPreview(
        title=BLOG_TITLE,
        description=BLOG_DESCRIPTION,
        page_title="Blog · Horatio",
        path="/blog",
        feeds=(blog_feed(),),
    )


def tag(db: Session, slug: str) -> LinkPreview | None:
    """A tag's page; none for one that has gone (merged into another)."""
    found = db.scalar(select(BlogTag).where(BlogTag.slug == slug))
    if found is None:
        return None
    return LinkPreview(
        title=f"{found.name} · {BLOG_TITLE}",
        description=f"Articles on {found.name} from {BLOG_TITLE}. {BLOG_DESCRIPTION}",
        page_title=f"{found.name} · Blog · Horatio",
        path=f"/blog/tags/{found.slug}",
        feeds=(tag_feed(found), blog_feed()),
    )


def author(db: Session, handle: str) -> LinkPreview | None:
    """An author's page, while anyone may see it (blog_authors.shown)."""
    found = blog_authors.by_handle(db, handle)
    if found is None or not blog_authors.shown(db, found):
        return None
    picture = pictures.author_picture_url(found.id, found.picture_id)
    return LinkPreview(
        title=found.display_name,
        description=shortened(markdown_text(found.bio))
        or f"{found.display_name} writes for {BLOG_TITLE}.",
        page_title=f"{found.display_name} · Blog · Horatio",
        image=f"{picture}/512.webp" if picture else "",
        image_size=(512, 512) if picture else None,
        card="summary" if picture else "",
        kind="profile",
        path=f"/blog/authors/{found.handle}",
        feeds=(blog_feed(),),
    )


def hero_size(found: BlogPost) -> tuple[int, int] | None:
    """The width and height of an article's hero picture's 1200 px copy, which is
    narrower for a picture that was smaller (never made bigger)."""
    root = pictures.upload_dir()
    if root is None or found.picture_id is None:
        return None
    path = pictures.blog_picture_file(root, found.picture_id, "1200.webp")
    if path is None:
        return None
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, UnidentifiedImageError):
        return None


def iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat(timespec="seconds")


def opening(body: str) -> str:
    """The first paragraph of an article's words that isn't a heading or a picture,
    as plain text: its description when it has no summary."""
    for paragraph in re.split(r"\n\s*\n", body.strip()):
        first = paragraph.split("\n")[0]
        if paragraph.strip() and not MD_HEADING.match(first) and not MD_FIGURE.match(first):
            return shortened(markdown_text(paragraph))
    return ""


def article(db: Session, slug: str) -> LinkPreview | None:
    """A published article; none for anything else, so a link to a draft says
    nothing of it."""
    found = db.scalar(published().where(BlogPost.slug == slug))
    if found is None or found.published_at is None:
        return None
    name = authors_of(db, {found.author_id})[found.author_id][0]
    picture = pictures.blog_picture_url(found.id, found.picture_id)
    more = [("article:published_time", iso(found.published_at))]
    if found.revised_at is not None:
        more.append(("article:modified_time", iso(found.revised_at)))
    more.append(("article:author", name.name))
    more += [("article:tag", t.name) for t in tags_of(db, [found.id])[found.id]]
    return LinkPreview(
        title=found.title,
        description=shortened(found.summary) or opening(found.body),
        page_title=f"{found.title} · Blog · Horatio",
        image=f"{picture}/1200.webp" if picture else "",
        image_size=hero_size(found),
        card="summary_large_image",
        kind="article",
        path=f"/blog/{found.slug}",
        more=tuple(more),
        feeds=(blog_feed(),),
    )
