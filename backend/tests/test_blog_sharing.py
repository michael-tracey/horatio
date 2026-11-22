"""Sharing the blog (#1162): link previews of its pages, its Atom feeds, the sitemap and
robots.txt. Only what anyone may read is in any of them."""

import io
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from horatio.app import app, serve_frontend
from horatio.config import get_settings
from horatio.db import get_session
from horatio.models import Suspension, User
from tests.api_helpers import Person, Troupe, sign_up

SITE = "https://horatio.example.org"
INDEX = Path(__file__).parents[2] / "frontend" / "index.html"
ATOM = "{http://www.w3.org/2005/Atom}"
MAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture(autouse=True)
def public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "public_url", SITE + "/")


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


@pytest.fixture
def pages(tmp_path: Path, session: Session) -> TestClient:
    """The app's pages, from the frontend's own index.html, as production serves them."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX.read_text())
    site = FastAPI()
    site.dependency_overrides[get_session] = lambda: session
    serve_frontend(dist, site)
    return TestClient(site)


@pytest.fixture
def top(client_for: Callable[[], TestClient]) -> TestClient:
    """Someone signed out, at the site's top level rather than under /api."""
    client_for()  # for its database session
    return TestClient(app)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def draft(person: Person, troupe: Troupe, **more: Any) -> dict[str, Any]:
    body = {"title": "Running your first Elysium", "summary": "What I wish I'd known."}
    body |= {"body": "Start **small**.", "troupe_id": troupe.id, **more}
    return ok(person.client.post("/blog/articles", json=body), 201)


def publish(troupe: Troupe, article: dict[str, Any]) -> dict[str, Any]:
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    return ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))


def published(troupe: Troupe, **more: Any) -> dict[str, Any]:
    return publish(troupe, draft(troupe.storyteller, troupe, **more))


def tag(troupe: Troupe, article: dict[str, Any], *names: str) -> dict[str, str]:
    tags = {t["name"]: t["id"] for t in ok(troupe.custodian.client.get("/blog/tags"))}
    path = f"/blog/articles/{article['id']}/tags"
    ok(troupe.custodian.client.put(path, json={"tag_ids": [tags[n] for n in names]}))
    return tags


def upload(person: Person, article_id: str) -> None:
    out = io.BytesIO()
    Image.new("RGB", (1600, 900), (120, 20, 20)).save(out, "PNG")
    files = {"file": ("p.png", out.getvalue(), "image/png")}
    ok(person.client.post(f"/blog/articles/{article_id}/picture", files=files))


def author(person: Person, name: str, handle: str) -> None:
    body = {"display_name": name, "handle": handle, "bio": "Runs games.", "links": []}
    ok(person.client.put("/blog/author", json=body))


def meta(page: str, name: str) -> list[str]:
    """The values of every <meta> named `name` in `page`, as written."""
    found: list[str] = []
    for attribute in ("property", "name"):
        start = f'<meta {attribute}="{name}" content="'
        at = page.find(start)
        while at != -1:
            end = page.index('"', at + len(start))
            found.append(page[at + len(start) : end])
            at = page.find(start, end)
    return found


# --- link previews ---------------------------------------------------------------------


def test_the_landing_page_previews_as_horatio_and_names_the_blogs_feed(
    pages: TestClient,
) -> None:
    page = pages.get("/").text

    assert "<title>Welcome · Horatio</title>" in page
    assert meta(page, "og:title") == ["Horatio"]
    assert meta(page, "og:description")[0].startswith("Character sheets, downtimes")
    assert meta(page, "description") == meta(page, "og:description")
    assert meta(page, "og:url") == [f"{SITE}/"]
    assert f'href="{SITE}/blog/feed.xml"' in page
    # The site's own picture.
    assert meta(page, "og:image") == [f"{SITE}/preview.jpg"]
    assert meta(page, "og:image:width") == ["1200"]


def test_the_blog_previews_as_itself_and_names_its_feed(pages: TestClient) -> None:
    page = pages.get("/blog").text

    assert "<title>Blog · Horatio</title>" in page
    assert meta(page, "og:title") == ["Horatio&#x27;s blog"]
    assert meta(page, "og:description")[0].startswith("Essays by the staff of troupes")
    assert meta(page, "og:url") == [f"{SITE}/blog"]
    assert (
        f'<link rel="alternate" type="application/atom+xml" title="Horatio&#x27;s blog" '
        f'href="{SITE}/blog/feed.xml" />'
    ) in page
    assert pages.get("/blog/").text == page
    # The site's own pages don't name it.
    assert "application/atom+xml" not in pages.get("/characters").text


