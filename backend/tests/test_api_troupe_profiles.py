"""Troupes' profiles (issue #119): what storytellers put on one, who sees it, and
what it never shows: to people not signed in, nothing unless the troupe made it
public, and never emails, characters or the venue's street address."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio.app import serve_frontend
from horatio.config import get_settings
from horatio.db import get_session
from horatio.models import AuditEvent
from tests.api_helpers import Person, Troupe
from tests.test_api_character_search import member
from tests.test_api_pictures import photo

PROFILE: dict[str, Any] = {
    "links": {
        "website": "https://lords.example.org",
        "discord": "https://discord.gg/lords",
        "facebook": "",
        "instagram": "https://instagram.com/lords",
        "join": "https://lords.example.org/join",
    },
    "schedule": "Second Saturday of the month, 7 pm to midnight",
    "venue": {
        "region": "Leeds",
        "name": "The Crypt",
        "address": "12 Mill Lane, Leeds LS1 4AB",
        "access": "Step-free access; a quiet room upstairs.",
    },
    "setting": {
        "chronicle": "Lords of the Night",
        "city": "Leeds",
        "era": "Modern nights",
        "tone": "Political intrigue, slow-burning horror.",
    },
    "new_players": "welcoming",
    "min_age": 18,
    "content_notes": "Violence and body horror.",
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


def save(troupe: Troupe, person: Person | None = None, **changes: Any) -> Any:
    body = {**PROFILE, "public": False, "contact_id": troupe.storyteller.id, **changes}
    return (person or troupe.storyteller).client.put(f"/troupes/{troupe.id}/profile", json=body)


def add_game(troupe: Troupe, starts_in: timedelta, hours: int = 5, person: Person | None = None):
    start = datetime.now(UTC) + starts_in
    return (person or troupe.storyteller).client.post(
        f"/troupes/{troupe.id}/games",
        json={
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=hours)).isoformat(),
        },
    )


def upload_portrait(troupe: Troupe, data: bytes, **crop: float) -> Any:
    return troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/portrait",
        files={"file": ("us.jpg", data, "image/jpeg")},
        data={f"crop_{k}": str(v) for k, v in crop.items()},
    )


def emails(troupe: Troupe) -> list[str]:
    return [
        p.email
        for p in (troupe.lead, troupe.storyteller, troupe.narrator, troupe.player, troupe.custodian)
    ]


def test_storytellers_fill_in_the_profile_and_it_shows_to_anyone_signed_in(
    troupe: Troupe,
) -> None:
    response = save(troupe)
    assert response.status_code == 200, response.text
    assert add_game(troupe, timedelta(days=30)).status_code == 201
    assert add_game(troupe, timedelta(days=2)).status_code == 201

    # Anyone signed in sees it, even someone with nothing to do with the troupe.
    seen = troupe.stranger.client.get(f"/troupes/{troupe.id}/profile")
    assert seen.status_code == 200, seen.text
    profile = seen.json()
    assert profile["links"]["website"] == "https://lords.example.org"
    assert profile["links"]["facebook"] is None
    assert profile["schedule"] == PROFILE["schedule"]
    assert profile["venue"]["address"] == "12 Mill Lane, Leeds LS1 4AB"
    assert profile["venue"]["address_hidden"] is False
    assert profile["setting"]["era"] == "Modern nights"
    assert profile["new_players"] == "welcoming"
    assert profile["min_age"] == 18
    assert profile["contact"] == {
        "id": troupe.storyteller.id,
        "handle": troupe.storyteller.handle,
        "display_name": "storyteller",
    }
    assert profile["lead"]["handle"] == troupe.lead.handle
    assert profile["can_edit"] is False
    # The next game first.
    starts = [g["starts_at"] for g in profile["games"]]
    assert len(starts) == 2 and starts == sorted(starts)
    # Never anyone's email, not even to people signed in.
    for email in emails(troupe):
        assert email not in seen.text
    assert troupe.storyteller.client.get(f"/troupes/{troupe.id}/profile").json()["can_edit"]
    logged = troupe.session.scalars(
        select(AuditEvent.action).where(AuditEvent.action.like("troupe.%"))
    )
    assert {"troupe.profile_changed", "troupe.game_added"} <= set(logged)


def test_a_private_profile_is_refused_to_people_not_signed_in(
    troupe: Troupe, visitor: TestClient, kept: Path
) -> None:
    save(troupe)
    upload_portrait(troupe, photo())
    portrait = troupe.stranger.client.get(f"/troupes/{troupe.id}/profile").json()["portrait"]

    response = visitor.get(f"/troupes/{troupe.id}/profile")
    assert response.status_code == 404
    # Nothing in it shows that the troupe exists.
    assert "Lords" not in response.text
    assert visitor.get(f"{portrait.removeprefix('/api')}/512.webp").status_code == 404
    # Nor anything else about the troupe.
    assert visitor.get(f"/troupes/{troupe.id}").status_code == 401
    assert visitor.get("/troupes").status_code == 401


def test_a_public_profile_shows_to_anyone_but_never_the_street_address(
    troupe: Troupe, visitor: TestClient, kept: Path
) -> None:
    member(troupe, troupe.player, "Agnes", "Toreador")
    assert save(troupe, public=True).status_code == 200
    add_game(troupe, timedelta(days=3))
    upload_portrait(troupe, photo())

    response = visitor.get(f"/troupes/{troupe.id}/profile")
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["public"] is True
    assert profile["venue"]["address"] is None
    assert profile["venue"]["address_hidden"] is True
    assert profile["venue"]["name"] == "The Crypt"
    assert "Mill Lane" not in response.text
    assert len(profile["games"]) == 1
    assert profile["can_edit"] is False
    # No emails, no characters, nothing only members see.
    for email in emails(troupe):
        assert email not in response.text
    assert "Agnes" not in response.text
    # Its portrait shows too, for link previews.
    portrait = visitor.get(f"{profile['portrait'].removeprefix('/api')}/512.webp")
    assert portrait.status_code == 200
    assert Image.open(BytesIO(portrait.content)).size == (512, 512)
    # The rest of the troupe stays for people signed in.
    assert visitor.get(f"/troupes/{troupe.id}").status_code == 401
    assert visitor.get(f"/troupes/{troupe.id}/staff").status_code == 401
    assert visitor.get(f"/troupes/{troupe.id}/characters").status_code == 401

    # Unticked again, it is private again, portrait and all.
    assert save(troupe, public=False).status_code == 200
    assert visitor.get(f"/troupes/{troupe.id}/profile").status_code == 404
    assert visitor.get(f"{profile['portrait'].removeprefix('/api')}/512.webp").status_code == 404


def test_the_public_switch_changes_only_who_sees_the_profile(
    troupe: Troupe, visitor: TestClient
) -> None:
    assert save(troupe).status_code == 200
    switched = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/profile/public", json={"public": True}
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["public"] is True
    assert switched.json()["schedule"] == PROFILE["schedule"]
    assert visitor.get(f"/troupes/{troupe.id}/profile").status_code == 200

    # Saving the rest of the profile without saying leaves it public.
    body = {**PROFILE, "schedule": "Every other Friday"}
    saved = troupe.storyteller.client.put(f"/troupes/{troupe.id}/profile", json=body)
    assert saved.json()["public"] is True

    # Only storytellers switch it.
    for person in (troupe.assistant, troupe.player):
        refused = person.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": False})
        assert refused.status_code == 403
    off = troupe.lead.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": False})
    assert off.json()["public"] is False
    assert visitor.get(f"/troupes/{troupe.id}/profile").status_code == 404


def test_people_not_signed_in_change_nothing(
    troupe: Troupe, visitor: TestClient, kept: Path
) -> None:
    save(troupe, public=True)
    game = add_game(troupe, timedelta(days=3)).json()
    body = {**PROFILE, "public": True}
    assert visitor.put(f"/troupes/{troupe.id}/profile", json=body).status_code == 401
    start = datetime.now(UTC) + timedelta(days=1)
    when = {"starts_at": start.isoformat(), "ends_at": (start + timedelta(hours=4)).isoformat()}
    assert visitor.post(f"/troupes/{troupe.id}/games", json=when).status_code == 401
    assert visitor.delete(f"/troupes/{troupe.id}/games/{game['id']}").status_code == 401
    sent = visitor.post(
        f"/troupes/{troupe.id}/portrait", files={"file": ("us.jpg", photo(), "image/jpeg")}
    )
    assert sent.status_code == 401
    assert visitor.delete(f"/troupes/{troupe.id}/portrait").status_code == 401
    assert visitor.delete(f"/troupes/{troupe.id}/banner").status_code == 401


def test_only_storytellers_edit_the_profile(troupe: Troupe) -> None:
    for person in (troupe.assistant, troupe.narrator, troupe.player, troupe.stranger):
        assert save(troupe, person).status_code == 403, person.email
        assert add_game(troupe, timedelta(days=1), person=person).status_code == 403
    for person in (troupe.lead, troupe.storyteller, troupe.custodian):
        assert save(troupe, person).status_code == 200, person.email


def test_the_contact_for_new_players_is_one_of_the_staff(troupe: Troupe) -> None:
    response = save(troupe, contact_id=troupe.player.id)
    assert response.status_code == 422
    assert "staff" in response.json()["detail"]
    assert save(troupe, contact_id=troupe.lead.id).status_code == 200
    assert save(troupe, contact_id=troupe.narrator.id).status_code == 200
    # Someone who leaves the staff is no longer shown as the contact.
    left = troupe.lead.client.delete(f"/troupes/{troupe.id}/staff/{troupe.narrator.id}")
    assert left.status_code == 204
    assert troupe.player.client.get(f"/troupes/{troupe.id}/profile").json()["contact"] is None


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "lords.example.org", "data:text/html,hi", "ftp://x.org"]
)
def test_links_are_web_addresses(troupe: Troupe, url: str) -> None:
    response = save(troupe, links={**PROFILE["links"], "website": url})
    assert response.status_code == 422
    assert "web address" in response.json()["detail"]


def test_games_end_after_they_start_and_are_still_to_come(troupe: Troupe) -> None:
    start = datetime.now(UTC) + timedelta(days=1)
    backwards = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/games",
        json={"starts_at": start.isoformat(), "ends_at": (start - timedelta(hours=1)).isoformat()},
    )
    assert backwards.status_code == 422
    assert add_game(troupe, timedelta(days=-2)).status_code == 422
    assert add_game(troupe, timedelta(days=1), hours=24 * 8).status_code == 422
    # A time without a zone means nothing to players elsewhere.
    naive = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/games",
        json={"starts_at": "2030-01-01T19:00:00", "ends_at": "2030-01-01T23:00:00"},
    )
    assert naive.status_code == 422

    # A game under way still shows; one over does not.
    under_way = add_game(troupe, timedelta(hours=-1), hours=4).json()
    later = add_game(troupe, timedelta(days=5)).json()
    games = troupe.player.client.get(f"/troupes/{troupe.id}/profile").json()["games"]
    assert [g["id"] for g in games] == [under_way["id"], later["id"]]

    removed = troupe.storyteller.client.delete(f"/troupes/{troupe.id}/games/{later['id']}")
    assert removed.status_code == 204
    games = troupe.player.client.get(f"/troupes/{troupe.id}/profile").json()["games"]
    assert [g["id"] for g in games] == [under_way["id"]]


def test_the_portrait_is_cropped_square_and_shows_in_troupe_lists(
    troupe: Troupe, kept: Path
) -> None:
    response = upload_portrait(troupe, photo((400, 400)), x=0, y=0, size=0.1)
    assert response.status_code == 200, response.text
    url = response.json()["portrait"]
    assert url.startswith(f"/api/troupes/{troupe.id}/portraits/")
    assert response.json()["portrait_crop"] == {"x": 0, "y": 0, "size": 0.1}
    # The white block is the picture's top left 40 px.
    small = troupe.player.client.get(f"{url.removeprefix('/api')}/48.webp")
    assert Image.open(BytesIO(small.content)).convert("RGB").getpixel((24, 24)) == pytest.approx(
        (255, 255, 255), abs=30
    )
    listed = troupe.player.client.get("/troupes").json()
    assert next(t for t in listed if t["id"] == troupe.id)["portrait"] == url

    moved = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/portrait/crop", json={"x": 0.5, "y": 0.5, "size": 0.5}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["portrait"] != url
    assert troupe.player.client.get(f"{url.removeprefix('/api')}/48.webp").status_code == 404

    assert troupe.storyteller.client.delete(f"/troupes/{troupe.id}/portrait").status_code == 204
    assert troupe.player.client.get(f"/troupes/{troupe.id}").json()["portrait"] is None
    assert not list(kept.rglob("*.webp"))


def test_the_banner_is_cut_wide(troupe: Troupe, kept: Path) -> None:
    response = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/banner",
        files={"file": ("wide.jpg", photo((1200, 900)), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    banner = response.json()["banner"]
    for width in (1500, 750):
        got = troupe.player.client.get(f"{banner.removeprefix('/api')}/{width}.webp")
        assert Image.open(BytesIO(got.content)).size == (width, width // 3)
    assert troupe.storyteller.client.delete(f"/troupes/{troupe.id}/banner").status_code == 204
    assert troupe.player.client.get(f"{banner.removeprefix('/api')}/750.webp").status_code == 404


def test_an_archived_troupe_profile_is_gone(troupe: Troupe, visitor: TestClient) -> None:
    save(troupe, public=True)
    archived = troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"})
    assert archived.status_code == 200
    assert visitor.get(f"/troupes/{troupe.id}/profile").status_code == 404
    assert troupe.player.client.get(f"/troupes/{troupe.id}/profile").status_code == 404
    assert troupe.custodian.client.get(f"/troupes/{troupe.id}/profile").status_code == 200


@pytest.fixture
def site(tmp_path: Path, session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The built frontend's index.html, served as it is in production."""
    (tmp_path / "index.html").write_text(
        "<title>Horatio</title>\n"
        '<meta name="description" content="Characters, troupes and downtimes." />\n'
        '<meta property="og:title" content="Horatio" />\n'
        '<meta property="og:description" content="Characters, troupes and downtimes." />\n'
        '<meta property="og:image" content="__HORATIO_PUBLIC_URL__/preview.jpg" />\n'
        '<meta property="og:image:width" content="1200" />\n'
        '<meta name="twitter:card" content="summary_large_image" />\n'
    )
    monkeypatch.setattr(get_settings(), "public_url", "https://horatio.example.org")
    app = FastAPI()
    app.dependency_overrides[get_session] = lambda: session
    serve_frontend(tmp_path, app)
    return TestClient(app)


