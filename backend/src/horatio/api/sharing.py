"""What feed readers and search engines read (#1162): the blog's Atom feeds, the
sitemap and robots.txt. Link previews of the public pages are horatio.link_previews.

These are at the site's top level, beside the app's own pages rather than under /api,
where readers and search engines look for them: /blog/feed.xml (and a tag's,
/blog/tags/<tag>/feed.xml), /sitemap.xml and /robots.txt. Each address in them is
absolute, on the site's address (HORATIO_PUBLIC_URL). Only what anyone may read goes
in: published articles, the tags they have, authors whose pages are shown, and
troupes whose profile is public and running.

The feeds are Atom (RFC 4287) rather than RSS 2.0: every feed reader reads it, and it
says exactly what each part is. An entry's id must never change, and an article's
slug never does once published (horatio.blog), so its address is its id; the body
goes as HTML, marked as such, where RSS leaves readers to guess.
"""

import hashlib
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import quote
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from horatio import pictures, suspensions
from horatio.api import blog_authors
from horatio.api.blog_public import authors_of, newest, published, tag_by_slug, tagged
from horatio.auth.deps import DbSession
from horatio.blog import tags_of
from horatio.config import get_settings
from horatio.email_design import markdown_html
from horatio.link_previews import BLOG_DESCRIPTION, BLOG_TITLE
from horatio.models import BlogAuthor, BlogPost, BlogPostTag, BlogTag, Troupe, User

router = APIRouter(include_in_schema=False)

# Articles in a feed: the latest published.
FEED_SIZE = 20

ATOM = "http://www.w3.org/2005/Atom"
SITEMAP = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Feed readers ask every so often; a quarter of an hour in caches is soon enough for a
# new article. The sitemap and robots.txt change less.
FEED_CACHE = "public, max-age=900"
SITE_CACHE = "public, max-age=3600"

# Characters XML 1.0 can't hold at all, which an article's words might.
NOT_XML = re.compile("[^\t\n\r -퟿-�\U00010000-\U0010ffff]")

# The app's pages that are only for people signed in, or for one person (an email's
# link), which search engines have no business in. The rest are the public ones:
# the blog, troupes' public profiles (/t/), the manual (/help), About, and signing in.
# The API isn't here: the public pages are drawn from it, and link previews' pictures
# are in it; anything else in it is only for people signed in.
PRIVATE = (
    "/characters",
    "/troupes",
    "/players/",
    "/play/",
    "/print/",
    "/rules",
    "/account",
    "/custodian",
    "/check-in",
    "/cycles/",
    "/two-step",
    "/charts",
    "/people",
    "/claim/",
    "/reset-password/",
    "/confirm-email/",
    "/unsubscribe/",
    "/sign-in/second-step",
    # Writing for the blog: the list of one's own, and each article being written. An
    # article whose slug starts "write", such as write-2, is the blog's.
    "/blog/write$",
    "/blog/write/",
)
PUBLIC = ("/blog", "/t/", "/help", "/about")


def site() -> str:
    return get_settings().public_url.rstrip("/")


def clean(text: str) -> str:
    return NOT_XML.sub("", text)


def stamp(at: datetime) -> str:
    """A time as Atom and sitemaps write it: RFC 3339, in UTC."""
    return at.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def xml_response(root: ET.Element, media_type: str, cache: str, request: Request) -> Response:
    """`root` as an XML document, cached for `cache`; 304 for a reader that has it."""
    body = b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8")
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    headers = {"Cache-Control": cache, "ETag": etag}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(body, media_type=media_type, headers=headers)


def child(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, tag, attrs)
    if text is not None:
        element.text = clean(text)
    return element


# --- the feeds -------------------------------------------------------------------------


def updated(article: BlogPost) -> datetime:
    """When an article last changed for readers: its changes published, or itself."""
    assert article.published_at is not None
    return article.revised_at or article.published_at


def content(article: BlogPost, base: str) -> str:
    """An article's words as HTML for a feed reader, its hero picture first, and the
    pictures in its words (#1163) at their 600 px copies' addresses."""
    picture = pictures.blog_picture_url(article.id, article.picture_id)
    hero = f'<p><img src="{base}{picture}/1200.webp" alt="" /></p>\n' if picture else ""
    return hero + markdown_html(article.body, pictures=True)