def test_a_published_article_previews_with_its_words_picture_and_dates(
    troupe: Troupe, pages: TestClient, kept: Path
) -> None:
    article = draft(
        troupe.storyteller,
        troupe,
        title='Fights & "fair" <play>',
        summary="Call it <b>out</b> & wait.",
    )
    upload(troupe.storyteller, article["id"])
    tag(troupe, article, "Storytelling")
    shown = publish(troupe, article)
    author(troupe.storyteller, "Sam the Storyteller", "sam_writes")

    response = pages.get(f"/blog/{shown['slug']}")

    assert response.status_code == 200
    page = response.text
    assert "<title>Fights &amp; &quot;fair&quot; &lt;play&gt; · Blog · Horatio</title>" in page
    assert meta(page, "og:title") == ["Fights &amp; &quot;fair&quot; &lt;play&gt;"]
    assert meta(page, "og:description") == ["Call it &lt;b&gt;out&lt;/b&gt; &amp; wait."]
    assert meta(page, "description") == meta(page, "og:description")
    assert "<play>" not in page and "<b>out" not in page
    assert meta(page, "og:type") == ["article"]
    picture = ok(troupe.storyteller.client.get(f"/blog/articles/{article['id']}"))["picture"]
    assert meta(page, "og:image") == [f"{SITE}{picture}/1200.webp"]
    assert (meta(page, "og:image:width"), meta(page, "og:image:height")) == (["1200"], ["600"])
    assert meta(page, "twitter:card") == ["summary_large_image"]
    assert meta(page, "article:published_time") == [shown["published_at"][:19] + "+00:00"]
    assert meta(page, "article:author") == ["Sam the Storyteller"]
    assert meta(page, "article:tag") == ["Storytelling"]
    assert meta(page, "og:url") == [f"{SITE}/blog/{shown['slug']}"]
    assert f'href="{SITE}/blog/feed.xml"' in page
    # The picture it names is there for anyone to fetch.
    visitor = TestClient(app, base_url="http://testserver/api")
    assert visitor.get(f"{picture.removeprefix('/api')}/1200.webp").status_code == 200


def test_with_no_summary_an_article_previews_with_the_start_of_its_words(
    troupe: Troupe, pages: TestClient
) -> None:
    shown = published(troupe, summary="", body="## Begin\n\nStart **small**, then *grow*.")
    page = pages.get(f"/blog/{shown['slug']}").text
    assert meta(page, "og:description") == ["Start small, then grow."]
    # No picture of its own: the site's, as it was.
    assert meta(page, "og:image") == [f"{SITE}/preview.jpg"]
    assert (meta(page, "og:image:width"), meta(page, "og:image:height")) == (["1200"], ["630"])


def test_an_article_not_published_previews_as_the_site_and_says_nothing_of_it(
    troupe: Troupe, pages: TestClient
) -> None:
    default = pages.get("/characters").text
    still = draft(troupe.storyteller, troupe, title="Secret draft", summary="Hush")
    waiting = draft(troupe.storyteller, troupe, title="Waiting one", summary="Hush")
    ok(troupe.storyteller.client.post(f"/blog/articles/{waiting['id']}/submit"))
    down = published(troupe, title="Taken down", summary="Hush")
    ok(
        troupe.custodian.client.post(
            f"/blog/articles/{down['id']}/unpublish", json={"reason": "Out of date"}
        )
    )
    for slug in (still["slug"], waiting["slug"], down["slug"], "nothing-here", "write"):
        response = pages.get(f"/blog/{slug}")
        assert response.status_code == 200
        assert response.text == default, slug
        assert "Hush" not in response.text

    # A published article's changes waiting for the custodian aren't in it either.
    live = published(troupe, title="Live one", summary="Published words")
    changes = {"title": "Changed title", "summary": "Changed words", "body": "New"}
    ok(troupe.storyteller.client.put(f"/blog/articles/{live['id']}", json=changes))
    page = pages.get(f"/blog/{live['slug']}").text
    assert meta(page, "og:title") == ["Live one"]
    assert "Changed" not in page


