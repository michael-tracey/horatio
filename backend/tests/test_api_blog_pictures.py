"""Pictures in a blog article's words (issue #1163): uploaded for the article, at the
sizes the blog shows, up to a limit; named in the Markdown only by the blog's own
scheme; shown to anyone only once the published words name them; and deleted once
no version of the article does."""

import io
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from horatio import blog, email_design
from horatio.config import get_settings
from horatio.models import BlogPostPicture
from tests.api_helpers import Person, Troupe


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


@pytest.fixture
def anyone(client_for: Callable[[], TestClient]) -> TestClient:
    """Someone signed out."""
    return client_for()


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def draft(person: Person, troupe_id: str, body: str = "Start small.") -> dict[str, Any]:
    return ok(
        person.client.post(
            "/blog/articles",
            json={"title": "Lighting a scene", "summary": "", "body": body, "troupe_id": troupe_id},
        ),
        201,
    )


def save(person: Person, article: dict[str, Any], body: str) -> Any:
    return person.client.put(
        f"/blog/articles/{article['id']}",
        json={
            "title": article["title"],
            "summary": article["summary"],
            "body": body,
            "troupe_id": article["troupe"]["id"] if article["troupe"] else None,
        },
    )


def png(size: tuple[int, int] = (1600, 900)) -> bytes:
    out = io.BytesIO()
    image = Image.new("RGB", size, (120, 20, 20))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make: metadata a phone adds, to be stripped
    image.save(out, "PNG", exif=exif)
    return out.getvalue()


def upload(person: Person, article_id: str, size: tuple[int, int] = (1600, 900)) -> Any:
    return person.client.post(
        f"/blog/articles/{article_id}/body-pictures",
        files={"file": ("p.png", png(size), "image/png")},
    )


def figure(picture_id: str, alt: str = "Candles on a long table", caption: str = "") -> str:
    said = f' "{caption}"' if caption else ""
    return f"![{alt}](blog-picture:{picture_id}{said})"


def fetch(client: TestClient, picture: dict[str, Any], name: str = "1200.webp") -> Any:
    return client.get(f"{picture['url']}/{name}".removeprefix("/api"))


def publish(troupe: Troupe, article: dict[str, Any]) -> dict[str, Any]:
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    return ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))


def test_a_picture_is_kept_with_its_article_at_the_blogs_sizes(
    troupe: Troupe, kept: Path, session: Session
) -> None:
    article = draft(troupe.storyteller, troupe.id)

    picture = ok(upload(troupe.storyteller, article["id"]), 201)

    assert picture["url"] == f"/api/blog/body-pictures/{picture['id']}"
    directory = kept / "blog-pictures" / article["id"] / picture["id"]
    assert sorted(p.name for p in directory.iterdir()) == ["1200.webp", "600.webp"]
    stored = session.get(BlogPostPicture, uuid.UUID(picture["id"]))
    assert stored is not None and str(stored.post_id) == article["id"]
    for name, size in (("1200.webp", (1200, 675)), ("600.webp", (600, 338))):
        shown = fetch(troupe.storyteller.client, picture, name)
        assert shown.status_code == 200
        assert shown.headers["content-type"] == "image/webp"
        with Image.open(io.BytesIO(shown.content)) as image:
            # Kept whole, made smaller, as WebP, and nothing of the upload's own with it.
            assert image.format == "WEBP"
            assert image.size == size
            assert not image.getexif()
    # A small one is never made bigger.
    small = ok(upload(troupe.storyteller, article["id"], (400, 300)), 201)
    with Image.open(io.BytesIO(fetch(troupe.storyteller.client, small).content)) as image:
        assert image.size == (400, 300)
    assert fetch(troupe.storyteller.client, picture, "full.webp").status_code == 404


def test_only_its_author_uploads_while_they_may_change_it(troupe: Troupe, kept: Path) -> None:
    article = draft(troupe.storyteller, troupe.id)

    assert upload(troupe.custodian, article["id"]).status_code == 403
    assert upload(troupe.lead, article["id"]).status_code == 404
    not_a_picture = troupe.storyteller.client.post(
        f"/blog/articles/{article['id']}/body-pictures",
        files={"file": ("p.png", b"not a picture", "image/png")},
    )
    assert not_a_picture.status_code == 422
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    assert upload(troupe.storyteller, article["id"]).status_code == 409
    assert not (kept / "blog-pictures").exists() or not any(
        (kept / "blog-pictures").rglob("*.webp")
    )


