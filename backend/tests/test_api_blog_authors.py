"""Blog authors (#1159): a public profile for writing on the blog, apart from the
player profile. Who sees it, what it never shows, its handle, its picture, and the
custodian clearing it."""

import uuid
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.config import get_settings
from horatio.models import AuditEvent, BlogAuthor
from tests.api_helpers import Person, Troupe, sign_up
from tests.test_api_pictures import photo

AUTHOR: dict[str, Any] = {
    "display_name": "Sam the Storyteller",
    "handle": "sam_writes",
    "bio": "Running **Lords of the Night** since 2019.",
    "links": [{"label": "", "url": "https://sam.example.org"}],
}


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def visitor(client_for: Callable[[], TestClient]) -> TestClient:
    """Someone not signed in."""
    return client_for()


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def save(person: Person, **changes: Any) -> Any:
    return person.client.put("/blog/author", json={**AUTHOR, **changes})


def upload(person: Person, data: bytes, **crop: float) -> Any:
    return person.client.post(
        "/blog/author/picture",
        files={"file": ("me.jpg", data, "image/jpeg")},
        data={f"crop_{k}": str(v) for k, v in crop.items()},
    )


def test_it_starts_from_their_name_and_handle_and_nothing_else_until_they_save(
    troupe: Troupe,
) -> None:
    person = troupe.storyteller
    person.client.put(
        "/profile",
        json={"display_name": "storyteller", "bio": "My private bio.", "pronouns": "she/her"},
    )
    start = person.client.get("/blog/author").json()
    assert start == {
        "saved": False,
        "display_name": "storyteller",
        "handle": person.handle,
        "bio": "",
        "links": [],
        "picture": None,
        "picture_crop": None,
        "public": False,
        "pictures_available": False,
    }
    # Nothing is public until it is saved.
    assert person.client.get(f"/blog/authors/{person.handle}").status_code == 404

    response = save(person)
    assert response.status_code == 200, response.text
    mine = response.json()
    assert mine["saved"] is True and mine["public"] is True
    assert mine["handle"] == "sam_writes"
    # A link gets its host as a label, as a player's do.
    assert mine["links"] == [{"label": "sam.example.org", "url": "https://sam.example.org"}]
    assert person.client.get("/blog/author").json() == mine


def test_the_public_page_shows_nothing_private(troupe: Troupe, visitor: TestClient) -> None:
    person = troupe.storyteller
    person.client.put(
        "/profile",
        json={
            "display_name": "Samantha Private",
            "bio": "My private bio.",
            "pronouns": "she/her",
            "discord_handle": "samdiscord",
            "links": [{"label": "Private", "url": "https://private.example.org"}],
        },
    )
    save(person)

    page = visitor.get("/blog/authors/SAM_WRITES")
    assert page.status_code == 200, page.text
    shown = page.json()
    assert set(shown) == {
        "handle",
        "display_name",
        "bio",
        "links",
        "picture",
        "yours",
        "can_clear",
    }
    assert shown["display_name"] == "Sam the Storyteller"
    assert shown["bio"] == AUTHOR["bio"]
    assert shown["yours"] is False and shown["can_clear"] is False
    text = page.text
    for private in (
        person.email,
        person.id,
        person.handle,
        "Samantha Private",
        "My private bio.",
        "she/her",
        "samdiscord",
        "private.example.org",
    ):
        assert private not in text
    # Anyone signed in sees the same; its author and the custodian a little more.
    assert troupe.stranger.client.get("/blog/authors/sam_writes").json() == shown
    assert person.client.get("/blog/authors/sam_writes").json()["yours"] is True
    assert troupe.custodian.client.get("/blog/authors/sam_writes").json()["can_clear"] is True


