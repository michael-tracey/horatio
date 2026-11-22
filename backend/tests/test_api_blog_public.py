"""The game developer blog's reading pages (#1158): signed out, only published
articles, and only what the blog shows of them; paging, featured and tags; and hero
pictures public once their article is."""

import io
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from horatio import blog_bell
from horatio.api import blog_public
from horatio.config import get_settings
from horatio.models import BlogPost
from horatio.models import Troupe as TroupeRow
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
        "picture_sizes": [],
        "author": {"name": "storyteller", "handle": None},
        # The troupe isn't public, so the blog names it, and nothing more (#1160).
        "troupe": {"name": "Lords of the Night", "card": None},
        "tags": [
            {"id": shown["tags"][0]["id"], "name": "Storytelling", "slug": "storytelling"},
            {
                "id": shown["tags"][1]["id"],
                "name": "Safety and consent",
                "slug": "safety-and-consent",
            },
        ],
        "featured": False,
        "published_at": shown["published_at"],
        "revised_at": None,
        "body_pictures": [],
        "author_card": None,
        "edit": None,
    }
    assert "Not yet" not in str(shown) and "New words" not in str(shown)
    # Its author has a way to change it from there.
    mine = ok(troupe.storyteller.client.get("/blog/public/articles/running-your-first-elysium"))
    assert mine["edit"] == f"/blog/write/{article['id']}"