def test_a_tags_and_an_authors_page_preview_while_they_are_shown(
    client_for: Callable[[], TestClient], troupe: Troupe, pages: TestClient, session: Session
) -> None:
    article = published(troupe)
    tags = tag(troupe, article, "Storytelling")
    author(troupe.storyteller, "Sam <the> Storyteller", "sam_writes")

    page = pages.get("/blog/tags/storytelling").text
    assert "<title>Storytelling · Blog · Horatio</title>" in page
    assert meta(page, "og:title") == ["Storytelling · Horatio&#x27;s blog"]
    assert f'href="{SITE}/blog/tags/storytelling/feed.xml"' in page
    assert f'href="{SITE}/blog/feed.xml"' in page

    page = pages.get("/blog/authors/sam_writes").text
    assert "<title>Sam &lt;the&gt; Storyteller · Blog · Horatio</title>" in page
    assert meta(page, "og:description") == ["Runs games."]
    assert meta(page, "og:type") == ["profile"]

    default = pages.get("/characters").text
    # A tag merged into another has moved for good to the other's page, whose preview
    # is there (#1184), keeping the page asked for.
    path = f"/blog/tags/{tags['Storytelling']}/merge"
    ok(troupe.custodian.client.post(path, json={"into_id": tags["Downtimes"]}))
    for old in ("/blog/tags/storytelling", "/blog/tags/storytelling/"):
        moved = pages.get(old, follow_redirects=False)
        assert moved.status_code == 301
        assert moved.headers["location"] == "/blog/tags/downtimes"
    paged = pages.get("/blog/tags/storytelling?page=2", follow_redirects=False)
    assert paged.headers["location"] == "/blog/tags/downtimes?page=2"
    page = pages.get("/blog/tags/storytelling").text
    assert meta(page, "og:title") == ["Downtimes · Horatio&#x27;s blog"]
    assert meta(page, "og:url") == [f"{SITE}/blog/tags/downtimes"]
    assert pages.get("/blog/tags/no-such-tag").text == default
    # An author merged into another account isn't shown.
    other = sign_up(client_for, "elsewhere")
    session.get_one(User, uuid.UUID(troupe.storyteller.id)).merged_into_id = uuid.UUID(other.id)
    session.flush()
    assert pages.get("/blog/authors/sam_writes").text == default
    assert pages.get("/blog/authors/nobody").text == default


# --- the feeds -------------------------------------------------------------------------


def entries(response: Any) -> list[ET.Element]:
    return ET.fromstring(response.content).findall(f"{ATOM}entry")


def test_the_feed_is_atom_of_published_articles_only_with_their_words_escaped(
    troupe: Troupe, top: TestClient, kept: Path
) -> None:
    draft(troupe.storyteller, troupe, title="Secret draft")
    first = published(troupe, title="First", summary="One & two")
    words = "Use <script>alert(1)</script> & **bold**.\n\nSee https://example.org/a?b=1&c=2"
    article = draft(troupe.storyteller, troupe, title="Second <one>", summary="", body=words)
    upload(troupe.storyteller, article["id"])
    second = publish(troupe, article)
    tag(troupe, second, "Storytelling")
    author(troupe.storyteller, "Sam", "sam_writes")

    response = top.get("/blog/feed.xml")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/atom+xml"
    assert response.headers["cache-control"] == "public, max-age=900"
    feed = ET.fromstring(response.content)
    assert feed.tag == f"{ATOM}feed"
    assert feed.findtext(f"{ATOM}title") == "Horatio's blog"
    assert feed.findtext(f"{ATOM}id") == f"{SITE}/blog"
    self_link = feed.find(f"{ATOM}link[@rel='self']")
    assert self_link is not None and self_link.get("href") == f"{SITE}/blog/feed.xml"
    found = entries(response)
    assert [e.findtext(f"{ATOM}title") for e in found] == ["Second <one>", "First"]
    newest, oldest = found
    assert newest.findtext(f"{ATOM}id") == f"{SITE}/blog/{second['slug']}"
    assert newest.findtext(f"{ATOM}published") == second["published_at"][:19] + "Z"
    assert newest.findtext(f"{ATOM}author/{ATOM}name") == "Sam"
    assert newest.findtext(f"{ATOM}author/{ATOM}uri") == f"{SITE}/blog/authors/sam_writes"
    category = newest.find(f"{ATOM}category")
    assert category is not None and category.get("term") == "storytelling"
    assert newest.find(f"{ATOM}summary") is None
    assert oldest.findtext(f"{ATOM}summary") == "One & two"
    content = newest.find(f"{ATOM}content")
    assert content is not None and content.get("type") == "html"
    html = content.text or ""
    # The words are HTML, built from the Markdown: what was written as HTML is text.
    assert "<strong>bold</strong>" in html
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert 'href="https://example.org/a?b=1&amp;c=2"' in html
    picture = ok(troupe.storyteller.client.get(f"/blog/articles/{second['id']}"))["picture"]
    assert f'<img src="{SITE}{picture}/1200.webp" alt="" />' in html
    # In the document itself, all of it is escaped once more.
    assert b"<script>" not in response.content and b"&lt;script&gt;" not in response.content
    assert "Secret" not in response.text and first["slug"] in response.text

    # A reader that has it already is told so.
    again = top.get("/blog/feed.xml", headers={"If-None-Match": response.headers["etag"]})
    assert again.status_code == 304
    assert top.head("/blog/feed.xml").status_code == 200