def test_only_those_who_write_for_the_blog_have_a_public_page(
    troupe: Troupe, visitor: TestClient
) -> None:
    # A player on no troupe's staff can make one, but it is theirs alone to see.
    response = save(troupe.player, handle="player_writes")
    assert response.status_code == 200, response.text
    assert response.json()["public"] is False
    assert visitor.get("/blog/authors/player_writes").status_code == 404
    assert troupe.stranger.client.get("/blog/authors/player_writes").status_code == 404
    assert troupe.player.client.get("/blog/authors/player_writes").status_code == 200
    assert troupe.custodian.client.get("/blog/authors/player_writes").status_code == 200

    # Narrators write for the blog too, and so does the custodian.
    save(troupe.narrator, handle="narrator_writes")
    assert visitor.get("/blog/authors/narrator_writes").status_code == 200
    save(troupe.custodian, handle="custodian_writes")
    assert visitor.get("/blog/authors/custodian_writes").status_code == 200

    # Staff of an archived troupe only are no longer shown.
    archived = troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"})
    assert archived.status_code == 200, archived.text
    assert visitor.get("/blog/authors/narrator_writes").status_code == 404
    assert troupe.narrator.client.get("/blog/author").json()["public"] is False


def test_a_handle_is_one_authors_and_never_someone_elses(troupe: Troupe) -> None:
    assert save(troupe.storyteller).status_code == 200
    # Taken regardless of case.
    taken = save(troupe.assistant, handle="Sam_Writes")
    assert taken.status_code == 409
    assert taken.json()["detail"] == "Another author has the handle Sam_Writes."
    # Nor another person's Horatio handle, so no one writes as someone else.
    theirs = save(troupe.assistant, handle=troupe.lead.handle)
    assert theirs.status_code == 409
    assert "someone else's handle on Horatio" in theirs.json()["detail"]
    # Their own Horatio handle is theirs to use, and the @ is dropped.
    mine = save(troupe.assistant, handle=f"@{troupe.assistant.handle}")
    assert mine.status_code == 200, mine.text
    assert mine.json()["handle"] == troupe.assistant.handle
    assert save(troupe.assistant, handle="no").status_code == 422
    assert save(troupe.assistant, handle="has spaces").status_code == 422
    # Their own handle, saved again or changed in case, is fine.
    assert save(troupe.storyteller, handle="SAM_writes").status_code == 200


def test_what_it_refuses(troupe: Troupe, visitor: TestClient) -> None:
    person = troupe.storyteller
    assert save(person, display_name="  ").status_code == 422
    too_long = save(person, bio="x" * 1001)
    assert too_long.status_code == 422
    assert too_long.json()["detail"] == "Keep the bio to 1000 characters."
    links = [{"label": "", "url": f"https://{n}.example.org"} for n in range(7)]
    assert save(person, links=links).status_code == 422
    script = save(person, links=[{"label": "x", "url": "javascript:alert(1)"}])
    assert script.status_code == 422
    # Empty addresses are dropped, not refused.
    fine = save(person, links=[*links[:6], {"label": "", "url": "  "}])
    assert fine.status_code == 200, fine.text
    assert len(fine.json()["links"]) == 6
    assert visitor.get("/blog/author").status_code == 401
    assert visitor.put("/blog/author", json=AUTHOR).status_code == 401


def test_the_picture_is_cut_square_and_shown_publicly(
    troupe: Troupe, visitor: TestClient, kept: Path
) -> None:
    person = troupe.storyteller
    first = upload(person, photo())
    assert first.status_code == 409
    assert first.json()["detail"] == "Save your author profile first, then add a picture."
    save(person)

    response = upload(person, photo((400, 300)), x=0, y=0, size=0.5)
    assert response.status_code == 200, response.text
    mine = response.json()
    url: str = mine["picture"]
    assert url.startswith("/api/blog/author-pictures/")
    assert mine["picture_crop"] == {"x": 0, "y": 0, "size": 0.5}
    assert visitor.get("/blog/authors/sam_writes").json()["picture"] == url

    path = url.removeprefix("/api")
    for size in (96, 256, 512):
        got = visitor.get(f"{path}/{size}.webp")
        assert got.status_code == 200, got.text
        assert got.headers["content-type"] == "image/webp"
        assert got.headers["cache-control"] == "public, max-age=3600"
        assert Image.open(BytesIO(got.content)).size == (size, size)
    assert visitor.get(f"{path}/full.webp").status_code == 200
    # Only its own files: not a character's sizes, nor anything outside.
    assert visitor.get(f"{path}/128.webp").status_code == 404
    assert visitor.get(f"{path}/..%2F..%2Fsecret").status_code == 404

    # Moving the crop makes a new picture; the old address stops working.
    moved = person.client.put("/blog/author/picture/crop", json={"x": 0.5, "y": 0, "size": 0.5})
    assert moved.status_code == 200, moved.text
    assert moved.json()["picture"] != url
    assert visitor.get(f"{path}/96.webp").status_code == 404
    author = troupe.session.scalars(select(BlogAuthor)).one()
    assert [p.name for p in (kept / "blog-authors" / str(author.id)).iterdir()] == [
        str(author.picture_id)
    ]

    removed = person.client.delete("/blog/author/picture")
    assert removed.status_code == 200, removed.text
    assert removed.json()["picture"] is None
    assert list((kept / "blog-authors" / str(author.id)).iterdir()) == []
    assert person.client.delete("/blog/author/picture").status_code == 404


