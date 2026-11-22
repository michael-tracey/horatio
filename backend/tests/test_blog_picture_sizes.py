"""Blog pictures keep their size (issue #1183): each copy's width and height, kept at
upload for the hero picture and the pictures in the words, sent with the article to
its author, the custodian and readers, and put on the pictures in feeds. Pictures
uploaded before (migration 0282) get theirs the first time they are shown."""

import io
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from horatio import email_design
from horatio.app import app
from horatio.config import get_settings
from horatio.models import BlogHeroPicture, BlogPostPicture
from tests.api_helpers import Person, Troupe

WIDE = [
    {"file": "1200.webp", "width": 1200, "height": 675},
    {"file": "600.webp", "width": 600, "height": 338},
]
HERO = [
    {"file": "1200.webp", "width": 1200, "height": 600},
    {"file": "600.webp", "width": 600, "height": 300},
]


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


def png(size: tuple[int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (120, 20, 20)).save(out, "PNG")
    return out.getvalue()


def draft(person: Person, troupe: Troupe) -> dict[str, Any]:
    body = {"title": "Lighting a scene", "summary": "", "body": "Start.", "troupe_id": troupe.id}
    return ok(person.client.post("/blog/articles", json=body), 201)


def save(person: Person, article: dict[str, Any], body: str) -> dict[str, Any]:
    words = {"title": article["title"], "summary": "", "body": body, "troupe_id": None}
    return ok(person.client.put(f"/blog/articles/{article['id']}", json=words))


def in_words(person: Person, article_id: str, size: tuple[int, int] = (1600, 900)) -> Any:
    files = {"file": ("p.png", png(size), "image/png")}
    return ok(person.client.post(f"/blog/articles/{article_id}/body-pictures", files=files), 201)


def hero(person: Person, article_id: str, size: tuple[int, int] = (1600, 900)) -> Any:
    files = {"file": ("p.png", png(size), "image/png")}
    return ok(person.client.post(f"/blog/articles/{article_id}/picture", files=files))


def figure(picture_id: str) -> str:
    return f"![Candles on a long table](blog-picture:{picture_id})"


def publish(troupe: Troupe, article: dict[str, Any]) -> dict[str, Any]:
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    return ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))


def test_a_picture_in_the_words_keeps_each_copys_size(
    troupe: Troupe, kept: Path, session: Session
) -> None:
    article = draft(troupe.storyteller, troupe)

    picture = in_words(troupe.storyteller, article["id"])
    small = in_words(troupe.storyteller, article["id"], (400, 300))

    assert picture["sizes"] == WIDE
    # Never made bigger, so both copies are the picture's own size.
    assert [s["width"] for s in small["sizes"]] == [400, 400]
    stored = session.get(BlogPostPicture, uuid.UUID(picture["id"]))
    assert stored is not None and stored.sizes == {"1200.webp": [1200, 675], "600.webp": [600, 338]}
    saved = save(troupe.storyteller, article, f"{figure(picture['id'])}\n\n{figure(small['id'])}")
    shown = {p["id"]: p for p in saved["body_pictures"]}
    assert shown[picture["id"]]["sizes"] == WIDE
    assert shown[picture["id"]]["url"] == f"/api/blog/body-pictures/{picture['id']}"
    assert shown[small["id"]]["sizes"][0] == {"file": "1200.webp", "width": 400, "height": 300}


def test_a_hero_picture_keeps_its_size_and_forgets_it_with_its_files(
    troupe: Troupe, kept: Path, session: Session
) -> None:
    article = draft(troupe.storyteller, troupe)

    first = hero(troupe.storyteller, article["id"])
    assert first["picture_sizes"] == HERO
    first_id = uuid.UUID(first["picture"].rsplit("/", 1)[1])
    assert session.get(BlogHeroPicture, first_id) is not None
    # A small one keeps its own size: 2:1, never made bigger.
    second = hero(troupe.storyteller, article["id"], (500, 400))
    assert second["picture_sizes"][0] == {"file": "1200.webp", "width": 500, "height": 250}
    session.expire_all()
    assert session.get(BlogHeroPicture, first_id) is None
    second_id = uuid.UUID(second["picture"].rsplit("/", 1)[1])
    removed = ok(troupe.storyteller.client.delete(f"/blog/articles/{article['id']}/picture"))
    assert removed["picture_sizes"] == []
    session.expire_all()
    assert session.get(BlogHeroPicture, second_id) is None


def test_a_published_articles_new_hero_has_its_size_in_the_changes(
    troupe: Troupe, kept: Path
) -> None:
    article = draft(troupe.storyteller, troupe)
    hero(troupe.storyteller, article["id"])
    publish(troupe, article)

    changed = hero(troupe.storyteller, article["id"], (800, 800))

    assert changed["picture_sizes"] == HERO
    assert changed["revision"]["picture_sizes"][0] == {
        "file": "1200.webp",
        "width": 800,
        "height": 400,
    }


