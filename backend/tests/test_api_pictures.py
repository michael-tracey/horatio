"""Characters' pictures (issue #70): uploading, checking and cleaning what comes in,
the sizes kept, who may see and change them, and removal."""

import uuid
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import ExifTags, Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import pictures
from horatio.config import get_settings
from horatio.models import AuditEvent, Notification
from tests.api_helpers import Person, Troupe
from tests.test_api_character_search import member


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pictures kept in a scratch directory."""
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def photo(
    size: tuple[int, int] = (300, 200),
    kind: str = "JPEG",
    *,
    mode: str = "RGB",
    orientation: int | None = None,
    gps: bool = False,
) -> bytes:
    """A picture as a phone might send it: maybe sideways, maybe with a location."""
    image = Image.new(mode, size, (200, 40, 60, 128) if mode == "RGBA" else (200, 40, 60))
    # A white block in the top left corner, to see which way up it ends.
    image.paste((255, 255, 255) if mode == "RGB" else (255, 255, 255, 255), (0, 0, 40, 40))
    exif = Image.Exif()
    if orientation:
        exif[ExifTags.Base.Orientation] = orientation
    if gps:
        location = exif.get_ifd(ExifTags.IFD.GPSInfo)
        location[ExifTags.GPS.GPSLatitudeRef] = "N"
        location[ExifTags.GPS.GPSLatitude] = (51.0, 30.0, 12.0)
        exif[ExifTags.Base.Make] = "PhoneCo"
    out = BytesIO()
    if kind in ("JPEG", "WEBP", "PNG") and (orientation or gps):
        image.save(out, kind, exif=exif)
    else:
        image.save(out, kind)
    return out.getvalue()


def upload(person: Person, character_id: str, data: bytes, **crop: float) -> Any:
    form = {f"crop_{k}": str(v) for k, v in crop.items()}
    return person.client.post(
        f"/characters/{character_id}/picture",
        files={"file": ("me.jpg", data, "image/jpeg")},
        data=form,
    )


def opened(person: Person, url: str, name: str) -> Image.Image:
    response = person.client.get(f"{url.removeprefix('/api')}/{name}")
    assert response.status_code == 200, response.text
    assert "private" in response.headers["cache-control"]
    return Image.open(BytesIO(response.content))


def actions(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(AuditEvent.action)
            .where(AuditEvent.action.like("picture.%"))
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )


def test_upload_keeps_cleaned_copies_at_each_size(troupe: Troupe, kept: Path) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")

    sent = photo((300, 200), orientation=6, gps=True)
    assert Image.open(BytesIO(sent)).getexif().get_ifd(ExifTags.IFD.GPSInfo)  # it had one
    response = upload(troupe.player, agnes, sent)

    assert response.status_code == 200, response.text
    picture = response.json()
    url = picture["picture"]
    assert url.startswith(f"/api/characters/{agnes}/pictures/")
    assert picture["uploaded_by"] == "player"
    for size in (48, 128, 512):
        image = opened(troupe.player, url, f"{size}.webp")
        assert (image.format, image.size) == ("WEBP", (size, size))
    assert opened(troupe.player, url, "portrait.webp").size == pictures.PORTRAIT
    jpeg = opened(troupe.player, url, "portrait.jpg")
    assert (jpeg.format, jpeg.size) == ("JPEG", pictures.PORTRAIT)
    # Turned the right way up: the sideways 300 × 200 picture is kept 200 × 300.
    full = opened(troupe.player, url, "full.webp")
    assert full.size == (200, 300)
    # Orientation 6 is a quarter turn clockwise: the top left corner ends top right.
    rgb = full.convert("RGB")
    assert rgb.getpixel((195, 5)) == pytest.approx((255, 255, 255), abs=30)
    # Nothing of the phone's goes with it: no location, no camera, no EXIF at all.
    for name in ("48.webp", "512.webp", "portrait.webp", "portrait.jpg", "full.webp"):
        image = opened(troupe.player, url, name)
        assert not image.getexif(), name
        assert "exif" not in image.info and "xmp" not in image.info, name
    # Nothing as uploaded is kept, only the copies.
    files = sorted(p.name for p in kept.rglob("*") if p.is_file())
    assert files == sorted(pictures.PICTURE_FILES)
    assert actions(troupe.session) == ["picture.uploaded"]


def test_the_crop_chooses_the_portrait(troupe: Troupe, kept: Path) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    # The white block is the picture's top left 40 px; crop just that.
    response = upload(troupe.player, agnes, photo((400, 400)), x=0, y=0, size=0.1)
    assert response.status_code == 200, response.text
    assert response.json()["crop"] == {"x": 0, "y": 0, "size": 0.1}
    small = opened(troupe.player, response.json()["picture"], "48.webp").convert("RGB")
    assert small.getpixel((24, 24)) == pytest.approx((255, 255, 255), abs=30)

    # Moving the crop cuts it again, under a new address.
    moved = troupe.player.client.put(
        f"/characters/{agnes}/picture/crop", json={"x": 0.5, "y": 0.5, "size": 0.5}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["picture"] != response.json()["picture"]
    assert moved.json()["crop"] == {"x": 0.5, "y": 0.5, "size": 0.5}
    small = opened(troupe.player, moved.json()["picture"], "48.webp").convert("RGB")
    assert small.getpixel((24, 24)) == pytest.approx((200, 40, 60), abs=30)
    # The old files are gone.
    assert troupe.player.client.get(f"{response.json()['picture'][4:]}/48.webp").status_code == 404
    assert len(list((kept / "characters" / agnes).iterdir())) == 1
    assert actions(troupe.session) == ["picture.uploaded", "picture.cropped"]


@pytest.mark.parametrize(
    ("data", "said"),
    [
        (b"just some text, not a picture", "not a picture Horatio can read"),
        (photo(kind="GIF"), "Only JPEG, PNG, WebP and HEIC"),
        (photo(kind="BMP"), "Only JPEG, PNG, WebP and HEIC"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 100, "not a picture Horatio can read"),
        (b"0" * (pictures.MAX_BYTES + 10), "over 10 MB"),
    ],
)
def test_only_real_pictures_of_the_right_kind(
    troupe: Troupe, kept: Path, data: bytes, said: str
) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    response = upload(troupe.player, agnes, data)
    assert response.status_code == 422
    assert said in response.json()["detail"]
    assert not list(kept.rglob("*.webp"))


def test_an_enormous_picture_is_refused_before_it_is_decoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pictures, "MAX_PIXELS", 100 * 100)
    with pytest.raises(pictures.PictureError, match="too large"):
        pictures.read_image(photo((200, 200), kind="PNG"))


def test_png_webp_and_heic_are_read(troupe: Troupe, kept: Path) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    for data in (photo(kind="PNG", mode="RGBA"), photo(kind="WEBP")):
        assert upload(troupe.player, agnes, data).status_code == 200
    # Transparency stays in the WebP copies and is put on white for the JPEG.
    response = upload(troupe.player, agnes, photo(kind="PNG", mode="RGBA"))
    url = response.json()["picture"]
    assert opened(troupe.player, url, "128.webp").mode == "RGBA"
    assert opened(troupe.player, url, "portrait.jpg").mode == "RGB"

    import pillow_heif

    heic = BytesIO()
    try:
        pillow_heif.from_pillow(Image.new("RGB", (120, 80), (10, 120, 30))).save(heic)
    except (ValueError, RuntimeError):
        pytest.skip("This libheif has no HEIC encoder to make a test picture with.")
    response = upload(troupe.player, agnes, heic.getvalue())
    assert response.status_code == 200, response.text
    assert opened(troupe.player, response.json()["picture"], "full.webp").size == (120, 80)


def test_who_can_change_and_see_a_picture(
    troupe: Troupe, kept: Path, client_for: Callable[[], TestClient]
) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    # The troupe's staff can upload one, as can the custodian.
    assert upload(troupe.lead, agnes, photo()).status_code == 200
    assert upload(troupe.custodian, agnes, photo()).status_code == 200
    # Narrators never see sheets, and strangers nothing at all.
    for nobody in (troupe.narrator, troupe.stranger):
        assert upload(nobody, agnes, photo()).status_code == 404
        assert nobody.client.get(f"/characters/{agnes}/picture").status_code == 404
        assert nobody.client.delete(f"/characters/{agnes}/picture").status_code == 404

    response = upload(troupe.player, agnes, photo())
    url = response.json()["picture"][4:]
    for someone in (troupe.player, troupe.lead, troupe.assistant, troupe.custodian):
        assert someone.client.get(f"{url}/128.webp").status_code == 200
    for nobody in (troupe.narrator, troupe.stranger):
        assert nobody.client.get(f"{url}/128.webp").status_code == 404
    signed_out = client_for()
    assert signed_out.get(f"{url}/128.webp").status_code == 401
    # Only a picture's own files, and only the character's current picture.
    for name in ("../128.webp", "original.jpg", "128.png", "%2e%2e%2fsecrets"):
        assert troupe.player.client.get(f"{url}/{name}").status_code == 404
    other = f"/characters/{agnes}/pictures/{uuid.uuid4()}/128.webp"
    assert troupe.player.client.get(other).status_code == 404


def test_the_roster_lists_and_page_show_the_picture(troupe: Troupe, kept: Path) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    nell = member(troupe, troupe.player, "Nell", "Giovanni")
    url = upload(troupe.player, agnes, photo()).json()["picture"]

    roster = {
        e["character_name"]: e
        for e in troupe.lead.client.get(f"/troupes/{troupe.id}/characters").json()
    }
    assert roster["Agnes"]["picture"] == url
    assert roster["Nell"]["picture"] is None
    mine = {c["name"]: c for c in troupe.player.client.get("/characters").json()}
    assert (mine["Agnes"]["picture"], mine["Agnes"]["clan"]) == (url, "Toreador")
    assert (mine["Nell"]["picture"], mine["Nell"]["clan"]) == (None, "Giovanni")
    assert troupe.player.client.get(f"/characters/{nell}").json()["picture"] is None


def test_staff_remove_a_picture_and_the_uploader_is_told(troupe: Troupe, kept: Path) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    upload(troupe.player, agnes, photo())
    upload(troupe.player, agnes, photo((100, 100)))

    removed = troupe.lead.client.delete(f"/characters/{agnes}/picture")

    assert removed.status_code == 204, removed.text
    after = troupe.player.client.get(f"/characters/{agnes}/picture").json()
    assert (after["picture"], after["available"]) == (None, True)
    assert not list(kept.rglob("*.webp"))
    assert actions(troupe.session) == ["picture.uploaded", "picture.replaced", "picture.removed"]
    told = troupe.session.scalars(
        select(Notification).where(Notification.kind == "picture.removed")
    ).one()
    assert str(told.user_id) == troupe.player.id
    assert told.summary == "lead removed Agnes's picture."
    bell = troupe.player.client.get("/notifications").json()["items"]
    assert [i["summary"] for i in bell] == ["lead removed Agnes's picture."]
    # The character's log says who did what.
    log = [e["message"] for e in troupe.player.client.get(f"/characters/{agnes}/log").json()]
    assert "lead removed Agnes (player)'s picture." in log
    assert "player gave Agnes a new picture." in log
    # Nothing left to remove; and removing your own upload tells nobody.
    assert troupe.lead.client.delete(f"/characters/{agnes}/picture").status_code == 404
    upload(troupe.player, agnes, photo())
    assert troupe.player.client.delete(f"/characters/{agnes}/picture").status_code == 204
    assert (
        len(
            troupe.session.scalars(
                select(Notification).where(Notification.kind == "picture.removed")
            ).all()
        )
        == 1
    )


def test_not_set_up(troupe: Troupe) -> None:
    agnes = member(troupe, troupe.player, "Agnes", "Toreador")
    assert troupe.player.client.get(f"/characters/{agnes}/picture").json()["available"] is False
    response = upload(troupe.player, agnes, photo())
    assert response.status_code == 409
    assert response.json()["detail"] == "Pictures are not set up here."


def test_deleting_a_character_deletes_its_picture(troupe: Troupe, kept: Path) -> None:
    character = troupe.player.client.post("/characters", json={"splat": "vampire", "name": "Ida"})
    character_id = character.json()["id"]
    upload(troupe.player, character_id, photo())
    assert (kept / "characters" / character_id).is_dir()
    assert troupe.player.client.delete(f"/characters/{character_id}").status_code == 204
    assert not (kept / "characters" / character_id).exists()


@pytest.mark.parametrize(
    ("size", "crop", "square", "portrait"),
    [
        # The middle of a landscape picture, the frame centred on it.
        ((400, 300), None, (50, 0, 350, 300), (80, 0, 320, 300)),
        # A small crop high up: the frame is moved down to stay inside.
        ((400, 400), pictures.Crop(0.25, 0, 0.25), (100, 0, 200, 100), (100, 0, 200, 125)),
        # A crop at the foot: the frame is moved up.
        ((400, 400), pictures.Crop(0, 0.75, 0.25), (0, 300, 100, 400), (0, 275, 100, 400)),
        # Crops past the edges are brought back inside.
        ((400, 400), pictures.Crop(0.9, 0.9, 0.5), (200, 200, 400, 400), (200, 150, 400, 400)),
    ],
)
def test_square_and_portrait_boxes(
    size: tuple[int, int],
    crop: pictures.Crop | None,
    square: pictures.Box,
    portrait: pictures.Box,
) -> None:
    found = pictures.square_box(*size, crop)
    assert found == square
    assert pictures.portrait_box(*size, found) == portrait