def feed(
    db: Session,
    request: Request,
    title: str,
    page: str,
    path: str,
    articles: Sequence[BlogPost],
) -> Response:
    """An Atom feed of `articles`, the blog's page `page` and this feed at `path`."""
    base = site()
    root = ET.Element("feed", xmlns=ATOM)
    child(root, "title", title)
    child(root, "subtitle", BLOG_DESCRIPTION)
    child(root, "id", base + page)
    child(root, "link", rel="alternate", type="text/html", href=base + page)
    child(root, "link", rel="self", type="application/atom+xml", href=base + path)
    newest_change = max((updated(x) for x in articles), default=datetime.now(UTC))
    child(root, "updated", stamp(newest_change))
    child(root, "icon", f"{base}/favicon-32.png")
    child(root, "logo", f"{base}/logo.png")
    child(root, "generator", "Horatio")

    authors = authors_of(db, {x.author_id for x in articles})
    tags = tags_of(db, [x.id for x in articles])
    for article in articles:
        assert article.published_at is not None
        address = f"{base}/blog/{quote(article.slug)}"
        entry = child(root, "entry")
        child(entry, "title", article.title)
        child(entry, "id", address)
        child(entry, "link", rel="alternate", type="text/html", href=address)
        child(entry, "published", stamp(article.published_at))
        child(entry, "updated", stamp(updated(article)))
        name = authors[article.author_id][0]
        who = child(entry, "author")
        child(who, "name", name.name)
        if name.handle:
            child(who, "uri", f"{base}/blog/authors/{quote(name.handle)}")
        for t in tags[article.id]:
            child(entry, "category", term=t.slug, label=clean(t.name), scheme=f"{base}/blog/tags/")
        if article.summary.strip():
            child(entry, "summary", article.summary.strip(), type="text")
        child(entry, "content", content(article, base), type="html")
    return xml_response(root, "application/atom+xml", FEED_CACHE, request)


def latest(db: Session, query: Select[BlogPost]) -> list[BlogPost]:
    return list(db.scalars(newest(query).limit(FEED_SIZE)))


@router.api_route("/blog/feed.xml", methods=["GET", "HEAD"])
def blog_feed(request: Request, db: DbSession) -> Response:
    """The blog's latest published articles, newest first."""
    return feed(db, request, BLOG_TITLE, "/blog", "/blog/feed.xml", latest(db, published()))


@router.api_route("/blog/tags/{slug}/feed.xml", methods=["GET", "HEAD"])
def tag_feed(slug: str, request: Request, db: DbSession) -> Response:
    """A tag's latest published articles, newest first. A retired tag's stays; one
    merged into another has gone, as its page has (#1161)."""
    found = tag_by_slug(db, slug)
    page = f"/blog/tags/{quote(found.slug)}"
    title = f"{found.name} · {BLOG_TITLE}"
    articles = latest(db, tagged(published(), found))
    return feed(db, request, title, page, f"{page}/feed.xml", articles)


# --- the sitemap and robots.txt ---------------------------------------------------------


def shown_authors(db: Session) -> list[BlogAuthor]:
    """The authors whose pages anyone may see (blog_authors.shown): no one merged into
    another account or suspended now (#1182), who are passed over first."""
    found = db.scalars(
        select(BlogAuthor)
        .join(User, User.id == BlogAuthor.user_id)
        .where(User.merged_into_id.is_(None), ~suspensions.suspended_user())
        .order_by(BlogAuthor.handle)
    )
    return [author for author in found if blog_authors.shown(db, author)]


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"])
def sitemap(request: Request, db: DbSession) -> Response:
    """Every public page worth a search engine's visit: the landing page (#1164), the
    blog, its published articles, the tags they have, the authors whose pages are
    shown, and the troupes whose profiles are public and running."""
    base = site()
    root = ET.Element("urlset", xmlns=SITEMAP)

    def url(path: str, lastmod: datetime | None = None) -> None:
        entry = child(root, "url")
        child(entry, "loc", base + path)
        if lastmod is not None:
            child(entry, "lastmod", stamp(lastmod))

    articles = list(db.scalars(newest(published())))
    url("/")
    url("/blog", max((updated(a) for a in articles), default=None))
    for article in articles:
        url(f"/blog/{quote(article.slug)}", updated(article))
    latest_in: dict[str, datetime] = {}
    by_id = {a.id: a for a in articles}
    for tag_slug, post_id in db.execute(
        select(BlogTag.slug, BlogPostTag.post_id)
        .join(BlogPostTag, BlogPostTag.tag_id == BlogTag.id)
        .where(BlogPostTag.post_id.in_(by_id))
    ):
        changed = updated(by_id[post_id])
        latest_in[tag_slug] = max(latest_in.get(tag_slug, changed), changed)
    for tag_slug in sorted(latest_in):
        url(f"/blog/tags/{quote(tag_slug)}", latest_in[tag_slug])
    for author in shown_authors(db):
        url(f"/blog/authors/{quote(author.handle)}")
    for troupe_id in db.scalars(
        select(Troupe.id)
        .where(Troupe.public, Troupe.archived_at.is_(None))
        .order_by(Troupe.name, Troupe.id)
    ):
        url(f"/t/{troupe_id}")
    return xml_response(root, "application/xml", SITE_CACHE, request)


@router.api_route("/robots.txt", methods=["GET", "HEAD"])
def robots() -> Response:
    """Where search engines may go: the public pages, and not the app's private ones."""
    lines = ["User-agent: *"]
    lines += [f"Allow: {path}" for path in PUBLIC]
    lines += [f"Disallow: {path}" for path in PRIVATE]
    lines += ["", f"Sitemap: {site()}/sitemap.xml", ""]
    return Response(
        "\n".join(lines), media_type="text/plain", headers={"Cache-Control": SITE_CACHE}
    )