def test_the_feed_shows_the_pictures_in_an_articles_words(
    troupe: Troupe, top: TestClient, pages: TestClient, kept: Path
) -> None:
    article = draft(troupe.storyteller, troupe, title="Lighting a scene", summary="")
    out = io.BytesIO()
    Image.new("RGB", (1600, 900), (20, 20, 120)).save(out, "PNG")
    files = {"file": ("p.png", out.getvalue(), "image/png")}
    path = f"/blog/articles/{article['id']}/body-pictures"
    picture = ok(troupe.storyteller.client.post(path, files=files), 201)
    words = f'![Candles & <wax>](blog-picture:{picture["id"]} "Lit at dusk")\n\nKeep the room dim.'
    changes = {"title": "Lighting a scene", "summary": "", "body": words, "troupe_id": troupe.id}
    ok(troupe.storyteller.client.put(f"/blog/articles/{article['id']}", json=changes))
    shown = publish(troupe, article)

    [entry] = entries(top.get("/blog/feed.xml"))

    html = entry.findtext(f"{ATOM}content") or ""
    assert f'src="{SITE}{picture["url"]}/600.webp"' in html
    assert 'alt="Candles &amp; &lt;wax&gt;"' in html and "Lit at dusk" in html
    assert "blog-picture:" not in html
    # Its address is anyone's to fetch, now the article is published.
    visitor = TestClient(app, base_url="http://testserver/api")
    assert visitor.get(f"{picture['url'].removeprefix('/api')}/600.webp").status_code == 200
    # Its preview's description is the words, not the picture.
    page = pages.get(f"/blog/{shown['slug']}").text
    assert meta(page, "og:description") == ["Keep the room dim."]


def test_the_feed_holds_the_latest_twenty(troupe: Troupe, top: TestClient) -> None:
    for n in range(22):
        published(troupe, title=f"Article {n}")
    titles = [e.findtext(f"{ATOM}title") for e in entries(top.get("/blog/feed.xml"))]
    assert titles == [f"Article {n}" for n in range(21, 1, -1)]


def test_a_tag_has_a_feed_of_its_own(troupe: Troupe, top: TestClient) -> None:
    tagged = published(troupe, title="Tagged")
    tags = tag(troupe, tagged, "Storytelling")
    published(troupe, title="Not tagged")
    waiting = draft(troupe.storyteller, troupe, title="Tagged draft")
    tag(troupe, waiting, "Storytelling")

    response = top.get("/blog/tags/storytelling/feed.xml")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/atom+xml"
    feed = ET.fromstring(response.content)
    assert feed.findtext(f"{ATOM}title") == "Storytelling · Horatio's blog"
    assert feed.findtext(f"{ATOM}id") == f"{SITE}/blog/tags/storytelling"
    assert [e.findtext(f"{ATOM}title") for e in entries(response)] == ["Tagged"]
    assert top.get("/blog/tags/no-such-tag/feed.xml").status_code == 404
    # Merged into another, its feed has moved for good to the other's (#1184).
    path = f"/blog/tags/{tags['Storytelling']}/merge"
    ok(troupe.custodian.client.post(path, json={"into_id": tags["Downtimes"]}))
    moved = top.get("/blog/tags/storytelling/feed.xml", follow_redirects=False)
    assert moved.status_code == 301
    assert moved.headers["location"] == "/blog/tags/downtimes/feed.xml"
    assert top.head("/blog/tags/storytelling/feed.xml", follow_redirects=False).status_code == 301
    downtimes = entries(top.get("/blog/tags/storytelling/feed.xml"))
    assert [e.findtext(f"{ATOM}title") for e in downtimes] == ["Tagged"]
    # Merged on again, the old feed leads to the last tag.
    path = f"/blog/tags/{tags['Downtimes']}/merge"
    ok(troupe.custodian.client.post(path, json={"into_id": tags["Community"]}))
    for old in ("storytelling", "downtimes"):
        moved = top.get(f"/blog/tags/{old}/feed.xml", follow_redirects=False)
        assert moved.headers["location"] == "/blog/tags/community/feed.xml"


