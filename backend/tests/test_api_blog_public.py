"""The game developer blog's reading pages (#1158): signed out, only published
articles, and only what the blog shows of them; paging, featured and tags; and hero
pictures public once their article is."""

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from horatio.api import blog_public
from horatio.config import get_settings
from tests.api_helpers import Person, Troupe


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def anyone(client_for: Callable[[], TestClient]) -> TestClient:
    """Someone signed out."""
    return client_for()


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def draft(person: Person, troupe_id: str | None = None, **more: Any) -> dict[str, Any]:
    body = {"title": "Running your first Elysium", "summary": "What I wish I'd known."}
    body |= {"body": "Start **small**.", "troupe_id": troupe_id, **more}
    return ok(person.client.post("/blog/articles", json=body), 201)


def publish(troupe: Troupe, article: dict[str, Any]) -> dict[str, Any]:
    """The storyteller's article, sent and published."""
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    return ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))


def published(troupe: Troupe, **more: Any) -> dict[str, Any]:
    return publish(troupe, draft(troupe.storyteller, troupe.id, **more))


def tag(troupe: Troupe, article: dict[str, Any], *names: str) -> None:
    tags = {t["name"]: t["id"] for t in ok(troupe.custodian.client.get("/blog/tags"))}
    path = f"/blog/articles/{article['id']}/tags"
    ok(troupe.custodian.client.put(path, json={"tag_ids": [tags[n] for n in names]}))


def titles(page: dict[str, Any], key: str = "articles") -> list[str]:
    return [a["title"] for a in page[key]]


def test_signed_out_the_blog_shows_only_published_articles(
    troupe: Troupe, anyone: TestClient
) -> None:
    published(troupe, title="Out now")
    draft(troupe.storyteller, troupe.id, title="Still a draft")
    waiting = draft(troupe.storyteller, troupe.id, title="Waiting")
    ok(troupe.storyteller.client.post(f"/blog/articles/{waiting['id']}/submit"))
    down = published(troupe, title="Taken down")
    path = f"/blog/articles/{down['id']}/unpublish"
    ok(troupe.custodian.client.post(path, json={"reason": "Out of date"}))

    page = ok(anyone.get("/blog/public/articles"))

    assert titles(page) == ["Out now"]
    assert (page["page"], page["pages"], page["total"]) == (1, 1, 1)
    for slug in ("still-a-draft", "waiting", "taken-down", "nothing-at-all"):
        refused = anyone.get(f"/blog/public/articles/{slug}")
        assert refused.status_code == 404
        assert refused.json()["detail"] == "No such article."
    # Signed in, it's the same, even for its author and the custodian.
    for person in (troupe.storyteller, troupe.custodian):
        assert titles(ok(person.client.get("/blog/public/articles"))) == ["Out now"]
        assert person.client.get("/blog/public/articles/still-a-draft").status_code == 404


def test_an_article_shows_its_published_words_and_nothing_private(
    troupe: Troupe, anyone: TestClient
) -> None:
    article = published(troupe)
    tag(troupe, article, "Storytelling", "Safety and consent")
    # Its author changes it, and the custodian returns the changes with a note.
    body = {"title": "A new title", "summary": "New", "body": "New words", "troupe_id": troupe.id}
    ok(troupe.storyteller.client.put(f"/blog/articles/{article['id']}", json=body))
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    path = f"/blog/articles/{article['id']}/return"
    ok(troupe.custodian.client.post(path, json={"note": "Not yet, a private word"}))

    shown = ok(anyone.get("/blog/public/articles/running-your-first-elysium"))

    assert shown == {
        "slug": "running-your-first-elysium",
        "title": "Running your first Elysium",
        "summary": "What I wish I'd known.",
        "body": "Start **small**.",
        "picture": None,
        "author": {"name": "storyteller", "handle": None},
        # The troupe isn't public, so it is its name only.
        "troupe": {"name": "Lords of the Night", "id": None},
        "tags": [
            {"name": "Storytelling", "slug": "storytelling"},
            {"name": "Safety and consent", "slug": "safety-and-consent"},
        ],
        "featured": False,
        "published_at": shown["published_at"],
        "revised_at": None,
        "edit": None,
    }
    assert "Not yet" not in str(shown) and "New words" not in str(shown)
    # Its author has a way to change it from there.
    mine = ok(troupe.storyteller.client.get("/blog/public/articles/running-your-first-elysium"))
    assert mine["edit"] == f"/blog/write/{article['id']}"