def test_readers_get_the_sizes_of_a_published_articles_pictures_only(
    troupe: Troupe, kept: Path, anyone: TestClient
) -> None:
    article = draft(troupe.storyteller, troupe)
    hero(troupe.storyteller, article["id"])
    picture = in_words(troupe.storyteller, article["id"])
    article = save(troupe.storyteller, article, figure(picture["id"]))
    published = publish(troupe, article)
    # Changes waiting name a new picture, which readers don't hear of.
    new = in_words(troupe.storyteller, article["id"], (300, 200))
    save(troupe.storyteller, published, f"{figure(picture['id'])}\n\n{figure(new['id'])}")

    read = ok(anyone.get(f"/blog/public/articles/{published['slug']}"))
    listed = ok(anyone.get("/blog/public/articles"))["articles"]

    assert read["picture_sizes"] == HERO
    assert read["body_pictures"] == [
        {"id": picture["id"], "url": f"/api/blog/body-pictures/{picture['id']}", "sizes": WIDE}
    ]
    assert listed[0]["picture_sizes"] == HERO
    # Its author sees both, as the changes' words name the new one.
    mine = ok(troupe.storyteller.client.get(f"/blog/articles/{article['id']}"))
    assert {p["id"] for p in mine["body_pictures"]} == {picture["id"], new["id"]}


def test_pictures_uploaded_before_get_their_sizes_when_next_shown(
    troupe: Troupe, kept: Path, session: Session, anyone: TestClient
) -> None:
    article = draft(troupe.storyteller, troupe)
    hero(troupe.storyteller, article["id"])
    picture = in_words(troupe.storyteller, article["id"])
    article = save(troupe.storyteller, article, figure(picture["id"]))
    published = publish(troupe, article)
    # As migration 0282 leaves them: no sizes in the words, no row for the hero.
    session.execute(update(BlogPostPicture).values(sizes=None))
    session.execute(delete(BlogHeroPicture))
    session.commit()

    read = ok(anyone.get(f"/blog/public/articles/{published['slug']}"))

    assert read["picture_sizes"] == HERO
    assert read["body_pictures"][0]["sizes"] == WIDE
    session.expire_all()
    stored = session.get(BlogPostPicture, uuid.UUID(picture["id"]))
    assert stored is not None and stored.sizes is not None
    heroes = list(session.scalars(select(BlogHeroPicture)))
    assert [(str(h.post_id), h.sizes["1200.webp"]) for h in heroes] == [
        (article["id"], [1200, 600])
    ]
    # Shown again, it is read from the row: the files could go and it would stay.
    again = ok(troupe.storyteller.client.get(f"/blog/articles/{article['id']}"))
    assert again["picture_sizes"] == HERO


def test_a_picture_whose_files_are_missing_is_shown_without_sizes(
    troupe: Troupe, kept: Path, session: Session, anyone: TestClient
) -> None:
    article = draft(troupe.storyteller, troupe)
    picture = in_words(troupe.storyteller, article["id"])
    article = save(troupe.storyteller, article, figure(picture["id"]))
    published = publish(troupe, article)
    session.execute(update(BlogPostPicture).values(sizes=None))
    session.commit()
    (kept / "blog-pictures" / article["id"] / picture["id"] / "600.webp").unlink()

    read = ok(anyone.get(f"/blog/public/articles/{published['slug']}"))

    assert read["body_pictures"][0]["sizes"] == []


def test_feeds_and_emails_give_pictures_their_width_and_height(
    troupe: Troupe, kept: Path, client_for: Callable[[], TestClient]
) -> None:
    article = draft(troupe.storyteller, troupe)
    hero(troupe.storyteller, article["id"])
    picture = in_words(troupe.storyteller, article["id"])
    publish(troupe, save(troupe.storyteller, article, figure(picture["id"])))
    client_for()  # for its database session

    feed = TestClient(app).get("/blog/feed.xml").text

    assert 'width="1200" height="600"' in feed  # the hero, its 1200 px copy
    assert 'width="600" height="338"' in feed  # the picture in the words, its 600 px copy

    body = figure(picture["id"])
    sizes = {uuid.UUID(picture["id"]): {"600.webp": [600, 338], "1200.webp": [1200, 675]}}
    shown = email_design.markdown_html(body, pictures=True, picture_sizes=sizes)
    assert 'width="600" height="338"' in shown
    # Not known: as wide as an email, its height left to the picture.
    unknown = email_design.markdown_html(body, pictures=True)
    assert 'width="600" style' in unknown and "height=" not in unknown