def test_an_empty_feed_is_still_a_feed(top: TestClient) -> None:
    response = top.get("/blog/feed.xml")
    assert response.status_code == 200
    feed = ET.fromstring(response.content)
    assert feed.findtext(f"{ATOM}updated")
    assert entries(response) == []


# --- the sitemap and robots.txt ---------------------------------------------------------


def addresses(top: TestClient) -> dict[str, str | None]:
    response = top.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    root = ET.fromstring(response.content)
    assert root.tag == f"{MAP}urlset"
    return {
        u.findtext(f"{MAP}loc") or "": u.findtext(f"{MAP}lastmod")
        for u in root.findall(f"{MAP}url")
    }


def test_the_sitemap_lists_the_public_pages_and_nothing_private(
    client_for: Callable[[], TestClient], troupe: Troupe, top: TestClient, session: Session
) -> None:
    article = published(troupe, title="Out now")
    tag(troupe, article, "Storytelling")
    still = draft(troupe.storyteller, troupe, title="Still a draft")
    tag(troupe, still, "Downtimes")
    down = published(troupe, title="Taken down")
    tag(troupe, down, "Safety and consent")
    ok(
        troupe.custodian.client.post(
            f"/blog/articles/{down['id']}/unpublish", json={"reason": "Out of date"}
        )
    )
    author(troupe.storyteller, "Sam", "sam_writes")
    # Three more who wrote for the blog: one merged into another account, one
    # suspended, and one who still writes.
    merged, barred, writer = (sign_up(client_for, name) for name in ("twice", "barred", "writer"))
    for person in (merged, barred, writer):
        ok(
            troupe.lead.client.put(
                f"/troupes/{troupe.id}/staff", json={"handle": person.handle, "role": "narrator"}
            )
        )
        author(person, person.handle, f"{person.handle}_writes")
    session.get_one(User, uuid.UUID(merged.id)).merged_into_id = uuid.UUID(troupe.player.id)
    session.add(
        Suspension(
            user_id=uuid.UUID(barred.id),
            reason="Rude.",
            suspended_by_id=uuid.UUID(troupe.custodian.id),
        )
    )
    session.flush()
    # A troupe whose profile is public, one private, and one public but archived.
    ok(troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": True}))
    hidden = ok(
        troupe.custodian.client.post(
            "/troupes", json={"name": "Hidden court", "lead_handle": troupe.lead.handle}
        ),
        201,
    )
    gone = ok(
        troupe.custodian.client.post(
            "/troupes", json={"name": "Old court", "lead_handle": troupe.lead.handle}
        ),
        201,
    )
    ok(troupe.lead.client.put(f"/troupes/{gone['id']}/profile/public", json={"public": True}))
    ok(troupe.lead.client.post(f"/troupes/{gone['id']}/archive", json={"reason": "Done"}))

    found = addresses(top)

    published_at = article["published_at"][:19] + "Z"
    assert found == {
        f"{SITE}/": None,
        f"{SITE}/blog": published_at,
        f"{SITE}/blog/{article['slug']}": published_at,
        f"{SITE}/blog/tags/storytelling": published_at,
        f"{SITE}/blog/authors/sam_writes": None,
        f"{SITE}/blog/authors/{writer.handle}_writes": None,
        f"{SITE}/t/{troupe.id}": None,
    }
    assert hidden["id"] not in str(found) and gone["id"] not in str(found)


def test_an_empty_sitemap_has_the_landing_page_and_the_blog(top: TestClient) -> None:
    assert addresses(top) == {f"{SITE}/": None, f"{SITE}/blog": None}


def test_robots_keeps_search_engines_to_the_public_pages(top: TestClient) -> None:
    response = top.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    lines = response.text.splitlines()
    assert lines[0] == "User-agent: *"
    for path in ("/blog", "/t/", "/help", "/about"):
        assert f"Allow: {path}" in lines
    for path in ("/characters", "/troupes", "/account", "/custodian", "/blog/write/"):
        assert f"Disallow: {path}" in lines
    assert f"Sitemap: {SITE}/sitemap.xml" in lines
    # Nothing public is kept from them: a disallowed path is never the start of one.
    disallowed = [line.removeprefix("Disallow: ") for line in lines if "Disallow" in line]
    for public in ("/blog", "/blog/write-2", "/t/abc", "/help/players", "/about", "/sign-in"):
        assert not any(public.startswith(d) or public == d.removesuffix("$") for d in disallowed), (
            public
        )
