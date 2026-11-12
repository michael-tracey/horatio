"""A troupe's own rock, paper and scissors for the Throws tab (issue #670)."""

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
from horatio.models import AuditEvent
from tests.api_helpers import Person, Troupe
from tests.test_api_character_search import member
from tests.test_api_pictures import photo


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def upload(troupe: Troupe, which: str, data: bytes, person: Person | None = None) -> Any:
    return (person or troupe.storyteller).client.post(
        f"/troupes/{troupe.id}/throw-images/{which}",
        files={"file": (f"{which}.png", data, "image/png")},
    )


def full_set(troupe: Troupe) -> dict[str, Any]:
    for which in ("rock", "paper", "scissors"):
        response = upload(troupe, which, photo((300, 200), "PNG", mode="RGBA"))
        assert response.status_code == 200, response.text
    return response.json()


def test_the_set_is_offered_only_with_all_three(troupe: Troupe, kept: Path) -> None:
    empty = troupe.storyteller.client.get(f"/troupes/{troupe.id}/throw-images").json()
    assert empty == {"name": "", "rock": None, "paper": None, "scissors": None, "complete": False}

    two = upload(troupe, "rock", photo()).json()
    two = upload(troupe, "paper", photo()).json()
    assert two["rock"] and two["paper"] and two["scissors"] is None
    assert two["complete"] is False

    three = upload(troupe, "scissors", photo()).json()
    assert three["complete"] is True


def test_each_picture_is_kept_whole_on_a_transparent_square(troupe: Troupe, kept: Path) -> None:
    images = full_set(troupe)
    member(troupe, troupe.player, "Agatha Thrown", clan="Ventrue")
    for size in (512, 128):
        got = troupe.player.client.get(f"{images['rock'].removeprefix('/api')}/{size}.webp")
        assert got.status_code == 200, got.text
        picture = Image.open(BytesIO(got.content))
        assert picture.format == "WEBP"
        assert picture.size == (size, size)
        assert picture.mode == "RGBA"
        # 300 × 200 fitted into the square leaves clear bands above and below.
        alpha = picture.getchannel("A")
        assert alpha.getpixel((size // 2, 0)) == 0
        assert alpha.getpixel((size // 2, size // 2)) != 0
        # Nothing of the upload's own goes with it.
        assert "exif" not in picture.info and "xmp" not in picture.info


def test_a_file_that_isnt_a_picture_is_refused(troupe: Troupe, kept: Path) -> None:
    refused = upload(troupe, "rock", b"not a picture at all")
    assert refused.status_code == 422
    assert "not a picture" in refused.json()["detail"]
    assert not list(kept.rglob("*.webp"))
    wrong = troupe.storyteller.client.post(
        f"/troupes/{troupe.id}/throw-images/lizard",
        files={"file": ("lizard.png", photo(), "image/png")},
    )
    assert wrong.status_code == 422


def test_only_storytellers_and_the_custodian_change_the_set(troupe: Troupe, kept: Path) -> None:
    for person in (troupe.assistant, troupe.narrator, troupe.player, troupe.stranger):
        assert upload(troupe, "rock", photo(), person).status_code == 403, person.email
        named = person.client.put(f"/troupes/{troupe.id}/throw-images/name", json={"name": "x"})
        assert named.status_code == 403, person.email
        assert person.client.delete(f"/troupes/{troupe.id}/throw-images").status_code == 403
    for person in (troupe.lead, troupe.storyteller, troupe.custodian):
        assert upload(troupe, "rock", photo(), person).status_code == 200, person.email


def test_members_see_the_set_and_others_dont(troupe: Troupe, kept: Path) -> None:
    images = full_set(troupe)
    picture = f"{images['paper'].removeprefix('/api')}/128.webp"
    # A player with no character in the troupe isn't one of its members.
    assert troupe.player.client.get(f"/troupes/{troupe.id}/throw-images").status_code == 404
    assert troupe.player.client.get(picture).status_code == 404
    assert troupe.stranger.client.get(picture).status_code == 404

    member(troupe, troupe.player, "Agatha Thrown", clan="Ventrue")
    assert troupe.player.client.get(f"/troupes/{troupe.id}/throw-images").json() == images
    assert troupe.player.client.get(picture).status_code == 200
    for person in (troupe.narrator, troupe.assistant, troupe.custodian):
        assert person.client.get(picture).status_code == 200, person.email


def test_replacing_naming_and_removing_go_in_the_troupe_log(
    troupe: Troupe, kept: Path, session: Session
) -> None:
    images = full_set(troupe)
    old = f"{images['rock'].removeprefix('/api')}/512.webp"
    replaced = upload(troupe, "rock", photo()).json()
    assert replaced["rock"] != images["rock"]
    # The picture it replaced is gone, files and all.
    assert troupe.storyteller.client.get(old).status_code == 404
    assert len(list(kept.rglob("512.webp"))) == 3

    named = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/throw-images/name", json={"name": "  Land of the  Sky bones "}
    )
    assert named.json()["name"] == "Land of the Sky bones"
    too_long = troupe.storyteller.client.put(
        f"/troupes/{troupe.id}/throw-images/name", json={"name": "x" * 61}
    )
    assert too_long.status_code == 422

    assert troupe.storyteller.client.delete(f"/troupes/{troupe.id}/throw-images").status_code == 204
    after = troupe.storyteller.client.get(f"/troupes/{troupe.id}/throw-images").json()
    assert after["complete"] is False and after["rock"] is None and after["name"] == ""
    assert not list(kept.rglob("*.webp"))
    assert troupe.storyteller.client.delete(f"/troupes/{troupe.id}/throw-images").status_code == 404

    actions = session.scalars(
        select(AuditEvent.action)
        .where(AuditEvent.action.startswith("troupe.throw_image"))
        .order_by(AuditEvent.created_at)
    ).all()
    assert actions == [
        "troupe.throw_image_uploaded",
        "troupe.throw_image_uploaded",
        "troupe.throw_image_uploaded",
        "troupe.throw_image_replaced",
        "troupe.throw_images_named",
        "troupe.throw_images_removed",
    ]
    messages = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller gave the troupe a new picture for Rock." in messages
    assert "storyteller named the troupe's throw pictures: Land of the Sky bones." in messages