def test_an_article_keeps_up_to_twenty_pictures(troupe: Troupe, kept: Path) -> None:
    article = draft(troupe.storyteller, troupe.id)
    added = [ok(upload(troupe.storyteller, article["id"], (40, 30)), 201) for _ in range(20)]

    refused = upload(troupe.storyteller, article["id"], (40, 30))

    assert refused.status_code == 409
    assert "up to 20 pictures" in refused.json()["detail"]
    # Saving words that name only some of them makes room again.
    body = "\n\n".join(figure(p["id"]) for p in added[:5])
    ok(save(troupe.storyteller, article, body))
    ok(upload(troupe.storyteller, article["id"], (40, 30)), 201)


def test_words_name_only_their_own_articles_pictures(troupe: Troupe, kept: Path) -> None:
    article = draft(troupe.storyteller, troupe.id)
    other = draft(troupe.narrator, troupe.id)
    theirs = ok(upload(troupe.narrator, other["id"]), 201)
    mine = ok(upload(troupe.storyteller, article["id"]), 201)

    assert save(troupe.storyteller, article, figure(theirs["id"])).status_code == 422
    assert save(troupe.storyteller, article, figure(str(uuid.uuid4()))).status_code == 422
    new = troupe.storyteller.client.post(
        "/blog/articles", json={"title": "Borrowed", "body": figure(mine["id"])}
    )
    assert new.status_code == 422
    saved = ok(save(troupe.storyteller, article, f"Intro.\n\n{figure(mine['id'])}"))
    assert figure(mine["id"]) in saved["body"]


def test_a_drafts_pictures_are_for_its_author_and_the_custodian_alone(
    troupe: Troupe, kept: Path, anyone: TestClient
) -> None:
    article = draft(troupe.storyteller, troupe.id)
    picture = ok(upload(troupe.storyteller, article["id"]), 201)
    ok(save(troupe.storyteller, article, figure(picture["id"])))

    mine = fetch(troupe.storyteller.client, picture)
    assert mine.status_code == 200
    assert mine.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert fetch(troupe.custodian.client, picture).status_code == 200
    assert fetch(troupe.lead.client, picture).status_code == 404
    assert fetch(anyone, picture).status_code == 404
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    assert fetch(anyone, picture).status_code == 404


def test_a_published_articles_pictures_are_anyones_and_cacheable(
    troupe: Troupe, kept: Path, anyone: TestClient
) -> None:
    article = draft(troupe.storyteller, troupe.id)
    picture = ok(upload(troupe.storyteller, article["id"]), 201)
    ok(save(troupe.storyteller, article, f"Before.\n\n{figure(picture['id'], caption='Lit')}"))

    publish(troupe, article)

    shown = fetch(anyone, picture, "600.webp")
    assert shown.status_code == 200
    assert shown.headers["cache-control"] == "public, max-age=3600"
    assert fetch(troupe.player.client, picture).status_code == 200
    # Unpublished, it is its author's and the custodian's again.
    ok(
        troupe.custodian.client.post(
            f"/blog/articles/{article['id']}/unpublish", json={"reason": "Out of date."}
        )
    )
    assert fetch(anyone, picture).status_code == 404
    assert fetch(troupe.storyteller.client, picture).status_code == 200


def test_a_revisions_new_pictures_wait_until_it_is_published(
    troupe: Troupe, kept: Path, anyone: TestClient
) -> None:
    article = draft(troupe.storyteller, troupe.id)
    old = ok(upload(troupe.storyteller, article["id"]), 201)
    ok(save(troupe.storyteller, article, figure(old["id"])))
    article = publish(troupe, article)
    new = ok(upload(troupe.storyteller, article["id"]), 201)

    # The changes take the old picture out and put a new one in.
    changed = ok(save(troupe.storyteller, article, f"Rewritten.\n\n{figure(new['id'])}"))
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))

    assert changed["body"] == figure(old["id"])
    assert fetch(anyone, old).status_code == 200
    assert fetch(anyone, new).status_code == 404
    assert fetch(troupe.storyteller.client, new).status_code == 200
    assert fetch(troupe.custodian.client, new).status_code == 200

    ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))

    assert fetch(anyone, new).status_code == 200
    # The old one, in no version now, is gone.
    assert fetch(troupe.storyteller.client, old).status_code == 404
    assert not (kept / "blog-pictures" / article["id"] / old["id"]).exists()