def test_a_public_profile_link_previews_with_the_troupe(
    troupe: Troupe, site: TestClient, kept: Path
) -> None:
    troupe.lead.client.patch(
        f"/troupes/{troupe.id}", json={"description": 'Vampires & "intrigue".\nMore.'}
    )
    upload_portrait(troupe, photo())
    # Private: the site's own preview, which says nothing about the troupe.
    save(troupe)
    page = site.get(f"/t/{troupe.id}").text
    assert 'content="Horatio"' in page
    assert "Lords of the Night" not in page

    save(troupe, public=True)
    page = site.get(f"/t/{troupe.id}").text
    assert "<title>Lords of the Night · Horatio</title>" in page
    assert '<meta property="og:title" content="Lords of the Night" />' in page
    assert 'content="Vampires &amp; &quot;intrigue&quot;."' in page
    portrait = troupe.player.client.get(f"/troupes/{troupe.id}").json()["portrait"]
    assert f'content="https://horatio.example.org{portrait}/512.webp"' in page
    assert '<meta name="twitter:card" content="summary" />' in page
    # Any other page, or a troupe that is not there, keeps the site's.
    assert "Lords" not in site.get("/troupes").text
    assert "preview.jpg" in site.get("/t/00000000-0000-0000-0000-000000000000").text