def card_of(troupe: Troupe, session: Session, **more: Any) -> dict[str, Any]:
    """The troupe's card as the blog shows it, once it is public with a description, an
    abbreviation and a portrait."""
    ok(troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": True}))
    body = {"description": "A Camarilla game in Leeds.", "abbreviation": "LotN", **more}
    ok(troupe.lead.client.patch(f"/troupes/{troupe.id}", json=body))
    portrait = uuid.uuid4()
    session.get_one(TroupeRow, troupe.id).portrait_id = portrait
    session.flush()
    return {
        "id": troupe.id,
        "name": "Lords of the Night",
        "abbreviation": "LotN",
        "portrait": f"/api/troupes/{troupe.id}/portraits/{portrait}",
        "description": "A Camarilla game in Leeds.",
    }


def test_a_public_troupe_has_its_card(troupe: Troupe, anyone: TestClient, session: Session) -> None:
    published(troupe)
    card = card_of(troupe, session)
    path = "/blog/public/articles/running-your-first-elysium"

    assert ok(anyone.get(path))["troupe"] == {"name": "Lords of the Night", "card": card}
    # The list of articles names it the same way.
    [listed] = ok(anyone.get("/blog/public/articles"))["articles"]
    assert listed["troupe"] == {"name": "Lords of the Night", "card": card}
    # Its author's preview and the custodian's queue have the card too.
    [mine] = ok(troupe.storyteller.client.get("/blog/articles/mine"))
    assert mine["troupe"]["card"] == card
    [queued] = ok(troupe.custodian.client.get("/blog/queue"))["published"]
    assert queued["troupe"]["card"] == card
    assert ok(troupe.storyteller.client.get("/blog/writer"))["troupes"][0]["card"] == card


def test_a_troupe_without_an_abbreviation_goes_by_its_made_one(
    troupe: Troupe, anyone: TestClient, session: Session
) -> None:
    published(troupe)
    card_of(troupe, session, abbreviation="")

    shown = ok(anyone.get("/blog/public/articles/running-your-first-elysium"))

    assert shown["troupe"]["card"]["abbreviation"] == "LotN"


def test_a_private_troupe_is_named_and_nothing_more(troupe: Troupe, anyone: TestClient) -> None:
    published(troupe)
    body = {"description": "Only for us", "abbreviation": "LotN"}
    ok(troupe.lead.client.patch(f"/troupes/{troupe.id}", json=body))

    shown = ok(anyone.get("/blog/public/articles/running-your-first-elysium"))
    listed = ok(anyone.get("/blog/public/articles"))

    assert shown["troupe"] == {"name": "Lords of the Night", "card": None}
    # Not its id, its abbreviation or its description, anywhere on the blog.
    for found in (shown, listed):
        assert str(troupe.id) not in str(found)
        assert "Only for us" not in str(found) and "LotN" not in str(found)
    # Its author still sees which troupe it is, to choose it.
    [mine] = ok(troupe.storyteller.client.get("/blog/articles/mine"))
    assert (mine["troupe"]["id"], mine["troupe"]["card"]) == (troupe.id, None)


def test_a_troupe_that_goes_private_or_is_archived_drops_its_card(
    troupe: Troupe, anyone: TestClient, session: Session
) -> None:
    published(troupe)
    card_of(troupe, session)
    path = "/blog/public/articles/running-your-first-elysium"
    named = {"name": "Lords of the Night", "card": None}

    ok(troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": False}))
    shown = ok(anyone.get(path))
    assert shown["troupe"] == named
    assert str(troupe.id) not in str(shown)

    ok(troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": True}))
    assert ok(anyone.get(path))["troupe"]["card"] is not None

    ok(troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"}))
    shown = ok(anyone.get(path))
    assert shown["troupe"] == named
    assert str(troupe.id) not in str(ok(anyone.get("/blog/public/articles")))
    # The custodian's queue says why: it is public, but archived.
    [queued] = ok(troupe.custodian.client.get("/blog/queue"))["published"]
    assert queued["troupe"] == {
        "id": troupe.id,
        "name": "Lords of the Night",
        "archived": True,
        "public": True,
        "card": None,
    }


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

    assert tagged["tag"]["name"] == "Safety and consent"
    assert tagged["tag"]["slug"] == "safety-and-consent"
    assert titles(tagged) == ["On safety and scenes", "On safety"]
    assert tagged["total"] == 2
    assert titles(filtered) == ["On safety and scenes"]
    # Only tags with published articles, in the custodian's order, counting those.
    assert tags == {"storytelling": 1, "safety-and-consent": 2}
    assert anyone.get("/blog/public/tags/no-such-tag").status_code == 404
    assert anyone.get("/blog/public/articles", params={"tag": "nope"}).status_code == 404


def test_retired_renamed_and_merged_tags_on_the_blog(troupe: Troupe, anyone: TestClient) -> None:
    c = troupe.custodian.client
    kept = {t["name"]: t["id"] for t in ok(c.get("/blog/tags/kept"))}
    one = published(troupe, title="On safety")
    two = published(troupe, title="On downtimes")
    tag(troupe, one, "Safety and consent")
    tag(troupe, two, "Downtimes")

    # Retired, a tag stays on its articles, in the list and at its page.
    ok(c.put(f"/blog/tags/{kept['Safety and consent']}/retired", json={"retired": True}))
    listed = [t["slug"] for t in ok(anyone.get("/blog/public/tags"))]
    assert "safety-and-consent" in listed
    assert titles(ok(anyone.get("/blog/public/tags/safety-and-consent"))) == ["On safety"]

    # Renamed once a published article has it, it keeps its address.
    ok(c.put(f"/blog/tags/{kept['Downtimes']}", json={"name": "Between games"}))
    renamed = ok(anyone.get("/blog/public/tags/downtimes"))
    assert renamed["tag"]["name"] == "Between games"
    assert titles(renamed) == ["On downtimes"]

    # Merged into another, its articles are on the other's, and its address gives the
    # other's page, for the app to move to (#1184).
    path = f"/blog/tags/{kept['Downtimes']}/merge"
    ok(c.post(path, json={"into_id": kept["Community"]}))
    assert titles(ok(anyone.get("/blog/public/tags/community"))) == ["On downtimes"]
    moved = ok(anyone.get("/blog/public/tags/downtimes"))
    assert moved["tag"] == {"id": kept["Community"], "name": "Community", "slug": "community"}
    assert titles(moved) == ["On downtimes"]
    assert titles(ok(anyone.get("/blog/public/articles", params={"tag": "downtimes"}))) == [
        "On downtimes"
    ]
    assert "downtimes" not in [t["slug"] for t in ok(anyone.get("/blog/public/tags"))]


def test_the_new_article_bell_leads_to_its_page(
    troupe: Troupe, anyone: TestClient, session: Session
) -> None:
    article = published(troupe)

    link = blog_bell.link(session.get_one(BlogPost, article["id"]))

    # The bell's /blog/<slug> is the page that reads /blog/public/articles/<slug>.
    assert link == "/blog/running-your-first-elysium"
    shown = ok(anyone.get(link.replace("/blog/", "/blog/public/articles/", 1)))
    assert shown["title"] == "Running your first Elysium"


def test_the_blogs_own_addresses_arent_slugs(troupe: Troupe) -> None:
    article = draft(troupe.storyteller, troupe.id, title="Write")

    assert article["slug"] == "write-2"
    path = f"/blog/articles/{article['id']}/slug"
    refused = troupe.storyteller.client.put(path, json={"slug": "tags"})
    assert refused.status_code == 409


# --- authors ------------------------------------------------------------------------------


def profile(person: Person, **more: Any) -> None:
    body = {"display_name": "Mara Quinn", "handle": "maraq", "bio": "I run *Lords*.", "links": []}
    ok(person.client.put("/blog/author", json={**body, **more}))


def test_an_article_shows_its_authors_card_once_they_have_a_profile(
    troupe: Troupe, anyone: TestClient
) -> None:
    published(troupe)
    path = "/blog/public/articles/running-your-first-elysium"
    before = ok(anyone.get(path))
    assert before["author"] == {"name": "storyteller", "handle": None}
    assert before["author_card"] is None

    profile(troupe.storyteller)

    after = ok(anyone.get(path))
    assert after["author"] == {"name": "Mara Quinn", "handle": "maraq"}
    assert after["author_card"] == {
        "handle": "maraq",
        "display_name": "Mara Quinn",
        "bio": "I run *Lords*.",
        "links": [],
        "picture": None,
    }
    assert ok(anyone.get("/blog/public/articles"))["articles"][0]["author"]["handle"] == "maraq"


def test_an_authors_page_lists_only_their_published_articles(
    troupe: Troupe, anyone: TestClient
) -> None:
    profile(troupe.storyteller)
    published(troupe, title="Mine, published")
    draft(troupe.storyteller, troupe.id, title="Mine, a draft")
    draft(troupe.custodian, None, title="The custodian's")
    other = draft(troupe.custodian, None, title="Not theirs")
    ok(troupe.custodian.client.post(f"/blog/articles/{other['id']}/submit"))
    ok(troupe.custodian.client.post(f"/blog/articles/{other['id']}/publish"))

    found = ok(anyone.get("/blog/public/authors/MaraQ/articles"))

    assert titles(found) == ["Mine, published"]
    assert found["total"] == 1
    assert found["author"] == {"name": "Mara Quinn", "handle": "maraq"}
    assert anyone.get("/blog/public/authors/nobody/articles").status_code == 404


def test_an_author_no_longer_writing_keeps_a_page_while_an_article_is_published(
    troupe: Troupe, anyone: TestClient
) -> None:
    profile(troupe.storyteller)
    article = published(troupe)
    ok(troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"}))

    assert titles(ok(anyone.get("/blog/public/authors/maraq/articles"))) == [article["title"]]

    path = f"/blog/articles/{article['id']}/unpublish"
    ok(troupe.custodian.client.post(path, json={"reason": "Out of date"}))
    assert anyone.get("/blog/public/authors/maraq/articles").status_code == 404


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
        assert image.size == (600, 300)
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