def test_a_public_troupe_is_linked_and_an_archived_one_isnt(
    troupe: Troupe, anyone: TestClient
) -> None:
    published(troupe)
    ok(troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": True}))
    path = "/blog/public/articles/running-your-first-elysium"

    assert ok(anyone.get(path))["troupe"] == {"name": "Lords of the Night", "id": troupe.id}

    ok(troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"}))
    assert ok(anyone.get(path))["troupe"] == {"name": "Lords of the Night", "id": None}


def test_the_blog_is_newest_first_a_page_at_a_time_with_the_featured_on_top(
    troupe: Troupe, anyone: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(blog_public, "PAGE_SIZE", 2)
    for n in range(1, 6):
        published(troupe, title=f"Article {n}")
    third = ok(troupe.custodian.client.get("/blog/queue"))["published"][2]
    ok(
        troupe.custodian.client.put(
            f"/blog/articles/{third['id']}/featured", json={"featured": True}
        )
    )

    first = ok(anyone.get("/blog/public/articles"))
    last = ok(anyone.get("/blog/public/articles", params={"page": 3}))

    assert titles(first) == ["Article 5", "Article 4"]
    assert (first["page"], first["pages"], first["total"]) == (1, 3, 5)
    assert titles(first, "featured") == ["Article 3"]
    assert first["featured"][0]["featured"] is True
    assert titles(last) == ["Article 1"]
    assert titles(ok(anyone.get("/blog/public/articles", params={"page": 9}))) == []
    assert anyone.get("/blog/public/articles", params={"page": 0}).status_code == 422


def test_a_tags_articles_and_how_many_each_tag_has(troupe: Troupe, anyone: TestClient) -> None:
    one = published(troupe, title="On safety")
    two = published(troupe, title="On safety and scenes")
    published(troupe, title="Untagged")
    hidden = draft(troupe.storyteller, troupe.id, title="A tagged draft")
    tag(troupe, one, "Safety and consent")
    tag(troupe, two, "Safety and consent", "Storytelling")
    tag(troupe, hidden, "Safety and consent")

    tagged = ok(anyone.get("/blog/public/tags/safety-and-consent"))
    filtered = ok(anyone.get("/blog/public/articles", params={"tag": "storytelling"}))
    tags = {t["slug"]: t["articles"] for t in ok(anyone.get("/blog/public/tags"))}

    assert tagged["tag"] == {"name": "Safety and consent", "slug": "safety-and-consent"}
    assert titles(tagged) == ["On safety and scenes", "On safety"]
    assert tagged["total"] == 2
    assert titles(filtered) == ["On safety and scenes"]
    # Every tag, in the custodian's order, counting only what is published.
    assert (tags["safety-and-consent"], tags["storytelling"], tags["community"]) == (2, 1, 0)
    assert anyone.get("/blog/public/tags/no-such-tag").status_code == 404
    assert anyone.get("/blog/public/articles", params={"tag": "nope"}).status_code == 404


def test_the_blogs_own_addresses_arent_slugs(troupe: Troupe) -> None:
    article = draft(troupe.storyteller, troupe.id, title="Write")

    assert article["slug"] == "write-2"
    path = f"/blog/articles/{article['id']}/slug"
    refused = troupe.storyteller.client.put(path, json={"slug": "tags"})
    assert refused.status_code == 409


# --- hero pictures ------------------------------------------------------------------------


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def upload(person: Person, article_id: str, colour: tuple[int, int, int]) -> dict[str, Any]:
    out = io.BytesIO()
    Image.new("RGB", (1600, 900), colour).save(out, "PNG")
    files = {"file": ("p.png", out.getvalue(), "image/png")}
    return ok(person.client.post(f"/blog/articles/{article_id}/picture", files=files))


def fetch(client: TestClient, picture: str, name: str = "600.webp") -> Any:
    return client.get(f"{picture}/{name}".removeprefix("/api"))


def test_a_hero_picture_is_public_once_its_article_is(
    troupe: Troupe, anyone: TestClient, kept: Path
) -> None:
    article = draft(troupe.storyteller, troupe.id)
    picture = upload(troupe.storyteller, article["id"], (120, 20, 20))["picture"]

    # Not while it is a draft.
    assert fetch(anyone, picture).status_code == 404
    assert fetch(troupe.lead.client, picture).status_code == 404
    mine = fetch(troupe.storyteller.client, picture)
    assert mine.headers["cache-control"] == "private, max-age=31536000, immutable"

    publish(troupe, article)
    shown = fetch(anyone, picture)
    assert shown.status_code == 200
    assert shown.headers["cache-control"] == "public, max-age=3600"
    with Image.open(io.BytesIO(shown.content)) as image:
        assert image.size == (600, 338)
    assert ok(anyone.get("/blog/public/articles"))["articles"][0]["picture"] == picture
    assert fetch(anyone, picture, "full.webp").status_code == 404

    # A new picture in its changes stays private until they are published.
    changed = upload(troupe.storyteller, article["id"], (20, 20, 120))["revision"]["picture"]
    assert fetch(anyone, changed).status_code == 404
    assert fetch(troupe.storyteller.client, changed).status_code == 200
    assert fetch(anyone, picture).status_code == 200

    # Unpublished, it is private again.
    path = f"/blog/articles/{article['id']}/unpublish"
    ok(troupe.custodian.client.post(path, json={"reason": "Out of date"}))
    assert fetch(anyone, changed).status_code == 404
    assert fetch(troupe.storyteller.client, changed).status_code == 200