def test_the_picture_is_only_shown_while_the_page_is(
    troupe: Troupe, visitor: TestClient, kept: Path
) -> None:
    save(troupe.player, handle="player_writes")
    url = upload(troupe.player, photo()).json()["picture"].removeprefix("/api")
    assert troupe.player.client.get(f"{url}/96.webp").status_code == 200
    assert visitor.get(f"{url}/96.webp").status_code == 404
    assert troupe.stranger.client.get(f"{url}/96.webp").status_code == 404
    # And never under another author's id.
    save(troupe.storyteller)
    other = troupe.session.scalars(
        select(BlogAuthor).where(BlogAuthor.handle == "sam_writes")
    ).one()
    picture = url.rsplit("/", 1)[1]
    assert visitor.get(f"/blog/author-pictures/{other.id}/{picture}/96.webp").status_code == 404
    assert visitor.get(f"/blog/author-pictures/{uuid.uuid4()}/{picture}/96.webp").status_code == 404


def test_the_custodian_clears_a_bio_or_picture_and_it_is_logged(
    troupe: Troupe, visitor: TestClient, kept: Path, session: Session
) -> None:
    save(troupe.storyteller)
    upload(troupe.storyteller, photo())
    clear = "/blog/authors/sam_writes/clear"
    assert troupe.storyteller.client.post(clear, json={"bio": True}).status_code == 403
    assert troupe.lead.client.post(clear, json={"bio": True}).status_code == 403
    assert troupe.custodian.client.post(clear, json={}).status_code == 422
    missing = troupe.custodian.client.post("/blog/authors/nobody_here/clear", json={"bio": True})
    assert missing.status_code == 404

    response = troupe.custodian.client.post(
        clear, json={"bio": True, "picture": True, "reason": "an advert"}
    )
    assert response.status_code == 200, response.text
    page = visitor.get("/blog/authors/sam_writes").json()
    assert page["bio"] == "" and page["picture"] is None
    # The rest stays.
    assert page["display_name"] == AUTHOR["display_name"] and len(page["links"]) == 1
    author = session.scalars(select(BlogAuthor)).one()
    assert list((kept / "blog-authors" / str(author.id)).iterdir()) == []

    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "account.blog_author_cleared")
    ).one()
    assert event.level == "notice"
    assert event.data["user_id"] == troupe.storyteller.id
    log = troupe.custodian.client.get("/audit", params={"group": "accounts"}).json()
    assert any(
        e["message"] == "custodian cleared the bio and picture of storyteller's author profile"
        " on the blog, @sam_writes (an advert)."
        for e in log["entries"]
    )
    # Nothing left there to clear is refused, not logged again.
    again = troupe.custodian.client.post(clear, json={"bio": True, "picture": True})
    assert again.status_code == 422
    links = troupe.custodian.client.post(clear, json={"links": True})
    assert links.status_code == 200 and links.json()["links"] == []


def test_a_merged_accounts_profile_goes_to_the_account_it_was_merged_into(
    client_for: Callable[[], TestClient], session: Session, troupe: Troupe
) -> None:
    twice = sign_up(client_for, "twice")
    save(twice, handle="twice_writes")
    merged = troupe.custodian.client.post(
        "/accounts/merge",
        json={"keep": troupe.storyteller.handle, "merge": twice.handle, "reason": "Same person."},
    )
    assert merged.status_code == 204, merged.text
    author = session.scalars(select(BlogAuthor)).one()
    assert str(author.user_id) == troupe.storyteller.id
    assert troupe.storyteller.client.get("/blog/author").json()["handle"] == "twice_writes"
