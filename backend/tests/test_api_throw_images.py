"""A troupe's own rock, paper and scissors for the Throws tab (issue #670)."""

import copy
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
from tests.api_helpers import Person, Troupe, backstory_optional
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

    # A test runs in one transaction, so every event has the same created_at and
    # their order is the database's to choose: count them, not their order.
    actions = session.scalars(
        select(AuditEvent.action).where(AuditEvent.action.startswith("troupe.throw_image"))
    ).all()
    assert sorted(actions) == sorted(
        [
            "troupe.throw_image_uploaded",
            "troupe.throw_image_uploaded",
            "troupe.throw_image_uploaded",
            "troupe.throw_image_replaced",
            "troupe.throw_images_named",
            "troupe.throw_images_removed",
        ]
    )
    messages = [e["message"] for e in troupe.lead.client.get(f"/troupes/{troupe.id}/log").json()]
    assert "storyteller gave the troupe a new picture for Rock." in messages
    assert "storyteller named the troupe's throw pictures: Land of the Sky bones." in messages


# --- Each person's choice (#671) ----------------------------------------------------


def choose(person: Person, troupe_id: str | None) -> Any:
    return person.client.patch("/preferences", json={"throw_images": troupe_id})


def another(troupe: Troupe, name: str) -> Troupe:
    """A second troupe with the same lead, for `upload` and `member`."""
    made = troupe.custodian.client.post(
        "/troupes", json={"name": name, "lead_handle": troupe.lead.handle}
    )
    assert made.status_code == 201, made.text
    other = copy.copy(troupe)
    # Its lead stands in as the storyteller who uploads; nobody else is on its staff.
    other.id, other.storyteller = made.json()["id"], troupe.lead
    backstory_optional(troupe.session, other.id)
    return other


def test_a_player_chooses_only_whole_sets_of_troupes_they_play_in(
    troupe: Troupe, kept: Path
) -> None:
    images = full_set(troupe)
    upload(troupe, "rock", photo())
    # Another troupe with a whole set, which the player doesn't play in.
    elsewhere = another(troupe, "Elsewhere by Night")
    full_set(elsewhere)
    # A third the player plays in, with only two pictures.
    half = another(troupe, "Half a Set")
    upload(half, "rock", photo())
    upload(half, "paper", photo())

    nothing = troupe.player.client.get("/throw-images").json()
    assert nothing == {"chosen": None, "offered": []}

    member(troupe, troupe.player, "Agatha Thrown", clan="Ventrue")
    member(half, troupe.player, "Bertha Halved", clan="Ventrue")
    mine = troupe.player.client.get("/throw-images").json()
    assert mine["chosen"] is None
    assert [s["troupe_name"] for s in mine["offered"]] == ["Lords of the Night"]
    offered = mine["offered"][0]
    assert offered["troupe_id"] == troupe.id
    assert offered["paper"] == images["paper"] and offered["rock"] != images["rock"]

    refused = choose(troupe.player, elsewhere.id)
    assert refused.status_code == 422
    assert "a troupe you play in" in refused.json()["detail"]
    assert choose(troupe.player, half.id).status_code == 422
    assert choose(troupe.player, "not a troupe").status_code == 422
    assert troupe.player.client.get("/preferences").json()["throw_images"] is None

    chosen = choose(troupe.player, troupe.id)
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["throw_images"] == troupe.id
    assert troupe.player.client.get("/throw-images").json()["chosen"] == offered
    # Staff play in their troupe too.
    assert choose(troupe.narrator, troupe.id).status_code == 200
    assert choose(troupe.player, None).json()["throw_images"] is None


def test_the_choice_falls_back_to_horatios_when_the_set_or_the_troupe_goes(
    troupe: Troupe, kept: Path
) -> None:
    images = full_set(troupe)
    character_id = member(troupe, troupe.player, "Agatha Thrown", clan="Ventrue")
    assert choose(troupe.player, troupe.id).status_code == 200
    assert troupe.player.client.get("/throw-images").json()["chosen"]["troupe_id"] == troupe.id

    # The troupe removes its set: Horatio's again, quietly.
    troupe.storyteller.client.delete(f"/troupes/{troupe.id}/throw-images")
    assert troupe.player.client.get("/throw-images").json() == {"chosen": None, "offered": []}

    # A new set counts again; leaving the troupe falls back, and its pictures stop coming.
    images = full_set(troupe)
    assert troupe.player.client.get("/throw-images").json()["chosen"]["troupe_id"] == troupe.id
    left = troupe.player.client.delete(f"/characters/{character_id}/troupes/{troupe.id}")
    assert left.status_code in (200, 204), left.text
    assert troupe.player.client.get("/throw-images").json() == {"chosen": None, "offered": []}
    picture = f"{images['rock'].removeprefix('/api')}/512.webp"
    assert troupe.player.client.get(picture).status_code == 404