def test_pictures_taken_out_of_the_words_go_when_they_are_saved(
    troupe: Troupe, kept: Path, session: Session
) -> None:
    article = draft(troupe.storyteller, troupe.id)
    one = ok(upload(troupe.storyteller, article["id"]), 201)
    two = ok(upload(troupe.storyteller, article["id"]), 201)
    unused = ok(upload(troupe.storyteller, article["id"]), 201)
    folder = kept / "blog-pictures" / article["id"]

    ok(save(troupe.storyteller, article, f"{figure(one['id'])}\n\n{figure(two['id'])}"))

    assert sorted(p.name for p in folder.iterdir()) == sorted([one["id"], two["id"]])
    assert session.get(BlogPostPicture, uuid.UUID(unused["id"])) is None
    ok(save(troupe.storyteller, article, figure(two["id"])))
    assert [p.name for p in folder.iterdir()] == [two["id"]]
    # Putting back one that went is refused, rather than showing nothing.
    assert save(troupe.storyteller, article, figure(one["id"])).status_code == 422


def test_thrown_away_changes_and_deleted_drafts_take_their_pictures(
    troupe: Troupe, kept: Path
) -> None:
    article = publish(troupe, draft(troupe.storyteller, troupe.id))
    new = ok(upload(troupe.storyteller, article["id"]), 201)
    ok(save(troupe.storyteller, article, figure(new["id"])))

    ok(troupe.storyteller.client.delete(f"/blog/articles/{article['id']}/revision"))

    assert not (kept / "blog-pictures" / article["id"] / new["id"]).exists()
    other = draft(troupe.storyteller, troupe.id)
    picture = ok(upload(troupe.storyteller, other["id"]), 201)
    ok(save(troupe.storyteller, other, figure(picture["id"])))
    ok(troupe.storyteller.client.delete(f"/blog/articles/{other['id']}"), 204)
    assert not (kept / "blog-pictures" / other["id"]).exists()


def test_unpublishing_keeps_the_pictures_of_the_version_kept(troupe: Troupe, kept: Path) -> None:
    article = draft(troupe.storyteller, troupe.id)
    old = ok(upload(troupe.storyteller, article["id"]), 201)
    ok(save(troupe.storyteller, article, figure(old["id"])))
    article = publish(troupe, article)
    new = ok(upload(troupe.storyteller, article["id"]), 201)
    ok(save(troupe.storyteller, article, figure(new["id"])))

    ok(
        troupe.custodian.client.post(
            f"/blog/articles/{article['id']}/unpublish", json={"reason": "Out of date."}
        )
    )

    # The changes became the article: their picture stays, the old one goes.
    assert fetch(troupe.storyteller.client, new).status_code == 200
    assert fetch(troupe.storyteller.client, old).status_code == 404


def test_only_the_blogs_own_pictures_are_named() -> None:
    picture = uuid.uuid4()
    assert blog.pictures_in(f"![a](blog-picture:{picture})\n![b](https://example.com/x.png)") == {
        picture
    }
    assert blog.pictures_in("![a](/api/blog/body-pictures/x/600.webp)") == set()


def test_emails_show_a_blog_articles_pictures_only_when_asked() -> None:
    picture = uuid.uuid4()
    body = f'Before.\n![Candles \\] lit](blog-picture:{picture} "At \\"Elysium\\"")\nAfter.'

    shown = email_design.markdown_html(body, pictures=True)

    site = get_settings().public_url.rstrip("/")
    assert f'<img src="{site}/api/blog/body-pictures/{picture}/600.webp"' in shown
    assert 'alt="Candles ] lit"' in shown
    assert "At &quot;Elysium&quot;</p>" in shown
    assert '<p style="margin: 0 0 16px 0">Before.</p>' in shown
    assert email_design.markdown_text(body, pictures=True).split("\n") == [
        "Before.",
        '[Picture: Candles ] lit] At "Elysium"',
        "After.",
    ]
    # Anything else, troupe news say, shows the line as the text it is.
    assert "<img" not in email_design.markdown_html(body)
    outside = "![Logo](https://example.com/logo.png)"
    assert "<img" not in email_design.markdown_html(outside, pictures=True)
